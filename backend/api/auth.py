import uuid
import datetime
from typing import List, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session
from backend.db.database import get_db
from backend.db.models import Municipio, Sintoma, Usuario
from backend.schemas.auth import (
    ForgotPasswordRequest,
    ResetPasswordRequest,
    PasswordRecoveryResponse,
    VerifyRecoveryCodeRequest,
    VerifyRecoveryCodeResponse,
    LoginRequest,
    LoginResponse,
    UserProfileResponse,
    RegisterPacienteRequest,
    RegisterMedicoRequest,
    RegisterMedicoResponse,
    VerifyMedicoResponse,
    PatientProfileUpdate,
    AdminUserResponse,
    AdminUserCreateRequest,
    AdminUserUpdateRequest,
)
from backend.core.password_recovery import (
    RECOVERY_MESSAGE, ensure_mail_configured, request_password_reset, reset_password, verify_recovery_code,
)
from backend.core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    get_current_user,
    require_roles
)

router = APIRouter(prefix="/auth", tags=["Autenticación"])
ROLES_ADMIN = ["funcionario", "admin", "administrador"]
ROLES_VALIDOS = {"paciente", "medico", "funcionario", "admin", "administrador"}


def _utcnow_naive() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def _validate_email_password(raw_email: str, password: str) -> str:
    email = (raw_email or "").strip().lower()
    if not email or "@" not in email or "." not in email.split("@", 1)[-1]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ingresa un correo electrónico válido",
        )
    if not password or len(password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La contraseña debe tener al menos 6 caracteres",
        )
    return email


def _validate_municipio_id(db: Session, raw_municipio_id: Optional[str]) -> Optional[str]:
    municipio_id = raw_municipio_id.strip() if raw_municipio_id else None
    if not municipio_id:
        return None
    if len(municipio_id) == 3:
        municipio_id = f"14{municipio_id}"
    muni = db.query(Municipio).filter(Municipio.id == municipio_id).first()
    if not muni:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El municipio seleccionado no es válido",
        )
    return municipio_id


def _admin_user_response(user: Usuario) -> AdminUserResponse:
    return AdminUserResponse(
        uid=user.uid,
        email=user.email,
        role=user.role,
        municipio_id=user.municipio_id,
        institucion=user.institucion,
        cedula=user.cedula,
        verificado=user.verificado,
        created_at=user.created_at,
    )


def _build_login_response(user: Usuario) -> LoginResponse:
    """Genera el JWT y la respuesta estándar de sesión para un usuario."""
    token_data = {
        "sub": user.uid,
        "uid": user.uid,
        "email": user.email,
        "role": user.role,
        "municipio_id": user.municipio_id,
        "verificado": user.verificado,
    }
    access_token = create_access_token(token_data)
    return LoginResponse(
        token=access_token,
        role=user.role,
        uid=user.uid,
        municipio_id=user.municipio_id,
        email=user.email,
    )


