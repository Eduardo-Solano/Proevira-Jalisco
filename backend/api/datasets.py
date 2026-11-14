from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
import pandas as pd
from sqlalchemy.orm import Session

from backend.config import settings
from backend.core.inference import inference_engine
from backend.core.security import require_roles
from backend.db.database import get_db
from backend.db.models import ImportacionDataset, Municipio, Prediccion
from scripts import limpieza

router = APIRouter(prefix="/datasets", tags=["Datos"])

MAX_CSV_BYTES = 50 * 1024 * 1024
CONFIRMED_CODES = {"1", "2", "3"}
MUNICIPIOS_CENTRO = {
    "14029": "CUQUÍO",
    "14039": "GUADALAJARA",
    "14044": "IXTLAHUACÁN DE LOS MEMBRILLOS",
    "14045": "IXTLAHUACÁN DEL RÍO",
    "14051": "JUANACATLÁN",
    "14070": "EL SALTO",
    "14071": "SAN CRISTÓBAL DE LA BARRANCA",
    "14097": "TLAJOMULCO DE ZÚÑIGA",
    "14098": "SAN PEDRO TLAQUEPAQUE",
    "14101": "TONALÁ",
    "14120": "ZAPOPAN",
    "14124": "ZAPOTLANEJO",
}


def _normalize_enfermedad(valor: str) -> str:
    enf = (valor or "").strip().lower()
    if enf in {"covid-19", "covid19", "covid"}:
        return "covid"
    if enf in {"dengue", "influenza"}:
        return enf
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Enfermedad inválida. Valores permitidos: Dengue, COVID-19 o Influenza.",
    )


def _normalize_code_series(series: pd.Series) -> pd.Series:
    return (
        series.fillna("")
        .astype(str)
        .str.strip()
        .str.replace(r"\.0+$", "", regex=True)
    )


def _safe_muni_id(value: Any) -> str:
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", ""}:
        return ""
    try:
        return limpieza.muni_id(text)
    except (TypeError, ValueError):
        return ""


def _read_uploaded_csv(raw_bytes: bytes) -> pd.DataFrame:
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="El archivo CSV está vacío.")
    if len(raw_bytes) > MAX_CSV_BYTES:
        raise HTTPException(status_code=413, detail="El archivo excede el límite permitido de 50 MB.")

    last_error = None
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            df = pd.read_csv(io.BytesIO(raw_bytes), dtype=str, encoding=encoding)
            if df.empty:
                raise HTTPException(status_code=400, detail="El archivo CSV no contiene registros.")
            df.columns = [str(col).strip() for col in df.columns]
            return df
        except HTTPException:
            raise
        except (pd.errors.EmptyDataError, pd.errors.ParserError, UnicodeDecodeError) as exc:
            last_error = exc
    raise HTTPException(status_code=400, detail=f"No se pudo leer el archivo CSV: {last_error}")


