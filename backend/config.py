import os
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Proyecto
    PROJECT_NAME: str = "Proevira Jalisco - Sistema de Vigilancia Epidemiológica"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = True

    # Base de datos
    DATABASE_URL: str = "sqlite:///./proevira.db"

    # Seguridad / JWT
    JWT_SECRET_KEY: str = "proevira_secret_key_change_me_in_production_12345678"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 horas

    # Firebase Authentication
    FIREBASE_CREDENTIALS_PATH: Optional[str] = None
    FIREBASE_PROJECT_ID: Optional[str] = None

    # CORS
    CORS_ORIGINS: List[str] = ["*"]

    # Rutas base
    BASE_DIR: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    MODEL_ARTIFACTS_DIR: str = os.path.join(BASE_DIR, "model", "artifacts")
    CLEAN_DATA_DIR: str = os.path.join(BASE_DIR, "data", "clean")

    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()

