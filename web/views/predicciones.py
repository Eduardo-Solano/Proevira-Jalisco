"""
Vista: Predicciones Temporales y Explicabilidad SHAP.
"""

from datetime import date

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd

from api_client import api, MUNICIPIOS_JALISCO

ENFERMEDADES = {"dengue": "Dengue", "influenza": "Influenza", "covid-19": "COVID-19"}

DESCRIPCION_RIESGO = {
    "bajo": "La proyección está en el rango menor de casos para este municipio.",
    "medio": "La proyección está en un rango intermedio; mantén la vigilancia habitual.",
    "alto": "La proyección está en un rango elevado respecto al historial del municipio.",
    "crítico": "La proyección está en el rango más alto observado para este municipio.",
}

NOMBRES_VARIABLES = {
    "media_4s": "Promedio de casos de las últimas 4 semanas",
    "rmedia_4s": "Promedio de casos de las últimas 4 semanas",
    "media_8s": "Promedio de casos de las últimas 8 semanas",
    "rmedia_8s": "Promedio de casos de las últimas 8 semanas",
    "max_8s": "Máximo de casos en las últimas 8 semanas",
    "rmax_8s": "Máximo de casos en las últimas 8 semanas",
    "def_4s": "Defunciones en las últimas 4 semanas",
    "rdef_4s": "Defunciones en las últimas 4 semanas",
    "std_8s": "Variación de casos en las últimas 8 semanas",
    "tendencia": "Cambio de casos respecto a semanas anteriores",
    "rtend": "Cambio de casos respecto a semanas anteriores",
    "tendencia_rel": "Tendencia reciente de casos",
    "rtend_rel": "Tendencia reciente de casos",
    "sem_sin": "Estacionalidad de la semana",
    "sem_cos": "Estacionalidad de la semana",
    "mun_cod": "Municipio",
    "enfermedad_cod": "Enfermedad",
}


def _titulo(texto: str) -> None:
    st.markdown(f'<div class="panel-title">{texto}</div>', unsafe_allow_html=True)


def _riesgo_texto(valor) -> str:
    if valor is None:
        return "No disponible"
    return str(valor).capitalize()


def _fecha_semana(valor):
    if valor is None:
        return pd.NaT
    if isinstance(valor, str) and "-W" in valor:
        try:
            anio, semana = valor.split("-W", 1)
            return pd.Timestamp(date.fromisocalendar(int(anio), int(semana), 1))
        except ValueError:
            return pd.NaT
    return pd.to_datetime(valor, errors="coerce")


def _fecha_texto(valor) -> str:
    fecha = _fecha_semana(valor)
    if pd.isna(fecha):
        return "No disponible"
    return fecha.strftime("%d/%m/%Y")


def _nombre_variable(nombre: str) -> str:
    if nombre in NOMBRES_VARIABLES:
        return NOMBRES_VARIABLES[nombre]

    for prefijo in ("rlog_lag", "log_lag", "lag"):
        if nombre.startswith(prefijo) and nombre[len(prefijo):].isdigit():
            desfase = int(nombre[len(prefijo):])
            if desfase == 0:
                return "Casos de la semana más reciente"
            return f"Casos de hace {desfase} semana{'s' if desfase != 1 else ''}"

    prefijos_edad = ("rtasa_edad_", "tasa_edad_")
    for prefijo in prefijos_edad:
        if nombre.startswith(prefijo):
            edad = nombre[len(prefijo):].replace("_", "-")
            return f"Proporción de casos en población de {edad} años"

    return nombre.replace("_", " ").capitalize()