def _prepare_dengue_df(df: pd.DataFrame, muni_names: Dict[str, str], batch_tag: str) -> pd.DataFrame:
    required = ("FECHA_SIGN_SINTOMAS", "MUNICIPIO_RES", "ESTATUS_CASO")
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Faltan columnas requeridas para Dengue: {', '.join(missing)}.",
        )

    muni_ids = df["MUNICIPIO_RES"].map(_safe_muni_id)
    fechas = pd.to_datetime(df["FECHA_SIGN_SINTOMAS"], errors="coerce")
    estatus = _normalize_code_series(df["ESTATUS_CASO"])
    mask = muni_ids.isin(MUNICIPIOS_CENTRO) & fechas.notna() & estatus.isin(CONFIRMED_CODES)
    if not mask.any():
        return pd.DataFrame()

    valid = df.loc[mask].copy()
    valid_muni = muni_ids.loc[mask]
    valid_dates = fechas.loc[mask].dt.strftime("%Y-%m-%d")

    if "ID_REGISTRO" in valid.columns:
        ids = valid["ID_REGISTRO"].fillna("").astype(str).str.strip()
        generated = pd.Series(
            [f"IMP-{batch_tag}-{idx}" for idx in range(len(valid))],
            index=valid.index,
        )
        ids = ids.where(ids != "", generated)
    else:
        ids = pd.Series(
            [f"IMP-{batch_tag}-{idx}" for idx in range(len(valid))],
            index=valid.index,
        )

    muni_col = (
        valid["MUNICIPIO"].fillna("").astype(str).str.strip().str.upper()
        if "MUNICIPIO" in valid.columns
        else pd.Series("", index=valid.index)
    )
    fallback_names = valid_muni.map(muni_names)
    muni_col = muni_col.where(muni_col != "", fallback_names)

    edad_col = (
        pd.to_numeric(valid["EDAD_ANOS"], errors="coerce").fillna("").astype(str)
        if "EDAD_ANOS" in valid.columns
        else pd.Series("", index=valid.index)
    )
    defuncion_col = (
        _normalize_code_series(valid["DEFUNCION"])
        if "DEFUNCION" in valid.columns
        else pd.Series("2", index=valid.index)
    )

    return pd.DataFrame(
        {
            "ID_REGISTRO": ids,
            "FECHA_SIGN_SINTOMAS": valid_dates,
            "MUNICIPIO_RES": valid_muni.str[-3:],
            "MUNICIPIO": muni_col,
            "EDAD_ANOS": edad_col,
            "ESTATUS_CASO": estatus.loc[mask],
            "DEFUNCION": defuncion_col,
        }
    )


def _prepare_respiratory_df(
    df: pd.DataFrame,
    enfermedad: str,
    muni_names: Dict[str, str],
) -> pd.DataFrame:
    base_required = ("FECHA_SINTOMAS", "MUNICIPIO_RES")
    missing = [col for col in base_required if col not in df.columns]
    if enfermedad == "covid":
        if "CLASIFICACION_FINAL_COVID" not in df.columns and "CLASIFICACION_FINAL" not in df.columns:
            missing.append("CLASIFICACION_FINAL_COVID")
    elif "CLASIFICACION_FINAL_FLU" not in df.columns:
        missing.append("CLASIFICACION_FINAL_FLU")

    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Faltan columnas requeridas para {enfermedad.upper()}: {', '.join(missing)}.",
        )

    muni_ids = df["MUNICIPIO_RES"].map(_safe_muni_id)
    fechas = pd.to_datetime(df["FECHA_SINTOMAS"], errors="coerce")

    if enfermedad == "covid":
        clas_raw = (
            df["CLASIFICACION_FINAL_COVID"].fillna(df["CLASIFICACION_FINAL"])
            if "CLASIFICACION_FINAL_COVID" in df.columns and "CLASIFICACION_FINAL" in df.columns
            else df.get("CLASIFICACION_FINAL_COVID", df.get("CLASIFICACION_FINAL"))
        )
        clas_norm = _normalize_code_series(clas_raw)
    else:
        clas_norm = _normalize_code_series(df["CLASIFICACION_FINAL_FLU"])

    mask = muni_ids.isin(MUNICIPIOS_CENTRO) & fechas.notna() & clas_norm.isin(CONFIRMED_CODES)
    if not mask.any():
        return pd.DataFrame()

    valid = df.loc[mask].copy()
    valid_muni = muni_ids.loc[mask]
    valid_dates = fechas.loc[mask].dt.strftime("%Y-%m-%d")

    muni_col = (
        valid["MUNICIPIO_NOMBRE"].fillna("").astype(str).str.strip().str.upper()
        if "MUNICIPIO_NOMBRE" in valid.columns
        else pd.Series("", index=valid.index)
    )
    fallback_names = valid_muni.map(muni_names)
    muni_col = muni_col.where(muni_col != "", fallback_names)

    edad_col = (
        pd.to_numeric(valid["EDAD"], errors="coerce").fillna("").astype(str)
        if "EDAD" in valid.columns
        else pd.Series("", index=valid.index)
    )

    return pd.DataFrame(
        {
            "MUNICIPIO_RES": valid_muni.str[-3:],
            "MUNICIPIO_NOMBRE": muni_col,
            "EDAD": edad_col,
            "FECHA_SINTOMAS": valid_dates,
            "CLASIFICACION_FINAL": pd.Series("", index=valid.index),
            "CLASIFICACION_FINAL_COVID": clas_norm.loc[mask] if enfermedad == "covid" else pd.Series("", index=valid.index),
            "CLASIFICACION_FINAL_FLU": clas_norm.loc[mask] if enfermedad == "influenza" else pd.Series("", index=valid.index),
        }
    )


