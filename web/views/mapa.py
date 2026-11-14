"""Vista de distribución geográfica del riesgo epidemiológico municipal."""

import json
from bisect import bisect_left
from datetime import date, timedelta
from html import escape
from math import ceil
from pathlib import Path

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
PESO_RIESGO = {"bajo": 1.0, "medio": 2.0, "alto": 3.0, "crítico": 4.0}
JALISCO_BOUNDARY_PATH = Path(__file__).resolve().parents[2] / "data" / "geo" / "jalisco.geojson"
CENTRO_BOUNDS_PADDING = 0.12
JALISCO_BOUNDS_PADDING = 0.35

ETIQUETAS_VARIABLES = {
    "lag0": "Casos de la semana más reciente",
    "log_lag0": "Casos recientes (escala log)",
    "lag1": "Casos de hace 1 semana",
    "log_lag1": "Casos hace 1 semana (escala log)",
    "lag2": "Casos de hace 2 semanas",
    "media_4s": "Promedio últimas 4 semanas",
    "media_8s": "Promedio últimas 8 semanas",
    "max_8s": "Máximo últimas 8 semanas",
    "std_8s": "Variación últimas 8 semanas",
    "tendencia": "Tendencia reciente",
    "tendencia_rel": "Cambio relativo 4s vs 8s",
    "def_4s": "Defunciones últimas 4 semanas",
    "sem_sin": "Estacionalidad semanal",
    "sem_cos": "Estacionalidad semanal",
    "mun_cod": "Municipio",
}


def _fecha_semana_legible(semana_str: str | None) -> str:
    if not semana_str or "-W" not in str(semana_str):
        return str(semana_str or "")
    try:
        anio_s, sem_s = str(semana_str).strip().upper().split("-W", 1)
        return date.fromisocalendar(int(anio_s), int(sem_s), 1).strftime("%d/%m/%Y")
    except ValueError:
        return str(semana_str)


def _semanas_futuras(semana_base: str, cantidad: int = 4) -> list[str]:
    try:
        anio_s, sem_s = semana_base.strip().upper().split("-W", 1)
        lunes = date.fromisocalendar(int(anio_s), int(sem_s), 1)
    except ValueError:
        return [semana_base]

    salida = []
    for paso in range(cantidad):
        iso = (lunes + timedelta(weeks=paso)).isocalendar()
        salida.append(f"{iso.year}-W{iso.week:02d}")
    return salida


def _etiqueta_variable(nombre: str) -> str:
    if nombre in ETIQUETAS_VARIABLES:
        return ETIQUETAS_VARIABLES[nombre]
    for prefijo in ("log_lag", "lag"):
        if nombre.startswith(prefijo) and nombre[len(prefijo):].isdigit():
            n = int(nombre[len(prefijo):])
            return "Casos de la semana más reciente" if n == 0 else f"Casos de hace {n} semanas"
    if nombre.startswith("tasa_edad_"):
        return f"Proporción edad {nombre.removeprefix('tasa_edad_').replace('_', '-')}"
    return nombre.replace("_", " ").capitalize()


def _radio_marcador(casos: float) -> int:
    return max(7, min(24, int(round(7 + (max(0.0, float(casos)) ** 0.5) * 3.2))))


def _formatear_umbrales(umbrales: list) -> str:
    """Convierte cortes [b1, b2, b3] (searchsorted left) en rangos enteros exactos por nivel."""
    if not isinstance(umbrales, list) or len(umbrales) != 3:
        return ""
    b1, b2, b3 = [float(x) for x in umbrales]
    tope = max(int(ceil(b3)) + 1, 5)
    grupos: dict[int, list[int]] = {0: [], 1: [], 2: [], 3: []}
    for c in range(tope + 1):
        idx = bisect_left([b1, b2, b3], float(c))
        grupos[idx].append(c)

    nombres = ((0, "Bajo"), (1, "Medio"), (2, "Alto"))
    partes = []
    for idx, nombre in nombres:
        vals = grupos[idx]
        if not vals:
            partes.append(f"{nombre}: n/a")
        elif vals[0] == vals[-1]:
            partes.append(f"{nombre}: {vals[0]}")
        else:
            partes.append(f"{nombre}: {vals[0]}–{vals[-1]}")
    crit_min = max((max(grupos[i]) + 1 for i in (0, 1, 2) if grupos[i]), default=int(ceil(b3)))
    partes.append(f"Crítico: {crit_min}+")
    return " · ".join(partes) + " casos"


