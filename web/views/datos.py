"""Vista de gestión, inventario, importación y calidad de conjuntos de datos."""

from datetime import datetime
import io
from pathlib import Path
import re

import pandas as pd
import streamlit as st

from api_client import DEMO_MODE, ApiError, api

WEB_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = WEB_DIR.parent / "data" / "clean"
ESQUEMAS = {
    "Dengue": ("FECHA_SIGN_SINTOMAS", "MUNICIPIO_RES", "ESTATUS_CASO"),
    "COVID-19": ("FECHA_SINTOMAS", "MUNICIPIO_RES"),
    "Influenza": ("FECHA_SINTOMAS", "MUNICIPIO_RES", "CLASIFICACION_FINAL_FLU"),
}
FECHAS = ("FECHA_SIGN_SINTOMAS", "FECHA_SINTOMAS")
ETIQUETAS_ENFERMEDAD = {"dengue": "Dengue", "covid": "COVID-19", "influenza": "Influenza"}


def _inventario_local() -> pd.DataFrame:
    filas = []
    for archivo in sorted(DATA_DIR.rglob("*")):
        if not archivo.is_file() or archivo.name.endswith(".tmp"):
            continue
        extension = archivo.suffix.lower()
        if extension not in {".csv", ".parquet", ".geojson"}:
            continue
        if extension == ".csv":
            with archivo.open("rb") as fuente:
                registros = max(sum(1 for _ in fuente) - 1, 0)
        else:
            registros = None
        relativo = archivo.relative_to(DATA_DIR)
        carpeta = relativo.parts[0] if len(relativo.parts) > 1 else "General"
        anio = re.search(r"20\d{2}", archivo.name)
        filas.append(
            {
                "Conjunto de datos": archivo.name,
                "Enfermedad / área": carpeta,
                "Fuente": str(relativo.parent) if str(relativo.parent) != "." else "data/clean",
                "Periodo": anio.group(0) if anio else "Multi-año",
                "Registros": registros,
                "Actualización": datetime.fromtimestamp(archivo.stat().st_mtime).strftime("%Y-%m-%d"),
                "Tamaño": f"{archivo.stat().st_size / 1024:.1f} KB",
            }
        )
    return pd.DataFrame(filas)


def _leer_csv_bytes(raw_bytes: bytes) -> pd.DataFrame:
    ultimo_error = None
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            df = pd.read_csv(io.BytesIO(raw_bytes), encoding=encoding)
            df.columns = [str(col).strip() for col in df.columns]
            return df
        except (pd.errors.EmptyDataError, pd.errors.ParserError, UnicodeDecodeError) as error:
            ultimo_error = error
    raise ValueError(str(ultimo_error or "Formato CSV no válido"))


def _validar_columnas(df: pd.DataFrame, enfermedad: str) -> list[str]:
    faltantes = [col for col in ESQUEMAS[enfermedad] if col not in df.columns]
    if enfermedad == "COVID-19":
        if "CLASIFICACION_FINAL_COVID" not in df.columns and "CLASIFICACION_FINAL" not in df.columns:
            faltantes.append("CLASIFICACION_FINAL_COVID (o CLASIFICACION_FINAL)")
    return faltantes