def _list_clean_datasets() -> List[Dict[str, Any]]:
    clean_dir = Path(settings.CLEAN_DATA_DIR)
    if not clean_dir.exists():
        return []

    rows: List[Dict[str, Any]] = []
    for file_path in sorted(clean_dir.rglob("*")):
        if not file_path.is_file() or file_path.name.endswith(".tmp"):
            continue
        ext = file_path.suffix.lower()
        if ext not in {".csv", ".parquet", ".geojson"}:
            continue
        records = None
        if ext == ".csv":
            with file_path.open("rb") as handle:
                records = max(sum(1 for _ in handle) - 1, 0)
        rel = file_path.relative_to(clean_dir)
        area = rel.parts[0] if len(rel.parts) > 1 else "General"
        year_match = re.search(r"20\d{2}", file_path.name)
        rows.append(
            {
                "nombre": file_path.name,
                "area": area,
                "fuente": str(rel.parent) if str(rel.parent) != "." else "data/clean",
                "periodo": year_match.group(0) if year_match else "Multi-año",
                "registros": records,
                "actualizado": datetime.fromtimestamp(file_path.stat().st_mtime).strftime("%Y-%m-%d"),
                "tamano_kb": round(file_path.stat().st_size / 1024, 1),
            }
        )
    return rows


def _serialize_import(row: ImportacionDataset) -> Dict[str, Any]:
    return {
        "id": row.id,
        "archivo_nombre": row.archivo_nombre,
        "enfermedad": row.enfermedad,
        "fuente": row.fuente,
        "filas_totales": row.filas_totales,
        "filas_validas": row.filas_validas,
        "filas_descartadas": row.filas_descartadas,
        "rango_fechas": row.rango_fechas,
        "ultima_semana": row.ultima_semana,
        "usuario_email": row.usuario_email,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _sync_predictions_cache(db: Session, enfermedad: str) -> None:
    db.query(Prediccion).filter(Prediccion.enfermedad == enfermedad).delete(synchronize_session=False)
    for item in inference_engine.predict_bulk(enfermedad=enfermedad):
        db.add(
            Prediccion(
                municipio_id=item["municipio"],
                semana=item["semana"],
                enfermedad=enfermedad,
                casos_esperados=item["casos_esperados"],
                nivel_riesgo=item["nivel_riesgo"],
                shap_top3=json.dumps(item.get("shap_top3", []), ensure_ascii=False),
            )
        )


@router.get("")
def list_datasets(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_roles(["funcionario", "medico"])),
):
    """Lista los conjuntos locales disponibles y el historial persistido de importaciones."""
    imports = (
        db.query(ImportacionDataset)
        .order_by(ImportacionDataset.created_at.desc(), ImportacionDataset.id.desc())
        .limit(50)
        .all()
    )
    return {
        "datasets": _list_clean_datasets(),
        "imports": [_serialize_import(row) for row in imports],
    }


