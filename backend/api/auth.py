import uuid
import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from backend.db.database import get_db
from backend.db.models import Usuario
from backend.schemas.auth import (
    LoginRequest,
    LoginResponse,
    UserProfileResponse,
    RegisterMedicoRequest,
    RegisterMedicoResponse,
    VerifyMedicoResponse,
    PatientProfileUpdate,
)
from backend.core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    get_current_user,
    require_roles
)

router = APIRouter(prefix="/auth", tags=["Autenticación"])


@router.post("/login", response_model=LoginResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)):
    """
    Valida credenciales y genera un token JWT con el rol y municipio del usuario.
    """
    user = db.query(Usuario).filter(Usuario.email == request.email).first()
    if not user or not user.hashed_password or not verify_password(request.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Crear token JWT
    token_data = {
        "sub": user.uid,
        "uid": user.uid,
        "email": user.email,
        "role": user.role,
        "municipio_id": user.municipio_id,
        "verificado": user.verificado
    }
    access_token = create_access_token(token_data)

    return LoginResponse(
        token=access_token,
        role=user.role,
        uid=user.uid,
        municipio_id=user.municipio_id,
        email=user.email
    )


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
    current_user: dict = Depends(require_roles(["funcionario"]))
):
    """
    Aprueba y activa a un médico registrado (Exclusivo para rol funcionario).
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