def render_predicciones_view():
    st.markdown(
        '<div class="page-heading">Proyección de casos</div>'
        '<div class="page-description">Compara los casos recientes con la estimación del modelo para un municipio y una enfermedad.</div>',
        unsafe_allow_html=True,
    )

    cobertura = st.radio(
        "Cobertura de la proyección",
        ["Municipio", "Región Centro"],
        horizontal=True,
        key="pred_coverage",
    )
    with st.container(border=True):
        _titulo("Elige qué consultar")
        f1, f2, f3, f4 = st.columns([1.2, 1, 1, 0.9])
        with f1:
            if cobertura == "Municipio":
                mun = st.selectbox(
                    "Municipio",
                    list(MUNICIPIOS_JALISCO.keys()),
                    format_func=lambda k: MUNICIPIOS_JALISCO[k]["nombre"],
                    key="pred_mun",
                )
            else:
                mun = None
                st.text_input("Municipios incluidos", "Los 12 municipios de la Región Centro", disabled=True)
        with f2:
            enf = st.selectbox(
                "Enfermedad",
                list(ENFERMEDADES.keys()),
                format_func=lambda x: ENFERMEDADES[x],
                key="pred_enf",
            )
        with f3:
            horizonte = st.selectbox(
                "Semanas a predecir",
                [1, 2, 3, 4],
                format_func=lambda n: f"{n} semana{'s' if n != 1 else ''}",
                key="pred_horizon",
            )
        with f4:
            st.markdown("<div style='height:1.75rem'></div>", unsafe_allow_html=True)
            if st.button("Actualizar datos", use_container_width=True, key="pred_refresh_btn"):
                api._clear_read_cache()
                st.rerun()

    es_region = cobertura == "Región Centro"
    nombre_municipio = "Región Centro" if es_region else MUNICIPIOS_JALISCO[mun]["nombre"]
    nombre_enfermedad = ENFERMEDADES.get(enf, enf.upper())

    if es_region:
        hist_data = api.get_region_prediction_history(enfermedad=enf, semanas=4, horizonte=horizonte)
        shap_data = {}
        metricas_modelo = None
    else:
        hist_data = api.get_prediction_history(mun, enfermedad=enf, semanas=4, horizonte=horizonte)
        shap_data = api.get_prediction_explain(mun, enfermedad=enf)
        metricas_modelo = api.get_model_metrics()
    model_info = api.get_model_info()

    df_h = pd.DataFrame(hist_data["historico"])
    df_p = pd.DataFrame(hist_data["prediccion"]).head(horizonte)
    predicciones = hist_data.get("prediccion", [])
    municipios_incluidos = hist_data.get("municipios_incluidos", 1)
    for frame in (df_h, df_p):
        if not frame.empty:
            frame["fecha"] = frame["semana"].map(_fecha_semana)

    # ── Resumen del pronóstico ──
    with st.container(border=True):
        titulo_resumen = (
            "Resumen de la próxima semana"
            if horizonte == 1
            else f"Resumen del pronóstico ({horizonte} semanas)"
        )
        _titulo(titulo_resumen)
        st.caption(
            f"{nombre_municipio} · {nombre_enfermedad} · "
            f"Horizonte seleccionado: {horizonte} semana{'s' if horizonte != 1 else ''}."
        )

        if df_p.empty:
            st.info(
                f"No hay suficientes datos históricos para calcular una proyección de "
                f"{nombre_enfermedad} en {nombre_municipio}."
            )
        else:
            forecast = df_p.iloc[0]
            casos_proyectados = float(forecast["casos"])
            casos_enteros = int(round(casos_proyectados))
            casos_por_semana = [int(round(float(v))) for v in df_p["casos"].tolist()]
            total_periodo = int(sum(casos_por_semana))
            sufijo_prox = "caso" if casos_enteros == 1 else "casos"

            cols = st.columns([1.15, 1.05, 1])
            if horizonte == 1:
                cols[0].metric(
                    "Casos en la región (1 semana)" if es_region else "Casos esperados (1 semana)",
                    f"{casos_enteros:,}",
                    help=(
                        "Suma entera de las proyecciones municipales para la próxima semana."
                        if es_region
                        else f"Casos enteros esperados para esa semana (promedio estadístico: {casos_proyectados:.2f})."
                    ),
                )
                cols[1].metric("Inicio de la semana", _fecha_texto(forecast.get("semana")))
            else:
                desglose_sem = ", ".join(str(v) for v in casos_por_semana)
                cols[0].metric(
                    f"Acumulado ({horizonte} semanas)",
                    f"{total_periodo:,}",
                    delta=f"Por semana: {desglose_sem}",
                    delta_color="off",
                    help=(
                        "Suma de los casos estimados de cada semana individual dentro del periodo seleccionado. "
                        f"Primera semana: {casos_enteros} {sufijo_prox}; última semana: {casos_por_semana[-1]}."
                    ),
                )
                cols[1].metric(
                    "Desde el",
                    _fecha_texto(df_p.iloc[0].get("semana")),
                    delta=f"Hasta el {_fecha_texto(df_p.iloc[-1].get('semana'))}",
                    delta_color="off",
                )
            if es_region:
                cols[2].metric("Municipios incluidos", str(municipios_incluidos))
            else:
                cols[2].metric(
                    "Nivel de riesgo esperado",
                    _riesgo_texto(forecast.get("nivel")),
                    help="Calculado frente al historial habitual de este municipio; no sustituye un aviso oficial.",
                )

            if not es_region:
                nivel = str(forecast.get("nivel", "")).lower()
                interpretacion = DESCRIPCION_RIESGO.get(nivel)
                if interpretacion:
                    st.caption(f"{interpretacion} Uso orientativo para vigilancia clínica.")

    # ── Curva epidemiológica ──
    with st.container(border=True):
        _titulo("Casos recientes y proyección")
        presentacion = st.radio(
            "Forma de visualizar",
            ["Líneas", "Barras", "Área"],
            horizontal=True,
            key="pred_chart_type",
        )

        if df_h.empty:
            st.info(f"No hay semanas observadas para {nombre_municipio} y {nombre_enfermedad}.")
        elif df_p.empty:
            st.info("No hay una proyección disponible para esta selección.")
        else:
            df_p = df_p.copy()
            df_p["casos"] = df_p["casos"].astype(float).round().astype(int)
            fig = go.Figure()
            nombre_observado = "Total regional observado" if es_region else "Casos observados"
            nombre_estimado = "Proyección regional" if es_region else "Casos estimados"
            if presentacion == "Barras":
                fig.add_trace(go.Bar(
                    x=df_h.fecha, y=df_h.casos,
                    name=nombre_observado, marker_color="#003366",
                ))
                fig.add_trace(go.Bar(
                    x=df_p.fecha, y=df_p.casos,
                    name=nombre_estimado, marker_color="#d32f2f",
                ))
                fig.update_layout(barmode="group")
            elif presentacion == "Área":
                fig.add_trace(go.Scatter(
                    x=df_h.fecha, y=df_h.casos,
                    mode="lines+markers", name=nombre_observado,
                    line=dict(color="#003366", width=3),
                    fill="tozeroy", fillcolor="rgba(0,51,102,0.12)",
                ))
                fig.add_trace(go.Scatter(
                    x=df_p.fecha, y=df_p.casos,
                    mode="lines+markers", name=nombre_estimado,
                    line=dict(color="#d32f2f", width=3, dash="dash"),
                    marker=dict(size=8, symbol="diamond", color="#d32f2f"),
                    fill="tozeroy", fillcolor="rgba(211,47,47,0.12)",
                ))
            else:
                fig.add_trace(go.Scatter(
                    x=df_h.fecha, y=df_h.casos,
                    mode="lines+markers", name=nombre_observado,
                    line=dict(color="#003366", width=3), marker=dict(size=6),
                ))
                fig.add_trace(go.Scatter(
                    x=[df_h.fecha.iloc[-1], df_p.fecha.iloc[0]],
                    y=[df_h.casos.iloc[-1], df_p.casos.iloc[0]],
                    mode="lines", line=dict(color="#d32f2f", width=2, dash="dot"), showlegend=False,
                ))
                fig.add_trace(go.Scatter(
                    x=df_p.fecha, y=df_p.casos,
                    mode="lines+markers", name=nombre_estimado,
                    line=dict(color="#d32f2f", width=3, dash="dash"),
                    marker=dict(size=8, symbol="diamond", color="#d32f2f"),
                ))
            fig.update_layout(
                xaxis_title="Inicio de semana", yaxis_title="Casos",
                template="plotly_white", hovermode="x unified", height=390,
                legend=dict(orientation="h", y=1.02, xanchor="right", x=1),
                margin=dict(l=10, r=10, t=20, b=10),
                yaxis=dict(rangemode="tozero", tickformat="d"),
            )
            fig.update_xaxes(tickformat="%d/%m/%Y", tickangle=-35)
            st.plotly_chart(fig, use_container_width=True)
            st.caption(
                (
                    "La cifra regional suma las predicciones municipales; no es un modelo regional independiente. "
                    if es_region
                    else ""
                )
                + "Las fechas corresponden al lunes de cada semana. Se muestran las últimas 4 semanas observadas. "
                "Azul: casos observados; rojo: "
                "estimaciones, no casos confirmados. Para semanas posteriores a la primera, el modelo "
                "usa su estimación anterior y pueden acumularse errores."
            )

            columnas_detalle = ["fecha", "casos"] + (["nivel"] if "nivel" in df_p else [])
            detalle = df_p[columnas_detalle].rename(
                columns={
                    "fecha": "Inicio de semana",
                    "casos": "Casos estimados",
                    "nivel": "Rango estimado",
                }
            )
            detalle["Inicio de semana"] = detalle["Inicio de semana"].map(_fecha_texto)
            detalle["Casos estimados"] = detalle["Casos estimados"].astype(float).round(0).astype(int)
            if "Rango estimado" in detalle:
                detalle["Rango estimado"] = detalle["Rango estimado"].astype(str).str.capitalize()
            st.markdown("**Estimación por semana**")
            st.dataframe(detalle, hide_index=True, use_container_width=True)

    # ── Factores explicativos claros ──
    if not es_region:
        with st.container(border=True):
            _titulo("Factores que más influyen en esta estimación")
            st.caption(
                "Indica qué señales clínicas e históricas tuvieron mayor peso para calcular la proyección."
            )

            df_shap = pd.DataFrame(shap_data.get("feature_importance", []))

            if df_p.empty:
                st.info("Se mostrarán factores cuando haya una proyección disponible.")
            elif df_shap.empty:
                st.info("No hay factores explicativos disponibles para mostrar.")
            else:
                df_shap["importancia"] = pd.to_numeric(df_shap["shap"], errors="coerce").abs()
                df_shap = df_shap.dropna(subset=["importancia"])
                df_shap["Variable"] = df_shap["feature"].map(_nombre_variable)
                df_shap = df_shap.groupby("Variable", as_index=False)["importancia"].sum()
                total_importancia = df_shap["importancia"].sum()
                if total_importancia <= 0:
                    st.info("No hay factores explicativos disponibles para mostrar.")
                else:
                    df_shap["Peso relativo"] = df_shap["importancia"] / total_importancia * 100
                    df_shap = df_shap.nlargest(6, "Peso relativo").sort_values("Peso relativo")
                    fig_s = px.bar(
                        df_shap,
                        x="Peso relativo",
                        y="Variable",
                        orientation="h",
                        labels={"Peso relativo": "Influencia relativa (%)", "Variable": ""},
                        text="Peso relativo",
                        color_discrete_sequence=["#4e9577"],
                    )
                    fig_s.update_traces(texttemplate="%{text:.0f}%", textposition="outside", cliponaxis=False)
                    fig_s.update_layout(
                        template="plotly_white",
                        height=max(260, len(df_shap) * 42),
                        margin=dict(l=10, r=50, t=10, b=10),
                        showlegend=False,
                        xaxis=dict(range=[0, float(df_shap["Peso relativo"].max()) * 1.25]),
                    )
                    st.plotly_chart(fig_s, use_container_width=True)

    # ── Referencia clínica y confiabilidad ──
    with st.expander("Confiabilidad histórica y fechas de actualización"):
        disease_key = "covid" if enf in ("covid-19", "covid") else enf
        info_enf = model_info.get("por_enfermedad", {}).get(disease_key, {}) if isinstance(model_info, dict) else {}
        ultima_obs_enf = info_enf.get("ultima_semana_datos") or model_info.get("ultima_semana_datos")

        if es_region:
            st.caption("Vista agregada de los 12 municipios de la Región Centro.")
        else:
            disease_block = (
                metricas_modelo.get("test", {}).get("municipal", {}).get(disease_key, {})
                if metricas_modelo
                else {}
            )
            test_metrics = disease_block.get("rf", disease_block.get("reparto", {}))
            muestras_evaluacion = disease_block.get("n")
            st.caption(
                f"Desempeño comprobado en semanas históricas de {nombre_enfermedad} en la Región Centro."
            )
            metric_cols = st.columns(3)
            metric_cols[0].metric(
                "Acierto en nivel de riesgo",
                f"{test_metrics['exactitud']*100:.0f}%" if "exactitud" in test_metrics else "No disponible",
                help="Porcentaje de semanas históricas donde la clasificación de riesgo coincidió con lo observado.",
            )
            metric_cols[1].metric(
                "Variación habitual por semana",
                f"±{test_metrics['mae']:.1f} casos" if "mae" in test_metrics else "No disponible",
                help="Diferencia promedio semanal entre lo proyectado y los casos confirmados.",
            )
            metric_cols[2].metric(
                "Semanas evaluadas",
                f"{muestras_evaluacion:,}" if muestras_evaluacion is not None else "No disponible",
            )

        data_col, forecast_col = st.columns(2)
        data_col.metric("Última semana clínica registrada", _fecha_texto(ultima_obs_enf))
        forecast_col.metric(
            "Última semana del horizonte",
            _fecha_texto(predicciones[-1]["semana"]) if predicciones else "No disponible",
        )

    st.caption(
        "Los casos y niveles mostrados son estimaciones, no casos confirmados ni alertas oficiales."
    )
