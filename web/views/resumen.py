"""Vista de síntesis epidemiológica para personal médico."""

from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

from api_client import DEMO_MODE, api

ENFERMEDADES = {
    "Todas": None,
    "COVID-19": "covid",
    "Influenza": "influenza",
    "Dengue": "dengue",
}


def _fecha_semana_texto(semana: str | None) -> str:
    if not semana or "-W" not in str(semana):
        return str(semana or "No disponible")
    try:
        anio, sem = str(semana).split("-W", 1)
        return date.fromisocalendar(int(anio), int(sem), 1).strftime("%d/%m/%Y")
    except ValueError:
        return str(semana)


def _semana_por_enfermedad(model_info: dict, codigo: str, fallback: str) -> str:
    por_enf = model_info.get("por_enfermedad", {}) if isinstance(model_info, dict) else {}
    return por_enf.get(codigo, {}).get("semana_prediccion") or fallback


def _ultima_observada_por_enfermedad(model_info: dict, codigo: str) -> str | None:
    por_enf = model_info.get("por_enfermedad", {}) if isinstance(model_info, dict) else {}
    return por_enf.get(codigo, {}).get("ultima_semana_datos")


def _obtener_datos(model_info: dict, semana_fallback: str, enfermedad: str | None) -> list[dict]:
    if enfermedad:
        sem_obj = _semana_por_enfermedad(model_info, enfermedad, semana_fallback)
        return api.get_predictions_bulk(semana=sem_obj, enfermedad=enfermedad)

    datos = []
    for codigo in ("dengue", "influenza", "covid"):
        sem_obj = _semana_por_enfermedad(model_info, codigo, semana_fallback)
        datos.extend(api.get_predictions_bulk(semana=sem_obj, enfermedad=codigo))
    return datos


def _resumen_observado(tendencia: list[dict], model_info: dict, filtro_enf: str | None) -> tuple[int, str, str, str]:
    """Calcula casos observados recientes y variación semanal real sin valores vacíos."""
    if not tendencia:
        return 0, "Sin registro", "Sin comparación", "Sin historial reciente"

    df_t = pd.DataFrame(tendencia).sort_values("semana").reset_index(drop=True)
    codigos = ["dengue", "influenza", "covid"] if filtro_enf is None else [filtro_enf]

    ultimo_total = 0
    previo_total = 0
    semanas_ref = []
    for c in codigos:
        if c not in df_t.columns:
            continue
        lim = _ultima_observada_por_enfermedad(model_info, c)
        sub = df_t[df_t["semana"] <= lim] if lim else df_t
        if sub.empty:
            continue
        ultimo_total += int(sub[c].iloc[-1])
        previo_total += int(sub[c].iloc[-2]) if len(sub) >= 2 else int(sub[c].iloc[-1])
        semanas_ref.append(str(sub["semana"].iloc[-1]))

    diff = ultimo_total - previo_total
    if diff > 0:
        tendencia_val = f"+{diff} casos"
        tendencia_det = f"Subió respecto a la semana previa ({previo_total})"
    elif diff < 0:
        tendencia_val = f"{diff} casos"
        tendencia_det = f"Bajó respecto a la semana previa ({previo_total})"
    else:
        tendencia_val = "Sin cambio"
        tendencia_det = f"Igual que la semana previa ({previo_total})"

    sem_label = semanas_ref[0] if len(set(semanas_ref)) == 1 and semanas_ref else "última semana"
    obs_det = f"Semana {sem_label} ({_fecha_semana_texto(sem_label)})" if "-" in sem_label else "Última semana por patología"
    return ultimo_total, obs_det, tendencia_val, tendencia_det


