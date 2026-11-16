"""Códigos por correo con intentos limitados y autorización de un solo uso."""

import datetime
import hashlib
import hmac
import logging
import secrets
import smtplib
import ssl
from email.message import EmailMessage

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from backend.config import settings
from backend.core.security import get_password_hash
from backend.db.database import SessionLocal
from backend.db.models import PasswordRecoveryCode, PasswordResetToken, Usuario

logger = logging.getLogger(__name__)
RECOVERY_MESSAGE = "Código de recuperación enviado. Revisa tu bandeja de entrada y la carpeta de correo no deseado."
INVALID_LINK_MESSAGE = "La autorización para cambiar la contraseña ya no es válida. Solicita un nuevo código."
INVALID_CODE_MESSAGE = "El código es incorrecto, venció o alcanzó el límite de intentos. Solicita uno nuevo si es necesario."
MAX_CODE_ATTEMPTS = 5


def _now():
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def ensure_mail_configured():
    if (
        not settings.SMTP_HOST or not settings.SMTP_FROM_EMAIL
        or not (settings.SMTP_USE_SSL or settings.SMTP_STARTTLS)
    ):
        raise HTTPException(status_code=503, detail="La recuperación por correo no está disponible en este momento. Contacta al administrador.")


def _code_digest(user_id: str, code: str) -> str:
    return hmac.new(settings.JWT_SECRET_KEY.encode("utf-8"),
                    f"password-recovery:{user_id}:{code}".encode("utf-8"), hashlib.sha256).hexdigest()


def send_reset_email(email: str, code: str):
    message = EmailMessage()
    message["Subject"] = "Recupera tu acceso a VIRALES Jalisco"
    message["From"] = settings.SMTP_FROM_EMAIL
    message["To"] = email
    message.set_content(
        "Recibimos una solicitud para cambiar tu contraseña de VIRALES Jalisco.\n\n"
        f"Tu código de recuperación es: {code}\n\n"
        "Escríbelo en la pantalla de recuperación de la web de VIRALES.\n"
        f"El código vence en {settings.PASSWORD_RESET_CODE_EXPIRE_MINUTES} minutos y solo se puede usar una vez.\n"
        "Si no solicitaste este cambio, ignora este correo. Tu contraseña seguirá siendo la misma."
    )
    message.add_alternative(
        '<html lang="es"><body style="font-family:Arial,sans-serif;color:#302537;line-height:1.6">'
        '<h2>Recupera tu acceso a VIRALES</h2>'
        '<p>Recibimos una solicitud para cambiar tu contraseña.</p>'
        '<p>Escribe este código en la pantalla de recuperación de la web de VIRALES:</p>'
        f'<p style="font-size:32px;font-weight:bold;letter-spacing:8px;color:#652379">{code}</p>'
        f'<p>Vence en {settings.PASSWORD_RESET_CODE_EXPIRE_MINUTES} minutos y solo puede usarse una vez.</p>'
        '<p>No compartas este código con otras personas.</p>'
        '<p>Si no solicitaste este cambio, ignora este correo. Tu contraseña seguirá siendo la misma.</p>'
        '</body></html>',
        subtype="html",
    )
    context = ssl.create_default_context()
    smtp_type = smtplib.SMTP_SSL if settings.SMTP_USE_SSL else smtplib.SMTP
    kwargs = {"timeout": 10}
    if settings.SMTP_USE_SSL:
        kwargs["context"] = context
    with smtp_type(settings.SMTP_HOST, settings.SMTP_PORT, **kwargs) as smtp:
        if not settings.SMTP_USE_SSL:
            smtp.starttls(context=context)
        if settings.SMTP_USERNAME:
            smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        smtp.send_message(message)


