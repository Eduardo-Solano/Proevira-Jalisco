"""Vista de distribución geográfica del riesgo epidemiológico."""

from html import escape

import folium
import pandas as pd
import streamlit as st
from folium.plugins import HeatMap
from streamlit_folium import st_folium

from api_client import DEMO_MODE, api

COLOR_RIESGO = {
    "bajo": "#4e9577",
    "medio": "#bd9b43",
    "alto": "#d17d45",
    "crítico": "#b54755",
}


def render_mapa_view():
    st.markdown(
        '<div class="page-heading">Distribución epidemiológica</div>'
        '<div class="page-description">Explora la distribución geográfica de los casos estimados por municipio.</div>',
        unsafe_allow_html=True,
    )

    enfermedades = {"COVID-19": "covid-19", "Influenza": "influenza", "Dengue": "dengue"}
    periodos = ["2026-W20 (Actual)", "2026-W19", "2026-W18", "2026-W17"]
    indicadores = [
        "Casos estimados",
        "Casos registrados",
        "Tasa de incidencia",
        "Mortalidad",
        "Variación de casos",
        "Nivel de riesgo",
    ]
    with st.container(border=True):
        enfermedad_col, periodo_col, indicador_col, capa_col = st.columns([1, 1, 1.15, 1.2])
        with enfermedad_col:
            enfermedad = st.selectbox("Enfermedad", list(enfermedades), key="map_enf")
        with periodo_col:
            periodo = st.selectbox("Periodo", periodos, key="map_sem")
        with indicador_col:
            indicador = st.selectbox("Indicador geográfico", indicadores, key="map_indicator")
        with capa_col:
            modo = st.radio(
                "Visualización",
                ["Marcadores", "Mapa de calor"],
                horizontal=True,
                key="map_modo",
            )

    if indicador not in ("Casos estimados", "Nivel de riesgo"):
        st.info(
            f"El indicador «{indicador}» no está disponible en los datos conectados. "
            "El mapa no sustituirá ese valor por una estimación diferente."
        )
        return

    semana = periodo.split(" ")[0]
    datos = api.get_predictions_bulk(semana=semana, enfermedad=enfermedades[enfermedad])
    df = pd.DataFrame(datos)
    if df.empty:
        st.info("No hay datos disponibles para la enfermedad y el periodo seleccionados.")
        return

    if DEMO_MODE:
        st.caption("Datos sintéticos de demostración; los casos mostrados son estimaciones, no confirmaciones.")

    municipios = df.sort_values("municipio")["municipio"].tolist()
    mapa_col, detalle_col = st.columns([1.55, 1])
    with mapa_col:
        with st.container(border=True):
            st.markdown('<div class="panel-title">Mapa epidemiológico</div>', unsafe_allow_html=True)
            st.caption(f"{enfermedad} · {semana} · {indicador}")
            mapa = folium.Map(location=[20.6767, -103.3475], zoom_start=7, tiles="OpenStreetMap")

            if modo == "Mapa de calor":
                peso_riesgo = {"bajo": 1, "medio": 2, "alto": 3, "crítico": 4}
                intensidad = (
                    lambda fila: peso_riesgo.get(str(fila.nivel_riesgo).lower(), 1)
                    if indicador == "Nivel de riesgo"
                    else fila.casos_esperados
                )
                HeatMap(
                    [[fila.lat, fila.lon, intensidad(fila)] for fila in df.itertuples()],
                    radius=25,
                    blur=15,
                    max_zoom=10,
                    gradient={0.2: "#4e9577", 0.5: "#e5c76d", 0.75: "#d17d45", 1: "#b54755"},
                ).add_to(mapa)
            else:
                for fila in df.itertuples():
                    nivel = str(fila.nivel_riesgo).lower()
                    color = COLOR_RIESGO.get(nivel, "#757575")
                    radio = max(8, min(24, int(fila.casos_esperados**0.5 * 1.5)))
                    popup = (
                        f"<b>{escape(str(fila.municipio))}</b><br>"
                        f"Riesgo: {escape(nivel)}<br>"
                        f"Casos estimados: {int(fila.casos_esperados)}<br>"
                        f"Semana: {escape(semana)}"
                    )
                    folium.CircleMarker(
                        [fila.lat, fila.lon],
                        radius=radio,
                        popup=folium.Popup(popup, max_width=230),
                        tooltip=f"{fila.municipio} · {nivel.upper()}",
                        color=color,
                        fill=True,
                        fill_color=color,
                        fill_opacity=0.7,
                        weight=2,
                    ).add_to(mapa)

            st_folium(mapa, width="100%", height=480, key=f"map_{enfermedad}_{semana}_{modo[:3]}")
            nota_leyenda = (
                    "Color e intensidad: riesgo; tamaño del marcador: casos estimados."
                    if indicador == "Nivel de riesgo"
                    else "Color: riesgo; tamaño e intensidad: casos estimados."
            )
            st.markdown(
                    '<div class="risk-legend"><span class="risk-legend-title">Nivel de riesgo</span>'
                    + "".join(
                        f'<span class="risk-legend-item"><span class="risk-dot" style="background:{color}"></span>{nivel}</span>'
                        for nivel, color in COLOR_RIESGO.items()
                    )
                    + f'<span class="risk-legend-note">{nota_leyenda}</span></div>',
                    unsafe_allow_html=True,
            )

    with detalle_col:
        with st.container(border=True):
            st.markdown('<div class="panel-title">Detalle regional</div>', unsafe_allow_html=True)
            municipio = st.selectbox("Entidad o municipio", municipios, key="map_municipio")
            seleccionado = df[df["municipio"] == municipio].iloc[0]
            st.markdown(f"### {escape(str(seleccionado['municipio']))}")
            riesgo = str(seleccionado["nivel_riesgo"]).lower()
            color = COLOR_RIESGO.get(riesgo, "#757575")
            st.markdown(
                f'<span class="risk-pill" style="background:#f0f3f0;color:{color}">'
                f'<span class="status-dot" style="background:{color}"></span>Riesgo {escape(riesgo)}</span>',
                unsafe_allow_html=True,
            )
            st.metric("Casos estimados", f"{int(seleccionado['casos_esperados']):,}")
            st.caption(f"{enfermedad} · Semana {semana}")
            st.caption("Los demás indicadores regionales no están disponibles en la fuente conectada.")