@router.post("/import", status_code=status.HTTP_201_CREATED)
async def import_csv_dataset(
    enfermedad: str = Form(...),
    fuente: str = Form(""),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_roles(["funcionario", "medico"])),
):
    """Valida, guarda e incorpora un archivo CSV clínico en el conjunto unificado del sistema."""
    enf_norm = _normalize_enfermedad(enfermedad)
    raw_bytes = await file.read()
    file_hash = hashlib.sha256(raw_bytes).hexdigest()

    existing = (
        db.query(ImportacionDataset)
        .filter(
            ImportacionDataset.archivo_hash == file_hash,
            ImportacionDataset.enfermedad == enf_norm,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Este archivo ya fue importado anteriormente como '{existing.archivo_nombre}' "
                f"el {existing.created_at.strftime('%Y-%m-%d %H:%M')}."
            ),
        )

    df_raw = _read_uploaded_csv(raw_bytes)
    filas_totales = int(len(df_raw))

    muni_names = dict(MUNICIPIOS_CENTRO)
    for mun in db.query(Municipio).all():
        if mun.id and mun.nombre:
            muni_names[str(mun.id).zfill(5)] = mun.nombre.strip().upper()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    if enf_norm == "dengue":
        prepared = _prepare_dengue_df(df_raw, muni_names, stamp)
        target_subdir = "dengue"
        date_col = "FECHA_SIGN_SINTOMAS"
    else:
        prepared = _prepare_respiratory_df(df_raw, enf_norm, muni_names)
        target_subdir = "datos_covid_influenza"
        date_col = "FECHA_SINTOMAS"

    filas_validas = int(len(prepared))
    filas_descartadas = filas_totales - filas_validas
    if filas_validas == 0:
        raise HTTPException(
            status_code=400,
            detail=(
                "No se encontraron registros confirmados válidos para los 12 municipios de la Región Centro "
                "(revisa municipio, fecha de síntomas y código de confirmación 1, 2 o 3)."
            ),
        )

    clean_root = Path(settings.CLEAN_DATA_DIR)
    dest_dir = clean_root / target_subdir
    dest_dir.mkdir(parents=True, exist_ok=True)
    base_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(file.filename or "dataset.csv").stem).strip("_") or "dataset"
    dest_path = dest_dir / f"import_{stamp}_{base_stem}.csv"
    unified_path = clean_root / "casos_municipio_semana.csv"
    unified_tmp = clean_root / "casos_municipio_semana.csv.tmp"

    try:
        prepared.to_csv(dest_path, index=False, encoding="utf-8-sig")
        limpieza.CLEAN = str(clean_root)
        unified_df = limpieza.casos_municipio_semana()
        unified_df.to_csv(unified_tmp, index=False, encoding="utf-8")
        os.replace(unified_tmp, unified_path)
        inference_engine.reload()
        _sync_predictions_cache(db, enf_norm)
    except HTTPException:
        dest_path.unlink(missing_ok=True)
        unified_tmp.unlink(missing_ok=True)
        raise
    except Exception as exc:
        dest_path.unlink(missing_ok=True)
        unified_tmp.unlink(missing_ok=True)
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error al consolidar los datos importados en el sistema: {exc}",
        ) from exc

    fechas_validas = pd.to_datetime(prepared[date_col], errors="coerce").dropna()
    rango_fechas = (
        f"{fechas_validas.min().strftime('%Y-%m-%d')} → {fechas_validas.max().strftime('%Y-%m-%d')}"
        if not fechas_validas.empty
        else None
    )
    ultima_semana = None
    if not fechas_validas.empty:
        iso_max = fechas_validas.max().isocalendar()
        ultima_semana = f"{iso_max.year}-W{iso_max.week:02d}"

    record = ImportacionDataset(
        archivo_nombre=Path(file.filename or dest_path.name).name,
        archivo_hash=file_hash,
        enfermedad=enf_norm,
        fuente=(fuente or "").strip() or "Carga manual en panel web",
        ruta_guardada=str(dest_path.relative_to(clean_root)),
        filas_totales=filas_totales,
        filas_validas=filas_validas,
        filas_descartadas=filas_descartadas,
        rango_fechas=rango_fechas,
        ultima_semana=ultima_semana,
        usuario_email=current_user.get("email"),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return _serialize_import(record)