@router.post("/login", response_model=LoginResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)):
    """
    Valida credenciales y genera un token JWT con el rol y municipio del usuario.
    """
    normalized_email = request.email.strip().lower()
    user = db.query(Usuario).filter(func.lower(Usuario.email) == normalized_email).first()
    if not user or not user.hashed_password or not verify_password(request.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return _build_login_response(user)


@router.post("/forgot-password", response_model=PasswordRecoveryResponse, status_code=202)
def forgot_password(request: ForgotPasswordRequest, background_tasks: BackgroundTasks):
    email = request.email.strip().lower()
    if "@" not in email or "." not in email.split("@", 1)[-1] or any(c.isspace() for c in email):
        raise HTTPException(status_code=400, detail="Ingresa un correo electrónico válido.")
    ensure_mail_configured()
    background_tasks.add_task(request_password_reset, email)
    return {"message": RECOVERY_MESSAGE}


@router.post("/reset-password", response_model=PasswordRecoveryResponse)
def confirm_password_reset(request: ResetPasswordRequest, db: Session = Depends(get_db)):
    reset_password(db, request.token, request.password)
    return {"message": "Tu contraseña fue actualizada. Ya puedes iniciar sesión."}


@router.post("/verify-recovery-code", response_model=VerifyRecoveryCodeResponse)
def confirm_recovery_code(request: VerifyRecoveryCodeRequest, db: Session = Depends(get_db)):
    token = verify_recovery_code(db, request.email.strip().lower(), request.code)
    return {"reset_token": token}


@router.get("/me", response_model=UserProfileResponse)
def get_me(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Obtiene el perfil del usuario autenticado.
    """
    uid = current_user.get("uid") or current_user.get("sub")
    user = db.query(Usuario).filter(Usuario.uid == uid).first()

    if not user:
        # Si fue autenticado externamente por Firebase
        return UserProfileResponse(
            uid=str(uid),
            email=current_user.get("email", ""),
            role=current_user.get("role", "paciente"),
            municipio_id=current_user.get("municipio_id"),
            institucion=None,
            cedula=None,
            verificado=current_user.get("verificado", True)
        )
    return UserProfileResponse(
        uid=user.uid,
        email=user.email,
        role=user.role,
        municipio_id=user.municipio_id,
        institucion=user.institucion,
        cedula=user.cedula,
        verificado=user.verificado
    )


@router.patch("/me", response_model=UserProfileResponse)
def update_patient_profile(
    request: PatientProfileUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    uid = current_user.get("uid") or current_user.get("sub")
    user = db.query(Usuario).filter(Usuario.uid == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="Perfil no encontrado")
    if user.role != "paciente":
        raise HTTPException(
            status_code=403,
            detail="Solo los pacientes pueden actualizar este perfil",
        )
    user.municipio_id = request.municipio_id
    db.commit()
    db.refresh(user)
    return UserProfileResponse(
        uid=user.uid,
        email=user.email,
        role=user.role,
        municipio_id=user.municipio_id,
        institucion=user.institucion,
        cedula=user.cedula,
        verificado=user.verificado
    )


@router.post("/register-paciente", response_model=LoginResponse, status_code=status.HTTP_201_CREATED)
def register_paciente(request: RegisterPacienteRequest, db: Session = Depends(get_db)):
    """
    Registro público de pacientes para la app móvil.
    Crea la cuenta verificada con rol 'paciente' y devuelve la sesión JWT activa.
    """
    email = _validate_email_password(request.email, request.password)

    existing = db.query(Usuario).filter(func.lower(Usuario.email) == email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El correo electrónico ya se encuentra registrado",
        )

    municipio_id = _validate_municipio_id(db, request.municipio_id)

    uid = f"pac_{uuid.uuid4().hex[:12]}"
    new_paciente = Usuario(
        uid=uid,
        email=email,
        hashed_password=get_password_hash(request.password),
        role="paciente",
        municipio_id=municipio_id,
        verificado=True,
        created_at=_utcnow_naive(),
    )
    db.add(new_paciente)
    db.commit()
    db.refresh(new_paciente)

    return _build_login_response(new_paciente)


@router.post("/register-medico", response_model=RegisterMedicoResponse)
def register_medico(request: RegisterMedicoRequest, db: Session = Depends(get_db)):
    """
    Registro público de médicos. Se crea en estado verificado = False
    hasta que un funcionario gubernamental apruebe su cédula.
    """
    existing = db.query(Usuario).filter(Usuario.email == request.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El correo electrónico ya se encuentra registrado"
        )

    uid = f"med_{uuid.uuid4().hex[:12]}"
    new_medico = Usuario(
        uid=uid,
        email=request.email,
        hashed_password=get_password_hash(request.password),
        role="medico",
        municipio_id=request.municipio_id,
        institucion=request.institucion,
        cedula=request.cedula,
        verificado=False,
        created_at=datetime.datetime.utcnow()
    )
    db.add(new_medico)
    db.commit()

    return RegisterMedicoResponse(
        uid=uid,
        email=request.email,
        role="medico",
        verificado=False,
        mensaje="Registro exitoso. Tu cuenta está en proceso de validación por la Secretaría de Salud."
    )


@router.post("/verify-medico/{uid}", response_model=VerifyMedicoResponse)
def verify_medico(
    uid: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_roles(ROLES_ADMIN))
):
    """
    Aprueba y activa a un médico registrado (Exclusivo para administradores/funcionarios).
    """
    user = db.query(Usuario).filter(Usuario.uid == uid).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")

    if user.role != "medico":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El usuario no tiene rol de médico")

    user.verificado = True
    db.commit()

    return VerifyMedicoResponse(
        uid=user.uid,
        email=user.email,
        role=user.role,
        verificado=True,
        mensaje=f"Médico {user.email} verificado correctamente"
    )


@router.get("/users", response_model=List[AdminUserResponse])
def list_users_admin(
    role: Optional[str] = Query(None, description="Filtrar por rol"),
    verificado: Optional[bool] = Query(None, description="Filtrar por verificación"),
    search: Optional[str] = Query(None, description="Buscar por correo, cédula o institución"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_roles(ROLES_ADMIN)),
):
    """Lista las cuentas registradas para el panel administrativo."""
    query = db.query(Usuario)
    if role:
        query = query.filter(func.lower(Usuario.role) == role.strip().lower())
    if verificado is not None:
        query = query.filter(Usuario.verificado == verificado)
    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        query = query.filter(
            or_(
                func.lower(Usuario.email).like(term),
                func.lower(func.coalesce(Usuario.cedula, "")).like(term),
                func.lower(func.coalesce(Usuario.institucion, "")).like(term),
            )
        )

    users = query.order_by(Usuario.verificado.asc(), Usuario.created_at.desc()).all()
    return [_admin_user_response(u) for u in users]


@router.post("/users", response_model=AdminUserResponse, status_code=status.HTTP_201_CREATED)
def create_user_admin(
    request: AdminUserCreateRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_roles(ROLES_ADMIN)),
):
    """Crea un usuario directamente desde el panel administrativo."""
    email = _validate_email_password(request.email, request.password)
    role_norm = (request.role or "").strip().lower()
    if role_norm not in ROLES_VALIDOS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Rol no válido. Usa paciente, medico o funcionario.",
        )

    existing = db.query(Usuario).filter(func.lower(Usuario.email) == email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El correo electrónico ya se encuentra registrado",
        )

    municipio_id = _validate_municipio_id(db, request.municipio_id)
    prefix = "med" if role_norm == "medico" else ("pac" if role_norm == "paciente" else "func")
    new_user = Usuario(
        uid=f"{prefix}_{uuid.uuid4().hex[:12]}",
        email=email,
        hashed_password=get_password_hash(request.password),
        role=role_norm,
        municipio_id=municipio_id,
        institucion=request.institucion.strip() if request.institucion else None,
        cedula=request.cedula.strip() if request.cedula else None,
        verificado=bool(request.verificado),
        created_at=_utcnow_naive(),
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return _admin_user_response(new_user)


@router.patch("/users/{uid}", response_model=AdminUserResponse)
def update_user_admin(
    uid: str,
    request: AdminUserUpdateRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_roles(ROLES_ADMIN)),
):
    """Actualiza rol, verificación, municipio o datos institucionales de un usuario."""
    user = db.query(Usuario).filter(Usuario.uid == uid).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")

    current_uid = current_user.get("uid") or current_user.get("sub")

    if request.role is not None:
        role_norm = request.role.strip().lower()
        if role_norm not in ROLES_VALIDOS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Rol no válido")
        if uid == current_uid and role_norm not in ROLES_ADMIN:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No puedes quitarte el rol de administrador a tu propia cuenta",
            )
        user.role = role_norm

    if request.clear_municipio:
        user.municipio_id = None
    elif request.municipio_id is not None:
        user.municipio_id = _validate_municipio_id(db, request.municipio_id)

    if request.institucion is not None:
        user.institucion = request.institucion.strip() or None
    if request.cedula is not None:
        user.cedula = request.cedula.strip() or None
    if request.verificado is not None:
        user.verificado = bool(request.verificado)

    db.commit()
    db.refresh(user)
    return _admin_user_response(user)


@router.delete("/users/{uid}")
def delete_user_admin(
    uid: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_roles(ROLES_ADMIN)),
):
    """Elimina un usuario del sistema preservando registros anónimos de síntomas."""
    current_uid = current_user.get("uid") or current_user.get("sub")
    if uid == current_uid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes eliminar tu propia cuenta activa",
        )

    user = db.query(Usuario).filter(Usuario.uid == uid).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")

    db.query(Sintoma).filter(Sintoma.user_id == uid).update({"user_id": None})
    db.delete(user)
    db.commit()
    return {"uid": uid, "eliminado": True}

