from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from backend.config import settings


def normalize_database_url(url: str) -> str:
    """Normaliza URLs postgres:// entregadas por proveedores cloud a postgresql://."""
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://"):]
    return url


database_url = normalize_database_url(settings.DATABASE_URL)

connect_args = {}
if database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    database_url,
    connect_args=connect_args,
    pool_pre_ping=True,
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """Dependencia de FastAPI para obtener la sesión de base de datos."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