def request_password_reset(email: str):
    """Se ejecuta después de responder para no revelar cuentas por el tiempo SMTP."""
    with SessionLocal() as db:
        user = db.query(Usuario).filter(func.lower(Usuario.email) == email).first()
        if not user or not user.hashed_password:
            return
        now = _now()
        cutoff = now - datetime.timedelta(seconds=max(60, settings.PASSWORD_RESET_COOLDOWN_SECONDS))
        code = f"{secrets.randbelow(1000000):06d}"
        values = dict(
            code_hash=_code_digest(user.uid, code), password_digest=_digest(user.hashed_password),
            expires_at=now + datetime.timedelta(minutes=max(1, settings.PASSWORD_RESET_CODE_EXPIRE_MINUTES)),
            requested_at=now, attempts=0,
        )
        existing = db.query(PasswordRecoveryCode).filter_by(user_id=user.uid)
        # La actualización condicional impide dos envíos simultáneos durante el cooldown.
        if existing.first():
            if not existing.filter(PasswordRecoveryCode.requested_at <= cutoff).update(values, synchronize_session=False):
                return
        else:
            db.add(PasswordRecoveryCode(user_id=user.uid, **values))
        db.query(PasswordResetToken).filter_by(user_id=user.uid).delete(synchronize_session=False)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return
        try:
            send_reset_email(user.email, code)
        except (OSError, smtplib.SMTPException, ValueError):
            # No registrar correos, tokens, enlaces ni credenciales del proveedor.
            logger.error("No se pudo entregar un correo de recuperación; revisar la configuración SMTP.")
            db.query(PasswordRecoveryCode).filter_by(user_id=user.uid, code_hash=values["code_hash"]).update(
                {"expires_at": now}, synchronize_session=False,
            )
            db.commit()


def verify_recovery_code(db, email: str, code: str) -> str:
    user = db.query(Usuario).filter(func.lower(Usuario.email) == email).first()
    now = _now()
    if not user or not user.hashed_password:
        raise HTTPException(status_code=400, detail=INVALID_CODE_MESSAGE)
    query = db.query(PasswordRecoveryCode).filter(
        PasswordRecoveryCode.user_id == user.uid,
        PasswordRecoveryCode.expires_at > now,
        PasswordRecoveryCode.attempts < MAX_CODE_ATTEMPTS,
        PasswordRecoveryCode.password_digest == _digest(user.hashed_password),
    )
    # El incremento atómico limita también las comprobaciones concurrentes.
    if not query.update({"attempts": PasswordRecoveryCode.attempts + 1}, synchronize_session=False):
        db.rollback()
        raise HTTPException(status_code=400, detail=INVALID_CODE_MESSAGE)
    record = db.get(PasswordRecoveryCode, user.uid, populate_existing=True)
    if not hmac.compare_digest(record.code_hash, _code_digest(user.uid, code)):
        db.commit()
        raise HTTPException(status_code=400, detail=INVALID_CODE_MESSAGE)
    token = secrets.token_urlsafe(32)
    # Consumo y creación del permiso temporal en la misma transacción.
    record.expires_at = now
    record.code_hash = _digest(secrets.token_urlsafe(32))
    grant = db.get(PasswordResetToken, user.uid)
    if grant is None:
        grant = PasswordResetToken(user_id=user.uid)
        db.add(grant)
    grant.token_hash = _digest(token)
    grant.password_digest = _digest(user.hashed_password)
    grant.expires_at = now + datetime.timedelta(minutes=5)
    grant.requested_at = now
    db.commit()
    return token


def reset_password(db, token: str, password: str):
    if len(password.encode("utf-8")) > 72:
        raise HTTPException(status_code=400, detail="La contraseña es demasiado larga.")
    token_hash = _digest(token)
    now = _now()
    record = db.query(PasswordResetToken).filter_by(token_hash=token_hash).first()
    user = db.get(Usuario, record.user_id) if record else None
    if (not record or record.expires_at <= now or not user or not user.hashed_password
            or record.password_digest != _digest(user.hashed_password)):
        raise HTTPException(status_code=400, detail=INVALID_LINK_MESSAGE)
    old_hash = user.hashed_password
    new_hash = get_password_hash(password)
    consumed = db.query(PasswordResetToken).filter(
        PasswordResetToken.token_hash == token_hash,
        PasswordResetToken.expires_at > now,
    ).delete(synchronize_session=False)
    changed = db.query(Usuario).filter(
        Usuario.uid == user.uid, Usuario.hashed_password == old_hash,
    ).update({"hashed_password": new_hash}, synchronize_session=False) if consumed else 0
    if not changed:
        db.rollback()
        raise HTTPException(status_code=400, detail=INVALID_LINK_MESSAGE)
    db.commit()
