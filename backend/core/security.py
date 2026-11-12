import os
import datetime
from typing import Optional, List, Dict, Any
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
import bcrypt
from backend.config import settings

# Esquema de autenticación Bearer
security_bearer = HTTPBearer(auto_error=False)

# Inicialización segura de Firebase Admin SDK
firebase_initialized = False
try:
    import firebase_admin
    from firebase_admin import credentials, auth as firebase_auth

    if not firebase_admin._apps:
        cred_path = settings.FIREBASE_CREDENTIALS_PATH
        if cred_path and os.path.exists(cred_path):
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
            firebase_initialized = True
        elif settings.FIREBASE_PROJECT_ID:
            firebase_admin.initialize_app(options={"projectId": settings.FIREBASE_PROJECT_ID})
            firebase_initialized = True
        else:
            try:
                firebase_admin.initialize_app()
                firebase_initialized = True
            except Exception:
                firebase_initialized = False
except Exception:
    firebase_initialized = False

# Contexto de contraseñas directo con bcrypt
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica si una contraseña en texto plano coincide con el hash."""
    if not hashed_password or not plain_password:
        return False
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    """Genera hash seguro de una contraseña usando bcrypt."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def create_access_token(data: dict, expires_delta: Optional[datetime.timedelta] = None) -> str:
    """Crea un token JWT propio firmado con la clave secreta del backend."""
    to_encode = data.copy()
    expire = datetime.datetime.utcnow() + (
        expires_delta if expires_delta else datetime.timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> Dict[str, Any]:
    """
    Decodifica y valida un token. Primero intenta validar como token de Firebase
    (si está configurado) y si falla, valida con el JWT local del backend.
    """
    # 1. Intentar con Firebase Authentication si está inicializado
    if firebase_initialized:
        try:
            from firebase_admin import auth as fb_auth
            decoded_firebase = fb_auth.verify_id_token(token)
            return {
                "uid": decoded_firebase.get("uid"),
                "email": decoded_firebase.get("email"),
                "role": decoded_firebase.get("role", "paciente"),
                "municipio_id": decoded_firebase.get("municipio_id"),
                "verificado": decoded_firebase.get("verificado", True),
                "is_firebase": True,
            }
        except Exception:
            pass

    # 2. Intentar como JWT local firmado
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer)) -> Dict[str, Any]:
    """Extrae el usuario autenticado del encabezado Authorization: Bearer <token>."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Se requiere encabezado Authorization: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return decode_token(credentials.credentials)


def require_roles(allowed_roles: List[str]):
    """Dependencia de RBAC para restringir endpoints según roles de usuario."""
    def role_checker(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        user_role = current_user.get("role", "paciente")
        if user_role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permiso denegado. Se requiere uno de los roles: {allowed_roles}"
            )
        # Si es médico, verificar que esté aprobado
        if user_role == "medico" and not current_user.get("verificado", True):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cuenta médica pendiente de verificación por un funcionario"
            )
        return current_user
    return role_checker
