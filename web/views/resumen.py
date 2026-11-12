"""Vista de síntesis epidemiológica."""

import pandas as pd
import plotly.express as px
import streamlit as st

from api_client import DEMO_MODE, api

ENFERMEDADES = {
    "Todas": None,
    "COVID-19": "covid-19",
    "Influenza": "influenza",
    "Dengue": "dengue",
}
PERIODOS = ["2026-W20 (Actual)", "2026-W19", "2026-W18", "2026-W17"]


def _obtener_datos(semana: str, enfermedad: str | None) -> list[dict]:
    if enfermedad:
        return api.get_predictions_bulk(semana=semana, enfermedad=enfermedad)

    datos = []
    for codigo in ("covid-19", "influenza", "dengue"):
        datos.extend(api.get_predictions_bulk(semana=semana, enfermedad=codigo))
    return datos


def render_resumen_view():
    st.markdown(
        '<div class="page-heading">Panorama epidemiológico</div>'
        '<div class="page-description">Síntesis de señales epidemiológicas para Jalisco.</div>',
        unsafe_allow_html=True,
    )

    filtro_enfermedad, filtro_periodo = st.columns(2)
    with filtro_enfermedad:
        enfermedad = st.selectbox("Enfermedad", list(ENFERMEDADES), key="overview_disease")
    with filtro_periodo:
        periodo = st.selectbox("Periodo de consulta", PERIODOS, key="overview_period")
    semana = periodo.split(" ")[0]

    if DEMO_MODE:
        st.caption("Datos sintéticos de demostración; no representan casos confirmados.")

    datos = _obtener_datos(semana, ENFERMEDADES[enfermedad])
    df = pd.DataFrame(datos)
    if df.empty:
        st.info("No hay información para los filtros seleccionados.")
        return

    enfermedad_seleccionada = ENFERMEDADES[enfermedad]
    total_estimado = int(df["casos_esperados"].sum()) if enfermedad_seleccionada else None
    municipios_riesgo = int(
        df.loc[df["nivel_riesgo"].astype(str).str.lower().isin(["alto", "crítico"]), "municipio_id"].nunique()
    )
    variacion = "No disponible"
    metricas = st.columns(4)
    valores = (
        (
            "Casos estimados",
            f"{total_estimado:,}" if total_estimado is not None else "Consulta una enfermedad",
            f"Periodo {semana}" if total_estimado is not None else "No se suman enfermedades distintas",
        ),
        ("Municipios en riesgo alto o crítico", str(municipios_riesgo), "Según nivel de riesgo disponible"),
        ("Tasa de incidencia", "No disponible", "No existe una tasa en los datos de esta vista"),
        ("Variación del periodo", variacion, "No hay serie comparable en el API"),
    )
    for columna, (etiqueta, valor, detalle) in zip(metricas, valores):
        with columna:
            st.markdown(
                f'<div class="metric-card"><div class="metric-label">{etiqueta}</div>'
                f'<p class="metric-val">{valor}</p><div class="metric-sub">{detalle}</div></div>',
                unsafe_allow_html=True,
            )

    st.markdown("")
    serie_region = df.sort_values("casos_esperados", ascending=False).iloc[0]
    enfermedad_serie = str(serie_region.get("enfermedad", "dengue")).lower()
    datos_historicos = api.get_prediction_history(
        str(serie_region["municipio_id"]),
        enfermedad=enfermedad_serie,
        semanas=12,
    )
    df_historico = pd.DataFrame(datos_historicos.get("historico", []))
    with st.container(border=True):
        municipio_serie = str(serie_region["municipio"])
        st.markdown(
            f'<div class="panel-title">Evolución histórica disponible · {municipio_serie}</div>',
            unsafe_allow_html=True,
        )
        st.caption(
            f"Serie histórica de {enfermedad_serie.upper()}; el periodo del filtro aplica a la distribución territorial."
        )
        if df_historico.empty:
            st.info("La fuente no proporcionó una serie histórica para estos filtros.")
        else:
            fig_hist = px.line(
                df_historico,
                x="semana",
                y="casos",
                markers=True,
                labels={"semana": "Semana epidemiológica", "casos": "Casos históricos"},
            )
            fig_hist.update_traces(line_color="#4e9577", line_width=3)
            fig_hist.update_layout(
                template="plotly_white",
                height=300,
                margin=dict(l=5, r=10, t=10, b=5),
                showlegend=False,
            )
            st.plotly_chart(fig_hist, use_container_width=True)

    grafica, comparativa = st.columns([1.5, 1])
    with grafica:
        with st.container(border=True):
            st.markdown('<div class="panel-title">Municipios con mayor volumen estimado</div>', unsafe_allow_html=True)
            st.caption("Ordenados por casos estimados; no son conteos confirmados.")
            top = df.sort_values("casos_esperados", ascending=False).head(8).copy()
            if not enfermedad_seleccionada:
                top["municipio"] = top["municipio"] + " · " + top["enfermedad"].str.upper()
            top = top.sort_values("casos_esperados")
            fig = px.bar(
                top,
                x="casos_esperados",
                y="municipio",
                orientation="h",
                labels={"casos_esperados": "Casos estimados", "municipio": ""},
                color_discrete_sequence=["#4e9577"],
            )
            fig.update_layout(
                template="plotly_white",
                height=300,
                margin=dict(l=5, r=10, t=10, b=5),
                showlegend=False,
            )
            st.plotly_chart(fig, use_container_width=True)

    with comparativa:
        with st.container(border=True):
            st.markdown('<div class="panel-title">Comparativa entre enfermedades</div>', unsafe_allow_html=True)
            filas = []
            for nombre, codigo in (("COVID-19", "covid-19"), ("Influenza", "influenza"), ("Dengue", "dengue")):
                comparacion = pd.DataFrame(api.get_predictions_bulk(semana=semana, enfermedad=codigo))
                if not comparacion.empty:
                    filas.append({"Enfermedad": nombre, "Casos estimados": int(comparacion["casos_esperados"].sum())})
            if filas:
                st.dataframe(pd.DataFrame(filas), hide_index=True, use_container_width=True)

    st.markdown("")
    izquierda, derecha = st.columns([1.2, 1])
    with izquierda:
        with st.container(border=True):
            st.markdown('<div class="panel-title">Señales por enfermedad</div>', unsafe_allow_html=True)
            for nombre, codigo, color, fondo in (
                ("Dengue", "dengue", "#b54755", "#f7e9eb"),
                ("Influenza", "influenza", "#bd9b43", "#f6f1df"),
                ("COVID-19", "covid-19", "#4e9577", "#e9f3ed"),
            ):
                if ENFERMEDADES[enfermedad] and codigo != ENFERMEDADES[enfermedad]:
                    continue
                sub = df[df["enfermedad"].str.lower() == codigo] if "enfermedad" in df else df
                riesgo_alto = int(sub["nivel_riesgo"].astype(str).str.lower().isin(["alto", "crítico"]).sum())
                st.markdown(
                    f'<div class="overview-signal" style="--disease-color:{color};--disease-bg:{fondo}">'
                    f'<strong>{nombre}</strong><span>{riesgo_alto} municipios con riesgo alto o crítico</span></div>',
                    unsafe_allow_html=True,
                )
    with derecha:
        with st.container(border=True):
            st.markdown('<div class="panel-title">Hallazgos y alertas vigentes</div>', unsafe_allow_html=True)
            alertas = api.get_alerts(activa=True)
            if alertas:
                for alerta in alertas[:3]:
                    st.markdown(f"**{alerta.get('nivel', 'Alerta').upper()} · {alerta.get('municipio', 'Región')}**")
                    st.caption(alerta.get("mensaje", ""))
            else:
                st.caption("No hay alertas activas para mostrar.")

    st.caption(
        "Los valores de riesgo y casos esperados son proyecciones del sistema; "
        "no deben interpretarse como diagnósticos ni casos confirmados."
    )