def render_resumen_view():
    st.markdown(
        '<div class="page-heading">Panorama epidemiológico</div>'
        '<div class="page-description">Resumen semanal de situación y proyección en los 12 municipios de la Región Centro.</div>',
        unsafe_allow_html=True,
    )

    resumen = api.get_dashboard_summary()
    semana_disponible = resumen.get("semana")
    if not semana_disponible:
        st.info("Todavía no hay una semana proyectada disponible en el servidor.")
        return

    model_info = {} if DEMO_MODE else api.get_model_info()
    if not DEMO_MODE and not model_info.get("por_enfermedad"):
        api._clear_read_cache()
        model_info = api.get_model_info()

    filtro_enfermedad, filtro_periodo = st.columns(2)
    with filtro_enfermedad:
        enfermedad = st.selectbox("Enfermedad", list(ENFERMEDADES), key="overview_disease")

    codigo_seleccionado = ENFERMEDADES[enfermedad]
    semana_objetivo = (
        _semana_por_enfermedad(model_info, codigo_seleccionado, semana_disponible)
        if codigo_seleccionado
        else "Próxima semana por enfermedad"
    )
    with filtro_periodo:
        st.selectbox(
            "Periodo proyectado",
            [semana_objetivo],
            format_func=lambda s: f"{s} (del {_fecha_semana_texto(s)})" if "-W" in s else s,
            key="overview_period",
        )

    if DEMO_MODE:
        st.caption("Vista de demostración con datos de ejemplo.")

    datos = _obtener_datos(model_info, semana_disponible, codigo_seleccionado)
    df = pd.DataFrame(datos)
    if df.empty:
        st.info("No hay información disponible para los filtros seleccionados.")
        return

    if "casos_esperados_redondeados" in df.columns:
        df["casos_enteros"] = (
            pd.to_numeric(df["casos_esperados_redondeados"], errors="coerce")
            .fillna(df["casos_esperados"].round())
            .astype(int)
        )
    else:
        df["casos_enteros"] = pd.to_numeric(df["casos_esperados"], errors="coerce").fillna(0.0).round().astype(int)

    total_estimado = int(df["casos_enteros"].sum())
    if codigo_seleccionado:
        detalle_estimado = f"Semana del {_fecha_semana_texto(semana_objetivo)} ({semana_objetivo})"
    else:
        desglose = df.groupby("enfermedad")["casos_enteros"].sum().to_dict()
        detalle_estimado = (
            f"Dengue: {int(desglose.get('dengue', 0))} · "
            f"Influenza: {int(desglose.get('influenza', 0))} · "
            f"COVID-19: {int(desglose.get('covid', 0))}"
        )

    mun_medio_sup = int(
        df.loc[df["nivel_riesgo"].astype(str).str.lower().isin(["medio", "alto", "crítico"]), "municipio_id"].nunique()
    )
    mun_alto_crit = int(
        df.loc[df["nivel_riesgo"].astype(str).str.lower().isin(["alto", "crítico"]), "municipio_id"].nunique()
    )
    detalle_riesgo = f"{mun_alto_crit} en nivel alto o crítico"

    obs_reciente, obs_det, var_val, var_det = _resumen_observado(
        resumen.get("tendencia", []), model_info, codigo_seleccionado
    )

    metricas = st.columns(4)
    valores = (
        ("Casos estimados (próxima semana)", f"{total_estimado:,}", detalle_estimado),
        ("Municipios con vigilancia activa", f"{mun_medio_sup} de 12", detalle_riesgo),
        ("Casos confirmados recientes", f"{obs_reciente:,}", obs_det),
        ("Cambio frente a semana previa", var_val, var_det),
    )
    for columna, (etiqueta, valor, detalle) in zip(metricas, valores):
        with columna:
            st.markdown(
                f'<div class="metric-card"><div class="metric-label">{etiqueta}</div>'
                f'<p class="metric-val">{valor}</p><div class="metric-sub">{detalle}</div></div>',
                unsafe_allow_html=True,
            )

    st.markdown("")
    df_historico = pd.DataFrame(resumen.get("tendencia", []))
    with st.container(border=True):
        st.markdown('<div class="panel-title">Casos observados en las últimas semanas</div>', unsafe_allow_html=True)
        st.caption("Registro semanal real acumulado en los 12 municipios de la Región Centro.")
        if df_historico.empty:
            st.info("No hay historial semanal disponible por el momento.")
        else:
            enfermedades_grafica = {
                "covid": "COVID-19",
                "influenza": "Influenza",
                "dengue": "Dengue",
            }
            series = list(enfermedades_grafica) if codigo_seleccionado is None else [codigo_seleccionado]
            df_linea = df_historico.melt(
                id_vars="semana",
                value_vars=[s for s in series if s in df_historico.columns],
                var_name="codigo_enfermedad",
                value_name="casos",
            )
            # Evitar caída falsa a 0 cuando una enfermedad cierra una semana antes (p. ej. Dengue en 2026-W43)
            mascara_valida = pd.Series(True, index=df_linea.index)
            for cod in series:
                lim = _ultima_observada_por_enfermedad(model_info, cod)
                if lim:
                    mascara_valida &= ~((df_linea["codigo_enfermedad"] == cod) & (df_linea["semana"] > lim))
            df_linea = df_linea[mascara_valida]
            df_linea["Enfermedad"] = df_linea["codigo_enfermedad"].map(enfermedades_grafica)
            df_linea["Fecha"] = df_linea["semana"].map(_fecha_semana_texto)
            fig_hist = px.line(
                df_linea,
                x="semana",
                y="casos",
                color="Enfermedad",
                markers=True,
                hover_data={"Fecha": True, "semana": True},
                labels={"semana": "Semana epidemiológica", "casos": "Casos confirmados"},
            )
            fig_hist.update_layout(
                template="plotly_white",
                height=300,
                margin=dict(l=5, r=10, t=10, b=5),
                yaxis=dict(rangemode="tozero", tickformat="d"),
            )
            st.plotly_chart(fig_hist, use_container_width=True)

    grafica, comparativa = st.columns([1.5, 1])
    with grafica:
        with st.container(border=True):
            st.markdown('<div class="panel-title">Municipios con mayor volumen proyectado</div>', unsafe_allow_html=True)
            top = df[df["casos_enteros"] > 0].sort_values("casos_enteros", ascending=False).head(8).copy()
            if top.empty:
                st.info("No se proyectan municipios con 1 o más casos para el filtro seleccionado.")
            else:
                if not codigo_seleccionado:
                    top["municipio"] = top["municipio"] + " · " + top["enfermedad"].str.upper()
                top = top.sort_values("casos_enteros")
                fig = px.bar(
                    top,
                    x="casos_enteros",
                    y="municipio",
                    orientation="h",
                    labels={"casos_enteros": "Casos estimados", "municipio": ""},
                    color_discrete_sequence=["#4e9577"],
                )
                fig.update_layout(
                    template="plotly_white",
                    height=300,
                    margin=dict(l=5, r=10, t=10, b=5),
                    showlegend=False,
                    xaxis=dict(rangemode="tozero", dtick=1, tickformat="d"),
                )
                st.plotly_chart(fig, use_container_width=True)

    with comparativa:
        with st.container(border=True):
            st.markdown('<div class="panel-title">Resumen por enfermedad</div>', unsafe_allow_html=True)
            filas = []
            for nombre, codigo in (("Dengue", "dengue"), ("Influenza", "influenza"), ("COVID-19", "covid")):
                sem_enf = _semana_por_enfermedad(model_info, codigo, semana_disponible)
                sub_enf = df[df["enfermedad"].str.lower() == codigo]
                if sub_enf.empty and codigo_seleccionado is None:
                    continue
                if sub_enf.empty and codigo_seleccionado != codigo:
                    continue
                riesgo_act = int(
                    sub_enf["nivel_riesgo"].astype(str).str.lower().isin(["medio", "alto", "crítico"]).sum()
                )
                filas.append(
                    {
                        "Enfermedad": nombre,
                        "Semana proyectada": sem_enf,
                        "Casos estimados": int(sub_enf["casos_enteros"].sum()),
                        "Municipios ≥ Medio": riesgo_act,
                    }
                )
            if filas:
                st.dataframe(pd.DataFrame(filas), hide_index=True, use_container_width=True)

    st.markdown("")
    izquierda, derecha = st.columns([1.2, 1])
    with izquierda:
        with st.container(border=True):
            st.markdown('<div class="panel-title">Semáforo por enfermedad</div>', unsafe_allow_html=True)
            for nombre, codigo, color, fondo in (
                ("Dengue", "dengue", "#b54755", "#f7e9eb"),
                ("Influenza", "influenza", "#bd9b43", "#f6f1df"),
                ("COVID-19", "covid", "#4e9577", "#e9f3ed"),
            ):
                if codigo_seleccionado and codigo != codigo_seleccionado:
                    continue
                sub = df[df["enfermedad"].str.lower() == codigo] if "enfermedad" in df else df
                riesgo_alto = int(sub["nivel_riesgo"].astype(str).str.lower().isin(["alto", "crítico"]).sum())
                riesgo_medio = int((sub["nivel_riesgo"].astype(str).str.lower() == "medio").sum())
                st.markdown(
                    f'<div class="overview-signal" style="--disease-color:{color};--disease-bg:{fondo}">'
                    f'<strong>{nombre}</strong><span>{riesgo_alto} en riesgo alto/crítico · {riesgo_medio} en riesgo medio</span></div>',
                    unsafe_allow_html=True,
                )
    with derecha:
        with st.container(border=True):
            st.markdown('<div class="panel-title">Alertas activas</div>', unsafe_allow_html=True)
            alertas = api.get_alerts(activa=True)
            if alertas:
                for alerta in alertas[:3]:
                    st.markdown(f"**{alerta.get('nivel', 'Alerta').upper()} · {alerta.get('municipio', 'Región')}**")
                    st.caption(alerta.get("mensaje", ""))
            else:
                st.caption("No hay alertas activas en este momento.")

    st.caption(
        "Las cifras estimadas son proyecciones estadísticas de apoyo a la vigilancia epidemiológica "
        "y no sustituyen la confirmación clínica o de laboratorio."
    )
