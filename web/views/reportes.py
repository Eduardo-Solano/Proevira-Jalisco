"""Vista de consulta y exportación de reportes existentes."""

import pandas as pd
import streamlit as st

from api_client import DEMO_MODE, MUNICIPIOS_JALISCO, api

TIPOS_REPORTE = {
    "Evolución epidemiológica": "evolucion",
    "Comparativo entre enfermedades": "comparativo",
    "Distribución geográfica": "geografico",
    "Resultados predictivos": "predictivo",
}


def _reporte(tipo: str, enfermedad: str, municipio: str | None, periodo: str) -> pd.DataFrame:
    if tipo == "geografico":
        datos = pd.DataFrame(api.get_predictions_bulk(semana=periodo, enfermedad=enfermedad))
        if municipio and not datos.empty:
            datos = datos[datos["municipio_id"].astype(str) == municipio]
        return datos

    enfermedades = (
        [("COVID-19", "covid-19"), ("Influenza", "influenza"), ("Dengue", "dengue")]
        if tipo == "comparativo"
        else [(enfermedad.upper(), enfermedad)]
    )
    semanas = int(periodo)
    filas = []
    for etiqueta, codigo in enfermedades:
        resultado = api.get_prediction_history(municipio, enfermedad=codigo, semanas=semanas)
        if tipo == "comparativo":
            observados = sum(int(item["casos"]) for item in resultado.get("historico", []))
            proyectados = sum(int(item["casos"]) for item in resultado.get("prediccion", []))
            filas.append(
                {
                    "Enfermedad": etiqueta,
                    "Casos históricos disponibles": observados,
                    "Casos proyectados": proyectados,
                    "Clasificación": "Estimaciones del modelo",
                }
            )
        else:
            filas.extend(
                {
                    "Enfermedad": etiqueta,
                    "Municipio": MUNICIPIOS_JALISCO[municipio]["nombre"],
                    "Semana": item["semana"],
                    "Casos": item["casos"],
                    "Tipo de valor": "Histórico reportado",
                }
                for item in resultado.get("historico", [])
            )
            filas.extend(
                {
                    "Enfermedad": etiqueta,
                    "Municipio": MUNICIPIOS_JALISCO[municipio]["nombre"],
                    "Semana": item["semana"],
                    "Casos": item["casos"],
                    "Tipo de valor": "Proyección (no confirmada)",
                }
                for item in resultado.get("prediccion", [])
            )
    return pd.DataFrame(filas)


def render_reportes_view():
    st.markdown(
        '<div class="page-heading">Reportes epidemiológicos</div>'
        '<div class="page-description">Consulta y exporta resultados estructurados de las fuentes disponibles.</div>',
        unsafe_allow_html=True,
    )

    tipo_label = st.selectbox("Tipo de reporte", list(TIPOS_REPORTE), key="report_type")
    tipo = TIPOS_REPORTE[tipo_label]
    enfermedad_col, region_col, periodo_col = st.columns(3)
    with enfermedad_col:
        enfermedad = st.selectbox(
            "Enfermedad",
            ["covid-19", "influenza", "dengue"],
            key="report_disease",
            disabled=tipo == "comparativo",
        )
    with region_col:
        opciones_region = ["todas"] + list(MUNICIPIOS_JALISCO) if tipo == "geografico" else list(MUNICIPIOS_JALISCO)
        municipio = st.selectbox(
            "Región",
            opciones_region,
            format_func=lambda codigo: "Todas las regiones" if codigo == "todas" else MUNICIPIOS_JALISCO[codigo]["nombre"],
            key="report_municipio",
        )
    with periodo_col:
        opciones_periodo = (
            ["2026-W20", "2026-W19", "2026-W18", "2026-W17"]
            if tipo == "geografico"
            else ["8", "12", "24"]
        )
        periodo = st.selectbox(
            "Semana" if tipo == "geografico" else "Ventana histórica (semanas)",
            opciones_periodo,
            format_func=lambda valor: valor if tipo == "geografico" else f"Últimas {valor} semanas",
            key="report_period",
        )

    st.markdown("#### Catálogo de reportes disponibles")
    st.caption(
        "Los reportes de evolución y predicción se consultan por región; "
        "el comparativo presenta las tres enfermedades y la distribución usa la región y semana seleccionadas."
    )

    datos = _reporte(tipo, enfermedad, None if municipio == "todas" else municipio, periodo)
    if DEMO_MODE:
        st.caption("Datos sintéticos de demostración; no son evidencia de casos confirmados.")
    if datos.empty:
        st.info("No hay información para generar este reporte.")
        return

    with st.container(border=True):
        st.markdown(f'<div class="panel-title">{tipo_label}</div>', unsafe_allow_html=True)
        if tipo == "geografico":
            columnas = [col for col in ("municipio", "nivel_riesgo", "casos_esperados") if col in datos]
            st.dataframe(datos[columnas], hide_index=True, use_container_width=True)
        else:
            st.dataframe(datos, hide_index=True, use_container_width=True)
        st.download_button(
            "Exportar CSV",
            datos.to_csv(index=False).encode("utf-8-sig"),
            f"reporte_{tipo}_{enfermedad}_{periodo}.csv",
            "text/csv",
            use_container_width=True,
        )
    st.caption("La exportación PDF no está disponible en la aplicación actual.")
