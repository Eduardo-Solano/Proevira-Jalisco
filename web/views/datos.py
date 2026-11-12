"""Vista de inventario local y validación preliminar de archivos."""

from datetime import datetime
from pathlib import Path
import re

import pandas as pd
import streamlit as st

WEB_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = WEB_DIR.parent / "data" / "clean"
ESQUEMAS = {
    "Dengue": ("FECHA_SIGN_SINTOMAS", "MUNICIPIO_RES", "ESTATUS_CASO"),
    "COVID-19": ("FECHA_SINTOMAS", "MUNICIPIO_RES", "CLASIFICACION_FINAL_COVID"),
    "Influenza": ("FECHA_SINTOMAS", "MUNICIPIO_RES", "CLASIFICACION_FINAL_FLU"),
}
FECHAS = ("FECHA_SIGN_SINTOMAS", "FECHA_SINTOMAS")


def _inventario() -> pd.DataFrame:
    filas = []
    for archivo in sorted(DATA_DIR.rglob("*")):
        if not archivo.is_file():
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
                "Periodo": anio.group(0) if anio else "No especificado",
                "Registros": registros,
                "Actualización local": datetime.fromtimestamp(archivo.stat().st_mtime).strftime("%Y-%m-%d"),
                "Tamaño": f"{archivo.stat().st_size / 1024:.1f} KB",
            }
        )
    return pd.DataFrame(filas)


def render_datos_view():
    st.markdown(
        '<div class="page-heading">Gestión de datos</div>'
        '<div class="page-description">Inventario de conjuntos locales y revisión preliminar de archivos.</div>',
        unsafe_allow_html=True,
    )

    st.markdown("#### A. Conjuntos de datos")
    inventario = _inventario()
    if inventario.empty:
        st.info("No se encontraron conjuntos de datos locales.")
    else:
        st.dataframe(inventario, hide_index=True, use_container_width=True)

    st.markdown("#### B. Importación y vista previa")
    st.info(
        "La API actual no cuenta con una operación de importación. "
        "Puedes validar y previsualizar un CSV aquí; el archivo no se guarda ni se incorpora al sistema."
    )
    enfermedad = st.selectbox("Enfermedad del archivo", list(ESQUEMAS), key="data_disease")
    st.text_input("Fuente de información", key="data_source", placeholder="Nombre de la institución o fuente")
    archivo = st.file_uploader("Selecciona un archivo CSV", type=["csv"], key="data_upload")
    datos = None
    validaciones = []
    if archivo is not None:
        try:
            datos = pd.read_csv(archivo)
        except (pd.errors.EmptyDataError, pd.errors.ParserError, UnicodeDecodeError) as error:
            st.error(f"No se pudo leer el CSV: {error}")
        if datos is not None:
            requeridas = ESQUEMAS[enfermedad]
            faltantes = [columna for columna in requeridas if columna not in datos.columns]
            if faltantes:
                validaciones.append(f"Faltan columnas requeridas: {', '.join(faltantes)}.")
            else:
                validaciones.append("La estructura contiene las columnas requeridas.")
            fechas = [columna for columna in FECHAS if columna in datos.columns]
            fechas_invalidas = 0
            if fechas:
                fechas_invalidas = int(pd.to_datetime(datos[fechas[0]], errors="coerce").isna().sum())
            validaciones.append(f"Fechas inválidas: {fechas_invalidas:,}.")
            validaciones.append(f"Filas con campos vacíos: {int(datos.isna().any(axis=1).sum()):,}.")
            validaciones.append(f"Filas duplicadas: {int(datos.duplicated().sum()):,}.")
            st.caption(f"Archivo: {archivo.name} · Fuente declarada: {st.session_state.get('data_source') or 'No especificada'}")
            st.dataframe(datos.head(20), hide_index=True, use_container_width=True)

    st.markdown("#### C. Historial de importaciones")
    st.caption("No hay historial disponible: esta interfaz no persiste importaciones y el backend no expone ese registro.")

    st.markdown("#### D. Calidad de datos")
    if datos is None:
        st.caption("Carga un CSV para revisar estructura, fechas, campos incompletos y duplicados.")
    else:
        for validacion in validaciones:
            st.write(f"• {validacion}")
