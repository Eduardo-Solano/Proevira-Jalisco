from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class ForgotPasswordRequest(BaseModel):
    email: str = Field(min_length=3, max_length=150)


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=40, max_length=128)
    password: str = Field(min_length=8, max_length=72)


class VerifyRecoveryCodeRequest(BaseModel):
    email: str = Field(min_length=3, max_length=150)
    code: str = Field(pattern=r"^[0-9]{6}$")


class VerifyRecoveryCodeResponse(BaseModel):
    reset_token: str


class PasswordRecoveryResponse(BaseModel):
    message: str


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