def render_mapa_view():
    st.markdown(
        '<div class="page-heading">Mapa epidemiológico municipal</div>'
        '<div class="page-description">Distribución geográfica de las predicciones municipales directas en la Región Centro de Jalisco.</div>',
        unsafe_allow_html=True,
    )

    enfermedades = {"Dengue": "dengue", "Influenza": "influenza", "COVID-19": "covid"}
    indicadores = ["Casos esperados", "Nivel de riesgo"]

    model_info = {} if DEMO_MODE else api.get_model_info()
    por_enfermedad = model_info.get("por_enfermedad", {}) if isinstance(model_info, dict) else {}

    with st.container(border=True):
        enfermedad_col, periodo_col, indicador_col, capa_col = st.columns([1, 1.15, 1.05, 1.2])
        with enfermedad_col:
            enfermedad = st.selectbox("Enfermedad", list(enfermedades), key="map_enf")

        enf_api = enfermedades[enfermedad]
        if DEMO_MODE:
            periodos = ["2026-W20 (Demostración)"]
            ultima_obs = None
        else:
            info_enf = por_enfermedad.get(enf_api, {})
            semana_base = info_enf.get("semana_prediccion") or model_info.get("semana_prediccion")
            ultima_obs = info_enf.get("ultima_semana_datos") or model_info.get("ultima_semana_datos")
            if not semana_base:
                st.info("El backend no reporta una semana de proyección disponible.")
                return
            semanas = _semanas_futuras(semana_base, cantidad=4)
            periodos = [
                f"{sem} · del {_fecha_semana_legible(sem)} (Próxima)"
                if idx == 0
                else f"{sem} · del {_fecha_semana_legible(sem)} (+{idx + 1} sem)"
                for idx, sem in enumerate(semanas)
            ]

        with periodo_col:
            periodo = st.selectbox("Semana proyectada", periodos, key="map_sem")
        with indicador_col:
            indicador = st.selectbox("Indicador", indicadores, key="map_indicator")
        with capa_col:
            modo = st.radio(
                "Visualización",
                ["Marcadores", "Mapa de calor"],
                horizontal=True,
                key="map_modo",
            )

    semana = periodo.split(" ")[0]
    datos = api.get_predictions_bulk(semana=semana, enfermedad=enf_api)
    df = pd.DataFrame(datos)
    if df.empty:
        st.info("No hay predicciones disponibles para la enfermedad y semana seleccionadas.")
        return

    df["casos_esperados"] = pd.to_numeric(df["casos_esperados"], errors="coerce").fillna(0.0)
    if "casos_esperados_redondeados" not in df.columns:
        df["casos_esperados_redondeados"] = df["casos_esperados"].round().astype(int)
    else:
        df["casos_esperados_redondeados"] = (
            pd.to_numeric(df["casos_esperados_redondeados"], errors="coerce")
            .fillna(df["casos_esperados"].round())
            .astype(int)
        )

    if DEMO_MODE:
        st.caption("Datos sintéticos de demostración; no representan casos reales.")
    else:
        obs_txt = (
            f" · Última semana confirmada ({enfermedad}): {ultima_obs} (del {_fecha_semana_legible(ultima_obs)})"
            if ultima_obs
            else ""
        )
        st.caption(
            f"Cobertura: {len(df)} municipios de la Región Centro{obs_txt}."
        )

    df = df.sort_values(["casos_esperados", "municipio"], ascending=[False, True]).reset_index(drop=True)
    municipios_ordenados = sorted(df["municipio"].tolist())

    mapa_col, detalle_col = st.columns([1.55, 1])
    with mapa_col:
        with st.container(border=True):
            st.markdown('<div class="panel-title">Mapa epidemiológico · Región Centro</div>', unsafe_allow_html=True)
            st.caption(f"{enfermedad} · Semana proyectada {semana} · Indicador: {indicador}")

            jalisco_boundary = None
            if JALISCO_BOUNDARY_PATH.exists():
                with JALISCO_BOUNDARY_PATH.open(encoding="utf-8") as boundary_file:
                    jalisco_boundary = json.load(boundary_file)

            lat_min = float(df["lat"].min())
            lat_max = float(df["lat"].max())
            lon_min = float(df["lon"].min())
            lon_max = float(df["lon"].max())

            if jalisco_boundary and "bbox" in jalisco_boundary:
                west, south, east, north = jalisco_boundary["bbox"]
                max_bounds_cfg = dict(
                    max_bounds=True,
                    min_lat=south - JALISCO_BOUNDS_PADDING,
                    min_lon=west - JALISCO_BOUNDS_PADDING,
                    max_lat=north + JALISCO_BOUNDS_PADDING,
                    max_lon=east + JALISCO_BOUNDS_PADDING,
                    maxBoundsViscosity=1,
                )
            else:
                max_bounds_cfg = {}

            mapa = folium.Map(
                location=[(lat_min + lat_max) / 2, (lon_min + lon_max) / 2],
                min_zoom=6,
                max_zoom=13,
                zoom_start=10,
                tiles="OpenStreetMap",
                prefer_canvas=True,
                **max_bounds_cfg,
            )
            mapa.fit_bounds(
                [
                    [lat_min - CENTRO_BOUNDS_PADDING, lon_min - CENTRO_BOUNDS_PADDING],
                    [lat_max + CENTRO_BOUNDS_PADDING, lon_max + CENTRO_BOUNDS_PADDING],
                ],
                padding=(16, 16),
                max_zoom=11,
            )

            if jalisco_boundary:
                folium.GeoJson(
                    jalisco_boundary,
                    name="Límite de Jalisco",
                    style_function=lambda feature: {
                        "color": "#7b8a8b",
                        "weight": 2,
                        "fillColor": "#4e9577",
                        "fillOpacity": 0.03,
                    },
                    tooltip=folium.GeoJsonTooltip(fields=["shapeName"], aliases=["Estado:"]),
                ).add_to(mapa)

            if modo == "Mapa de calor":
                if indicador == "Nivel de riesgo":
                    puntos = [
                        [float(fila.lat), float(fila.lon), PESO_RIESGO.get(str(fila.nivel_riesgo).lower(), 1.0)]
                        for fila in df.itertuples()
                    ]
                else:
                    max_casos = max(float(df["casos_esperados"].max()), 1.0)
                    puntos = [
                        [float(fila.lat), float(fila.lon), max(float(fila.casos_esperados) / max_casos, 0.05)]
                        for fila in df.itertuples()
                    ]

                HeatMap(
                    puntos,
                    radius=28,
                    blur=18,
                    min_opacity=0.35,
                    max_zoom=11,
                    gradient={0.2: "#4e9577", 0.5: "#e5c76d", 0.75: "#d17d45", 1.0: "#b54755"},
                ).add_to(mapa)
            else:
                for fila in df.itertuples():
                    nivel = str(fila.nivel_riesgo).lower()
                    color = COLOR_RIESGO.get(nivel, "#757575")
                    radio = _radio_marcador(fila.casos_esperados)
                    popup = (
                        f"<b>{escape(str(fila.municipio))}</b> ({escape(str(fila.municipio_id))})<br>"
                        f"Riesgo proyectado: <b>{escape(nivel.upper())}</b><br>"
                        f"Casos estimados: <b>{int(fila.casos_esperados_redondeados)}</b><br>"
                        f"Semana: {escape(semana)}"
                    )
                    folium.CircleMarker(
                        [float(fila.lat), float(fila.lon)],
                        radius=radio,
                        popup=folium.Popup(popup, max_width=250),
                        tooltip=(
                            f"{fila.municipio} · {nivel.upper()} · "
                            f"{int(fila.casos_esperados_redondeados)} casos"
                        ),
                        color=color,
                        fill=True,
                        fill_color=color,
                        fill_opacity=0.72,
                        weight=2,
                    ).add_to(mapa)

            st_folium(
                mapa,
                height=480,
                key=f"map_{enf_api}_{semana}_{indicador}_{modo[:3]}",
                returned_objects=[],
                use_container_width=True,
            )
            nota_leyenda = (
                "Intensidad proporcional al nivel de riesgo municipal (1–4)."
                if modo == "Mapa de calor" and indicador == "Nivel de riesgo"
                else "Color según nivel de riesgo municipal; tamaño/intensidad según casos esperados."
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
            st.markdown('<div class="panel-title">Detalle municipal</div>', unsafe_allow_html=True)
            municipio_sel = st.selectbox("Municipio", municipios_ordenados, key="map_municipio")
            fila_sel = df[df["municipio"] == municipio_sel].iloc[0]
            mid_sel = str(fila_sel["municipio_id"])

            detalle_pred = {}
            hist_pred = {}
            semana_param = None if (not DEMO_MODE and semana == semana_base) else semana
            try:
                detalle_pred = api.get_prediction(mid_sel, semana=semana_param, enfermedad=enf_api)
            except Exception:
                pass
            try:
                hist_pred = api.get_prediction_history(mid_sel, enfermedad=enf_api, semanas=4, horizonte=1)
            except Exception:
                pass

            riesgo = str(detalle_pred.get("nivel_riesgo") or fila_sel["nivel_riesgo"]).lower()
            casos_esp = float(detalle_pred.get("casos_esperados", fila_sel["casos_esperados"]))
            casos_red = int(detalle_pred.get("casos_esperados_redondeados", fila_sel["casos_esperados_redondeados"]))
            color = COLOR_RIESGO.get(riesgo, "#757575")

            st.markdown(f"### {escape(str(municipio_sel))}")
            st.markdown(
                f'<span class="risk-pill" style="background:#f0f3f0;color:{color}">'
                f'<span class="status-dot" style="background:{color}"></span>Riesgo {escape(riesgo)}</span>',
                unsafe_allow_html=True,
            )

            historico = hist_pred.get("historico", [])
            ultimo_punto = historico[-1] if historico else None

            col_m1, col_m2 = st.columns(2)
            col_m1.metric(
                f"Casos en esta semana ({semana})",
                f"{casos_red:,}",
                help=(
                    f"Estimación individual solo para la semana {semana} (del {_fecha_semana_legible(semana)}). "
                    f"Promedio estadístico: {casos_esp:.2f} casos."
                ),
            )
            if ultimo_punto is not None:
                col_m2.metric(
                    f"Último observado ({ultimo_punto['semana']})",
                    f"{int(ultimo_punto['casos'])}",
                )
            else:
                col_m2.metric("Semana proyectada", semana)

            if casos_red == 0 and casos_esp > 0:
                st.caption("Actividad mínima estimada (menos de 1 caso en promedio semanal).")

            umbrales = detalle_pred.get("umbrales")
            rangos_txt = _formatear_umbrales(umbrales) if umbrales else ""
            if rangos_txt:
                st.caption(
                    f"Referencia habitual en **{municipio_sel}** ({enfermedad}): {rangos_txt}. "
                    "Cada municipio se evalúa según su propia incidencia histórica."
                )
            else:
                st.caption(
                    "El nivel de riesgo se compara contra el historial habitual de cada municipio."
                )

            shap_top3 = detalle_pred.get("shap_top3") or []
            if shap_top3:
                st.markdown("**¿Qué influyó más en esta estimación?**")
                for item in shap_top3:
                    val = float(item.get("valor", 0.0))
                    efecto = "tiende a subir el riesgo" if val >= 0 else "mantiene bajo el riesgo"
                    st.caption(f"• {_etiqueta_variable(str(item.get('feature', '')))}: {efecto}")

    with st.expander("Tabla comparativa de los 12 municipios", expanded=False):
        tabla = df[["municipio", "casos_esperados_redondeados", "nivel_riesgo"]].rename(
            columns={
                "municipio": "Municipio",
                "casos_esperados_redondeados": "Casos estimados",
                "nivel_riesgo": "Nivel de riesgo",
            }
        )
        st.dataframe(tabla, hide_index=True, use_container_width=True)
