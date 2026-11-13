import datetime
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from backend.db.database import Base


class Municipio(Base):
    __tablename__ = "municipios"

    id = Column(String(10), primary_key=True, index=True)  # Clave INEGI p.ej. "14039"
    nombre = Column(String(100), nullable=False)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)

    clues = relationship("Clue", back_populates="municipio_rel")
    predicciones = relationship("Prediccion", back_populates="municipio_rel")
    alertas = relationship("Alerta", back_populates="municipio_rel")


class Clue(Base):
    __tablename__ = "clues"

    clues = Column(String(20), primary_key=True, index=True)  # Clave CLUES
    nombre = Column(String(255), nullable=False)
    institucion = Column(String(100), nullable=True)
    tipo = Column(String(100), nullable=True)
    nivel_atencion = Column(String(50), nullable=True)
    municipio_id = Column(String(10), ForeignKey("municipios.id"), nullable=False, index=True)
    municipio = Column(String(100), nullable=True)
    direccion = Column(String(300), nullable=True)
    telefono = Column(String(50), nullable=True)
    horario = Column(Text, nullable=True)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)

    municipio_rel = relationship("Municipio", back_populates="clues")


class Prediccion(Base):
    __tablename__ = "predicciones"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    municipio_id = Column(String(10), ForeignKey("municipios.id"), nullable=False, index=True)
    semana = Column(String(15), nullable=False, index=True)  # Formato "2026-W20"
    enfermedad = Column(String(20), nullable=False, index=True)  # "dengue", "influenza", "covid"
    casos_esperados = Column(Float, nullable=False)
    nivel_riesgo = Column(String(20), nullable=False)  # "bajo", "medio", "alto", "crítico"
    shap_top3 = Column(Text, nullable=True)  # JSON con [{feature, valor}]
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    municipio_rel = relationship("Municipio", back_populates="predicciones")

    __table_args__ = (
        UniqueConstraint("municipio_id", "semana", "enfermedad", name="uq_prediccion_muni_sem_enf"),
    )


class Alerta(Base):
    __tablename__ = "alertas"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    municipio_id = Column(String(10), ForeignKey("municipios.id"), nullable=True, index=True)
    nivel = Column(String(20), nullable=False)  # "bajo", "medio", "alto", "crítico"
    mensaje = Column(Text, nullable=False)
    activa = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    municipio_rel = relationship("Municipio", back_populates="alertas")


class AlertaPredictivaBorrador(Base):
    __tablename__ = "alertas_predictivas_borrador"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    municipio_id = Column(String(10), ForeignKey("municipios.id"), nullable=False, index=True)
    semana = Column(String(15), nullable=False, index=True)
    enfermedad = Column(String(20), nullable=False, index=True)
    nivel = Column(String(20), nullable=False)
    casos_esperados = Column(Float, nullable=False)
    mensaje = Column(Text, nullable=False)
    estado = Column(String(20), default="pendiente", nullable=False, index=True)
    alerta_id = Column(Integer, ForeignKey("alertas.id"), nullable=True)
    created_at = Column(
        DateTime,
        default=lambda: datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None),
        nullable=False,
    )
    reviewed_at = Column(DateTime, nullable=True)
    reviewed_by = Column(String(128), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "municipio_id",
            "semana",
            "enfermedad",
            name="uq_alerta_predictiva_muni_sem_enf",
        ),
    )


class Usuario(Base):
    __tablename__ = "usuarios"

    uid = Column(String(128), primary_key=True, index=True)  # Firebase UID o UUID
    email = Column(String(150), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=True)  # Respaldo local
    role = Column(String(30), default="paciente", nullable=False)  # "paciente", "medico", "funcionario"
    municipio_id = Column(String(10), ForeignKey("municipios.id"), nullable=True)
    institucion = Column(String(150), nullable=True)
    cedula = Column(String(50), nullable=True)
    verificado = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class Sintoma(Base):
    __tablename__ = "sintomas"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    id_local = Column(String(64), unique=True, index=True, nullable=False)  # UUID generado por cliente móvil
    user_id = Column(String(128), ForeignKey("usuarios.uid"), nullable=True, index=True)
    municipio_id = Column(String(10), ForeignKey("municipios.id"), nullable=True, index=True)
    fiebre = Column(Boolean, default=False)
    cefalea = Column(Boolean, default=False)
    dolor_muscular = Column(Boolean, default=False)
    dolor_articular = Column(Boolean, default=False)
    dolor_retroocular = Column(Boolean, default=False)
    tos = Column(Boolean, default=False)
    dificultad_respiratoria = Column(Boolean, default=False)
    otros_sintomas = Column(Text, nullable=True)
    dias_con_sintomas = Column(Integer, default=1)
    temperatura = Column(Float, nullable=True)
    sospecha_enfermedad = Column(String(30), nullable=True)  # "dengue", "influenza", "covid"
    synced = Column(Boolean, default=True)
    ts_registro = Column(DateTime, default=datetime.datetime.utcnow)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