def render_datos_view():
    st.markdown(
        '<div class="page-heading">Gestión de datos</div>'
        '<div class="page-description">Inventario de conjuntos locales, importación al sistema y validación de calidad.</div>',
        unsafe_allow_html=True,
    )

    datasets_api = []
    imports_api = []
    if not DEMO_MODE:
        try:
            payload = api.get_datasets()
            datasets_api = payload.get("datasets", [])
            imports_api = payload.get("imports", [])
        except ApiError:
            datasets_api = []
            imports_api = []

    st.markdown("#### A. Conjuntos de datos")
    if datasets_api:
        inventario = pd.DataFrame(
            [
                {
                    "Conjunto de datos": item.get("nombre"),
                    "Enfermedad / área": item.get("area"),
                    "Fuente": item.get("fuente"),
                    "Periodo": item.get("periodo"),
                    "Registros": item.get("registros"),
                    "Actualización": item.get("actualizado"),
                    "Tamaño": f"{item.get('tamano_kb', 0):.1f} KB",
                }
                for item in datasets_api
            ]
        )
    else:
        inventario = _inventario_local()

    if inventario.empty:
        st.info("No se encontraron conjuntos de datos locales.")
    else:
        st.dataframe(inventario, hide_index=True, use_container_width=True)

    st.markdown("#### B. Importación y vista previa")
    st.caption(
        "Sube un archivo CSV clínico para incorporarlo al conjunto unificado del sistema y actualizar "
        "las series semanales de vigilancia epidemiológica."
    )

    last_import = st.session_state.pop("last_csv_import", None)
    if last_import:
        st.success(
            f"Archivo **{last_import.get('archivo_nombre')}** importado correctamente "
            f"({last_import.get('filas_validas', 0):,} registros confirmados incorporados; "
            f"rango: {last_import.get('rango_fechas') or 'N/D'})."
        )

    col_enf, col_fuente = st.columns(2)
    enfermedad = col_enf.selectbox("Enfermedad del archivo", list(ESQUEMAS), key="data_disease")
    fuente = col_fuente.text_input(
        "Fuente de información",
        key="data_source",
        placeholder="Ej. Secretaría de Salud Jalisco / SINAVE",
    )
    archivo = st.file_uploader("Selecciona un archivo CSV", type=["csv"], key="data_upload")

    datos = None
    validaciones = []
    estructura_valida = False
    raw_bytes = b""
    if archivo is not None:
        raw_bytes = archivo.getvalue()
        try:
            datos = _leer_csv_bytes(raw_bytes)
        except ValueError as error:
            st.error(f"No se pudo leer el CSV: {error}")

        if datos is not None:
            faltantes = _validar_columnas(datos, enfermedad)
            if faltantes:
                validaciones.append(f"Faltan columnas requeridas: {', '.join(faltantes)}.")
                st.warning(f"Faltan columnas requeridas para {enfermedad}: {', '.join(faltantes)}.")
            else:
                estructura_valida = True
                validaciones.append("La estructura contiene las columnas requeridas.")

            fechas = [columna for columna in FECHAS if columna in datos.columns]
            fechas_invalidas = 0
            if fechas:
                fechas_invalidas = int(pd.to_datetime(datos[fechas[0]], errors="coerce").isna().sum())
            validaciones.append(f"Registros totales en el archivo: {len(datos):,}.")
            validaciones.append(f"Fechas inválidas o vacías: {fechas_invalidas:,}.")
            validaciones.append(f"Filas con campos vacíos: {int(datos.isna().any(axis=1).sum()):,}.")
            validaciones.append(f"Filas duplicadas exactas: {int(datos.duplicated().sum()):,}.")

            st.caption(
                f"Vista previa: **{archivo.name}** ({len(datos):,} filas) · "
                f"Fuente declarada: {fuente or 'No especificada'}"
            )
            st.dataframe(datos.head(20), hide_index=True, use_container_width=True)

            if st.button(
                "Importar CSV al sistema",
                type="primary",
                disabled=DEMO_MODE or not estructura_valida or datos.empty,
                key="btn_import_csv",
            ):
                with st.spinner("Validando, consolidando semanas epidemiológicas y recargando el sistema..."):
                    res = api.import_csv(
                        enfermedad=enfermedad,
                        fuente=fuente,
                        filename=archivo.name,
                        file_bytes=raw_bytes,
                    )
                if res.get("success"):
                    st.session_state["last_csv_import"] = res.get("data")
                    st.rerun()
                else:
                    st.error(f"No se pudo importar el archivo: {res.get('error')}")

    st.markdown("#### C. Historial de importaciones")
    if DEMO_MODE:
        st.caption("El historial persistido de importaciones requiere conexión con el backend.")
    elif not imports_api:
        st.caption("Aún no se han registrado importaciones desde el panel.")
    else:
        hist_df = pd.DataFrame(
            [
                {
                    "Archivo": item.get("archivo_nombre"),
                    "Enfermedad": ETIQUETAS_ENFERMEDAD.get(item.get("enfermedad"), item.get("enfermedad")),
                    "Fuente": item.get("fuente") or "No especificada",
                    "Incorporados": item.get("filas_validas"),
                    "Descartados": item.get("filas_descartadas"),
                    "Rango de fechas": item.get("rango_fechas") or "—",
                    "Última semana": item.get("ultima_semana") or "—",
                    "Usuario": item.get("usuario_email") or "—",
                    "Fecha": (item.get("created_at") or "")[:16].replace("T", " "),
                }
                for item in imports_api
            ]
        )
        st.dataframe(hist_df, hide_index=True, use_container_width=True)

    st.markdown("#### D. Calidad de datos")
    if datos is None:
        st.caption("Carga un CSV para revisar estructura, fechas, campos incompletos y duplicados.")
    else:
        for validacion in validaciones:
            st.write(f"• {validacion}")
