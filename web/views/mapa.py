"""
Vista: Mapa de Riesgo Epidemiológico Municipal — Folium + OpenStreetMap.
"""

from html import escape

import streamlit as st
import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium
import pandas as pd
from api_client import DEMO_MODE, api

COLOR_RIESGO = {
    "bajo": "#4e9577",
    "medio": "#bd9b43",
    "alto": "#d17d45",
    "crítico": "#b54755",
}
FONDO_RIESGO = {
    "bajo": "#e9f3ed",
    "medio": "#f6f1df",
    "alto": "#faeee5",
    "crítico": "#f7e9eb",
}


def render_mapa_view():
    st.markdown(
        '<div class="page-heading">Mapa de riesgo epidemiológico</div>'
        '<div class="page-description">Explora la distribución de casos estimados por municipio y semana.</div>',
        unsafe_allow_html=True,
    )

    # ── Filtros ──
    with st.container(border=True):
        f1, f2, f3 = st.columns([1, 1, 1.7])

        with f1:
            enfermedad = st.selectbox(
                "Patología",
                ["dengue", "influenza", "covid-19"],
                format_func=lambda x: {"dengue": "Dengue", "influenza": "Influenza", "covid-19": "COVID-19"}[x],
                key="map_enf",
            )

        with f2:
            semana_raw = st.selectbox(
                "Semana epidemiológica",
                ["2026-W20 (Actual)", "2026-W19", "2026-W18", "2026-W17"],
                key="map_sem",
            )
            semana = semana_raw.split(" ")[0]

        with f3:
            modo = st.radio(
                "Capa",
                ["Marcadores de riesgo", "Mapa de calor"],
                horizontal=True,
                index=1,
                key="map_modo",
            )

    # ── Datos ──
    datos = api.get_predictions_bulk(semana=semana, enfermedad=enfermedad)
    df = pd.DataFrame(datos)

    if df.empty:
        st.info("No hay datos disponibles para la patología y semana seleccionadas.")
        return

    if "calor" in modo.lower():
        leyenda = """
        <div class="risk-legend">
            <span class="risk-legend-title">Intensidad de casos</span>
            <span class="heat-scale"></span>
            <span class="risk-legend-item">Menor</span>
            <span class="risk-legend-item">Mayor</span>
            <span class="risk-legend-note">El color se concentra donde hay más casos estimados.</span>
        </div>
        """
    else:
        leyenda_items = "".join(
            f'<span class="risk-legend-item"><span class="risk-dot" style="background:{COLOR_RIESGO[nivel]}"></span>{etiqueta}</span>'
            for nivel, etiqueta in (
                ("crítico", "Crítico"),
                ("alto", "Alto"),
                ("medio", "Medio"),
                ("bajo", "Bajo"),
            )
        )
        leyenda = (
            '<div class="risk-legend"><span class="risk-legend-title">Nivel de riesgo</span>'
            f'{leyenda_items}<span class="risk-legend-note">Toca un punto para ver el detalle.</span></div>'
        )
    st.markdown(leyenda, unsafe_allow_html=True)

    # ── Mapa + Tabla ──
    col_map, col_tbl = st.columns([1.25, 1])

    with col_map:
        with st.container(border=True):
            st.markdown('<div class="panel-title">Distribución geográfica</div>', unsafe_allow_html=True)
            subtitulo = f"{enfermedad.upper()} · {semana}"
            if DEMO_MODE:
                subtitulo += " · DATOS SINTÉTICOS"
            st.caption(subtitulo)
            m = folium.Map(location=[20.6767, -103.3475], zoom_start=8, tiles="OpenStreetMap")

            if "calor" in modo.lower():
                heat = [[r.lat, r.lon, r.casos_esperados] for r in df.itertuples()]
                HeatMap(
                    heat,
                    radius=25,
                    blur=15,
                    max_zoom=10,
                    gradient={
                        0.2: "#4e9577",
                        0.5: "#e5c76d",
                        0.75: "#d17d45",
                        1: "#b54755",
                    },
                ).add_to(m)
            else:
                for r in df.itertuples():
                    color = COLOR_RIESGO.get(r.nivel_riesgo, "#757575")
                    radio = max(8, min(24, int(r.casos_esperados**0.5 * 1.5)))
                    popup = f"""
                    <div style="font-family:sans-serif;font-size:13px;min-width:160px">
                        <b style="color:#244b4b">{escape(str(r.municipio))}</b><br>
                        Riesgo: <b style="color:{color};text-transform:uppercase">{r.nivel_riesgo}</b><br>
                        Casos estimados: <b>{r.casos_esperados}</b><br>
                        <small>Semana {semana}</small>
                    </div>"""
                    folium.CircleMarker(
                        [r.lat, r.lon],
                        radius=radio,
                        popup=folium.Popup(popup, max_width=230),
                        tooltip=f"{r.municipio} · {r.nivel_riesgo.upper()} ({r.casos_esperados})",
                        color=color, fill=True, fill_color=color, fill_opacity=0.7, weight=2,
                    ).add_to(m)

            st_folium(m, width="100%", height=460, key=f"map_{enfermedad}_{semana}_{modo[:3]}")

    with col_tbl:
        with st.container(border=True):
            st.markdown('<div class="panel-title">Desglose municipal</div>', unsafe_allow_html=True)
            st.caption("Riesgo e intensidad relativa de casos")
            tbl = (
                df[["municipio", "nivel_riesgo", "casos_esperados"]]
                .sort_values("casos_esperados", ascending=False)
                .rename(columns={"municipio": "Municipio", "nivel_riesgo": "Riesgo", "casos_esperados": "Casos est."})
            )
            mayor_cantidad = max(1, int(tbl["Casos est."].max()))
            filas = []
            for municipio, riesgo, casos in tbl.itertuples(index=False, name=None):
                nivel = str(riesgo).lower()
                color = COLOR_RIESGO.get(nivel, "#788780")
                fondo = FONDO_RIESGO.get(nivel, "#eef1ef")
                ancho = max(5, round(int(casos) / mayor_cantidad * 100))
                filas.append(
                    "<tr>"
                    f'<td>{escape(str(municipio))}</td>'
                    f'<td><span class="risk-pill" style="background:{fondo};color:{color}">'
                    f'<span class="status-dot" style="background:{color}"></span>{escape(nivel)}</span></td>'
                    f'<td><div class="case-track" title="{int(casos)} casos estimados">'
                    f'<span style="width:{ancho}%;background:{color}"></span></div></td>'
                    "</tr>"
                )
            st.markdown(
                '<div class="municipal-table-wrap"><table class="municipal-table">'
                "<thead><tr><th>Municipio</th><th>Riesgo</th><th>Casos est.</th></tr></thead>"
                f"<tbody>{''.join(filas)}</tbody></table></div>",
                unsafe_allow_html=True,
            )
            st.download_button(
                "Descargar CSV",
                tbl.to_csv(index=False).encode("utf-8"),
                f"riesgo_{enfermedad}_{semana}.csv",
                "text/csv",
                use_container_width=True,
            )
