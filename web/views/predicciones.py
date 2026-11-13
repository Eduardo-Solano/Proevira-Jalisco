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

    # ── Filtros ──
    with st.container(border=True):
        _titulo("Elige qué consultar")
        f1, f2, f3 = st.columns(3)
        with f1:
            mun = st.selectbox(
                "Municipio",
                list(MUNICIPIOS_JALISCO.keys()),
                format_func=lambda k: MUNICIPIOS_JALISCO[k]["nombre"],
                key="pred_mun",
            )
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

    nombre_municipio = MUNICIPIOS_JALISCO[mun]["nombre"]
    nombre_enfermedad = ENFERMEDADES.get(enf, enf.upper())

    hist_data = api.get_prediction_history(mun, enfermedad=enf, semanas=4, horizonte=horizonte)
    shap_data = api.get_prediction_explain(mun, enfermedad=enf)
    model_info = api.get_model_info()
    metricas_modelo = api.get_model_metrics()

    df_h = pd.DataFrame(hist_data["historico"])
    df_p = pd.DataFrame(hist_data["prediccion"]).head(horizonte)
    predicciones = hist_data.get("prediccion", [])
    for frame in (df_h, df_p):
        if not frame.empty:
            frame["fecha"] = frame["semana"].map(_fecha_semana)

    # ── Resumen del pronóstico ──
    with st.container(border=True):
        _titulo("Estimación para la primera semana")
        st.caption(
            f"{nombre_municipio} · {nombre_enfermedad} · "
            f"Pronóstico de {horizonte} semana{'s' if horizonte != 1 else ''}; "
            "las tarjetas muestran la primera."
        )

        if df_p.empty:
            st.info(
                f"No hay suficientes datos históricos para calcular una proyección de "
                f"{nombre_enfermedad} en {nombre_municipio}."
            )
        else:
            forecast = df_p.iloc[0]
            casos_proyectados = float(forecast["casos"])

            cols = st.columns(3)
            cols[0].metric(
                "Casos estimados",
                f"{casos_proyectados:,.1f}",
                help="Estimación del modelo para la primera semana del horizonte.",
            )
            cols[1].metric("Fecha estimada", _fecha_texto(forecast.get("semana")))
            cols[2].metric(
                "Rango estimado",
                _riesgo_texto(forecast.get("nivel")),
                help="Rango calculado con umbrales históricos de este municipio; no es una alerta oficial.",
            )

            nivel = str(forecast.get("nivel", "")).lower()
            interpretacion = DESCRIPCION_RIESGO.get(nivel)
            if interpretacion:
                st.caption(f"{interpretacion} No es una alerta oficial.")

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
            fig = go.Figure()
            if presentacion == "Barras":
                fig.add_trace(go.Bar(
                    x=df_h.fecha, y=df_h.casos,
                    name="Casos observados", marker_color="#003366",
                ))
                fig.add_trace(go.Bar(
                    x=df_p.fecha, y=df_p.casos,
                    name="Casos estimados", marker_color="#d32f2f",
                ))
                fig.update_layout(barmode="group")
            elif presentacion == "Área":
                fig.add_trace(go.Scatter(
                    x=df_h.fecha, y=df_h.casos,
                    mode="lines+markers", name="Casos observados",
                    line=dict(color="#003366", width=3),
                    fill="tozeroy", fillcolor="rgba(0,51,102,0.12)",
                ))
                fig.add_trace(go.Scatter(
                    x=df_p.fecha, y=df_p.casos,
                    mode="lines+markers", name="Casos estimados",
                    line=dict(color="#d32f2f", width=3, dash="dash"),
                    marker=dict(size=8, symbol="diamond", color="#d32f2f"),
                    fill="tozeroy", fillcolor="rgba(211,47,47,0.12)",
                ))
            else:
                fig.add_trace(go.Scatter(
                    x=df_h.fecha, y=df_h.casos,
                    mode="lines+markers", name="Casos observados",
                    line=dict(color="#003366", width=3), marker=dict(size=6),
                ))
                fig.add_trace(go.Scatter(
                    x=[df_h.fecha.iloc[-1], df_p.fecha.iloc[0]],
                    y=[df_h.casos.iloc[-1], df_p.casos.iloc[0]],
                    mode="lines", line=dict(color="#d32f2f", width=2, dash="dot"), showlegend=False,
                ))
                fig.add_trace(go.Scatter(
                    x=df_p.fecha, y=df_p.casos,
                    mode="lines+markers", name="Casos estimados",
                    line=dict(color="#d32f2f", width=3, dash="dash"),
                    marker=dict(size=8, symbol="diamond", color="#d32f2f"),
                ))
            fig.update_layout(
                xaxis_title="Fecha de inicio de semana", yaxis_title="Casos",
                template="plotly_white", hovermode="x unified", height=390,
                legend=dict(orientation="h", y=1.02, xanchor="right", x=1),
                margin=dict(l=10, r=10, t=20, b=10),
            )
            fig.update_xaxes(tickformat="%d/%m/%Y", tickangle=-35)
            st.plotly_chart(fig, use_container_width=True)
            st.caption(
                "Las fechas corresponden al lunes de cada semana. Se muestran las últimas 4 semanas observadas. "
                "Azul: casos observados; rojo: "
                "estimaciones, no casos confirmados. Para semanas posteriores a la primera, el modelo "
                "usa su estimación anterior y pueden acumularse errores."
            )

            if "nivel" in df_p:
                detalle = df_p[["fecha", "casos", "nivel"]].rename(
                    columns={"fecha": "Inicio de semana", "casos": "Casos estimados", "nivel": "Rango estimado"}
                )
                detalle["Inicio de semana"] = detalle["Inicio de semana"].map(_fecha_texto)
                detalle["Casos estimados"] = detalle["Casos estimados"].astype(float).round(1)
                detalle["Rango estimado"] = detalle["Rango estimado"].astype(str).str.capitalize()
                st.markdown("**Estimación por semana**")
                st.dataframe(detalle, hide_index=True, use_container_width=True)

    # ── Variables del modelo ──
    with st.container(border=True):
        _titulo("Variables más importantes del modelo")
        st.caption(
            "Resumen global del modelo: muestra qué variables aportan más, no qué causó "
            "la proyección de este municipio ni si una variable aumenta o reduce los casos."
        )

        df_shap = pd.DataFrame(shap_data.get("feature_importance", []))

        if df_p.empty:
            st.info("Se mostrarán variables cuando haya una proyección disponible.")
        elif df_shap.empty:
            st.info("No hay información de importancia de variables para mostrar.")
        else:
            df_shap["importancia"] = pd.to_numeric(df_shap["shap"], errors="coerce").abs()
            df_shap = df_shap.dropna(subset=["importancia"])
            df_shap["Variable"] = df_shap["feature"].map(_nombre_variable)
            df_shap = df_shap.groupby("Variable", as_index=False)["importancia"].sum()
            total_importancia = df_shap["importancia"].sum()
            if total_importancia <= 0:
                st.info("No hay información de importancia de variables para mostrar.")
            else:
                df_shap["Importancia relativa"] = df_shap["importancia"] / total_importancia * 100
                df_shap = df_shap.nlargest(8, "Importancia relativa").sort_values("Importancia relativa")
                fig_s = px.bar(
                    df_shap,
                    x="Importancia relativa",
                    y="Variable",
                    orientation="h",
                    labels={"Importancia relativa": "Importancia relativa (%)", "Variable": ""},
                    text="Importancia relativa",
                    color_discrete_sequence=["#4e9577"],
                )
                fig_s.update_traces(texttemplate="%{text:.1f}%", textposition="outside", cliponaxis=False)
                fig_s.update_layout(
                    template="plotly_white",
                    height=max(300, len(df_shap) * 42),
                    margin=dict(l=10, r=50, t=10, b=10),
                    showlegend=False,
                    xaxis=dict(range=[0, float(df_shap["Importancia relativa"].max()) * 1.25]),
                )
                st.plotly_chart(fig_s, use_container_width=True)

    # ── Detalles técnicos opcionales ──
    with st.expander("Métricas y detalles técnicos"):
        disease_key = "covid" if enf in ("covid-19", "covid") else enf
        disease_block = (
            metricas_modelo.get("test", {}).get("municipal", {}).get(disease_key, {})
            if metricas_modelo
            else {}
        )
        test_metrics = disease_block.get("rf", disease_block.get("reparto", {}))
        muestras_evaluacion = disease_block.get("n")
        st.caption(
            "Evaluación general del modelo en semanas históricas separadas para prueba; "
            "no mide la precisión de esta proyección en particular."
        )
        metric_cols = st.columns(4)
        metric_cols[0].metric(
            "Error promedio (MAE)",
            f"{test_metrics['mae']:.3f}" if "mae" in test_metrics else "No disponible",
            help="Diferencia absoluta promedio entre la estimación y los casos observados. Menor es mejor.",
        )
        metric_cols[1].metric(
            "Error con penalización (RMSE)",
            f"{test_metrics['rmse']:.3f}" if "rmse" in test_metrics else "No disponible",
            help="Penaliza más los errores grandes. Menor es mejor.",
        )
        metric_cols[2].metric(
            "Clasificación de riesgo (F1)",
            f"{test_metrics['f1_macro']:.3f}" if "f1_macro" in test_metrics else "No disponible",
            help="Resume el equilibrio del modelo al clasificar niveles de riesgo. Más cercano a 1 es mejor.",
        )
        metric_cols[3].metric(
            "Registros evaluados",
            f"{muestras_evaluacion:,}" if muestras_evaluacion is not None else "No disponible",
        )

        split = metricas_modelo.get("split", {}) if metricas_modelo else {}
        corte = split.get("por_enfermedad", {}).get(disease_key, {}).get("corte_test") or split.get("corte_test", "No disponible")
        st.caption(f"Enfermedad: {nombre_enfermedad} · Corte de prueba: {corte}.")
        st.markdown("**Datos del modelo**")
        modelo_col, data_col, training_col, forecast_col = st.columns(4)
        modelo_col.metric("Modelo", model_info.get("modelo", "Random Forest"))
        data_col.metric("Última fecha observada", _fecha_texto(model_info.get("ultima_semana_datos")))
        training_col.metric("Entrenamiento", model_info.get("fecha_entrenamiento") or "No disponible")
        forecast_col.metric(
            "Última fecha del horizonte",
            _fecha_texto(predicciones[-1]["semana"]) if predicciones else "No disponible",
        )

    st.caption(
        "Los casos y niveles mostrados son estimaciones, no casos confirmados ni alertas oficiales."
    )
