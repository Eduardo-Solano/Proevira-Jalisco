from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class LoginRequest(BaseModel):
    email: str
    password: str


class PatientProfileUpdate(BaseModel):
    municipio_id: Optional[str] = None


class LoginResponse(BaseModel):
    token: str
    role: str
    uid: str
    municipio_id: Optional[str] = None
    email: str


class UserProfileResponse(BaseModel):
    uid: str
    email: str
    role: str
    municipio_id: Optional[str] = None
    institucion: Optional[str] = None
    cedula: Optional[str] = None
    verificado: bool


class RegisterPacienteRequest(BaseModel):
    email: str
    password: str
    municipio_id: Optional[str] = None


class RegisterMedicoRequest(BaseModel):
    email: str
    password: str
    institucion: str
    cedula: str
    municipio_id: Optional[str] = None


class RegisterMedicoResponse(BaseModel):
    uid: str
    email: str
    role: str
    verificado: bool
    mensaje: str


class VerifyMedicoResponse(BaseModel):
    uid: str
    email: str
    role: str
    verificado: bool
    mensaje: str


class AdminUserResponse(BaseModel):
    uid: str
    email: str
    role: str
    municipio_id: Optional[str] = None
    institucion: Optional[str] = None
    cedula: Optional[str] = None
    verificado: bool
    created_at: Optional[datetime] = None


class AdminUserCreateRequest(BaseModel):
    email: str
    password: str
    role: str = "medico"
    municipio_id: Optional[str] = None
    institucion: Optional[str] = None
    cedula: Optional[str] = None
    verificado: bool = True


class AdminUserUpdateRequest(BaseModel):
    role: Optional[str] = None
    municipio_id: Optional[str] = None
    institucion: Optional[str] = None
    cedula: Optional[str] = None
    verificado: Optional[bool] = None
    clear_municipio: bool = False
