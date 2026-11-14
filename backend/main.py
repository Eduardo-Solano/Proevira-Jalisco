import logging
from sqlalchemy import text
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.config import settings
from backend.api import (
    system,
    auth,
    predictions,
    alerts,
    clues,
    symptoms,
    dashboard,
    datasets,
)

# Configuración de Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("proevira")

app = FastAPI(
    title=settings.PROJECT_NAME,
    description=(
        "API del Sistema de Vigilancia Epidemiológica y Orientación Ciudadana "
        "(Dengue, Influenza y COVID-19) - Región Centro de Jalisco. "
        "Cumple con NOM-004-SSA3-2012, NOM-017-SSA2-2012 y LFPDPPP."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# Configuración de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rutas públicas directas para healthcheck de infraestructura
app.include_router(system.router, prefix="")
app.include_router(system.router, prefix=settings.API_V1_PREFIX)

# Registro de routers bajo el prefijo maestro /api/v1
app.include_router(auth.router, prefix=settings.API_V1_PREFIX)
app.include_router(predictions.router, prefix=settings.API_V1_PREFIX)
app.include_router(alerts.router, prefix=settings.API_V1_PREFIX)
app.include_router(clues.router, prefix=settings.API_V1_PREFIX)
app.include_router(symptoms.router, prefix=settings.API_V1_PREFIX)
app.include_router(dashboard.router, prefix=settings.API_V1_PREFIX)
app.include_router(datasets.router, prefix=settings.API_V1_PREFIX)

# Registro de rutas de compatibilidad directa (según contrato /auth/*, /predictions/*, etc.)
app.include_router(auth.router, prefix="")
app.include_router(predictions.router, prefix="")
app.include_router(alerts.router, prefix="")
app.include_router(clues.router, prefix="")
app.include_router(symptoms.router, prefix="")
app.include_router(dashboard.router, prefix="")
app.include_router(datasets.router, prefix="")


@app.on_event("startup")
async def on_startup():
    logger.info("Iniciando Proevira Jalisco Backend...")
    # Keep existing SQLite prototypes compatible after adding optional symptom fields.
    from backend.db.database import engine
    if settings.DATABASE_URL.startswith("sqlite"):
        with engine.begin() as connection:
            columns = connection.execute(
                text("PRAGMA table_info(sintomas)")
            ).fetchall()
            if columns and not any(row[1] == "temperatura" for row in columns):
                connection.execute(
                    text("ALTER TABLE sintomas ADD COLUMN temperatura FLOAT")
                )
    from backend.db.models import AlertaPredictivaBorrador, ImportacionDataset
    AlertaPredictivaBorrador.__table__.create(bind=engine, checkfirst=True)
    ImportacionDataset.__table__.create(bind=engine, checkfirst=True)
    logger.info(f"API Documentación disponible en /docs")
