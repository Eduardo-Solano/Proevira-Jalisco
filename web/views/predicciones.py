"""
Vista: Predicciones Temporales y Explicabilidad SHAP.
"""

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from api_client import api, MUNICIPIOS_JALISCO


def render_predicciones_view():
    st.markdown(
        '<div class="page-heading">Análisis predictivo</div>'
        '<div class="page-description">Consulta las proyecciones y explicabilidad disponibles para cada municipio.</div>',
        unsafe_allow_html=True,
    )

    # ── Filtros ──
    f1, f2, f3 = st.columns(3)
    with f1:
        mun = st.selectbox(
            "Región geográfica",
            list(MUNICIPIOS_JALISCO.keys()),
            format_func=lambda k: MUNICIPIOS_JALISCO[k]["nombre"],
            key="pred_mun",
        )

    with f2:
        enf = st.selectbox(
            "Enfermedad",
            ["dengue", "influenza", "covid-19"],
            format_func=lambda x: {"dengue": "Dengue", "influenza": "Influenza", "covid-19": "COVID-19"}[x],
            key="pred_enf",
        )

    with f3:
        horizonte = st.selectbox(
            "Semanas a predecir",
            [1, 2, 3, 4],
            format_func=lambda n: f"{n} semana{'s' if n != 1 else ''}",
            key="pred_horizon",
        )

    hist_data = api.get_prediction_history(mun, enfermedad=enf, semanas=4, horizonte=horizonte)
    shap_data = api.get_prediction_explain(mun, enfermedad=enf)
    model_info = api.get_model_info()
    metricas_modelo = api.get_model_metrics()
    predicciones = hist_data.get("prediccion", [])
    st.markdown("#### Modelo y horizonte")
    model_col, data_col, training_col, forecast_col = st.columns(4)
    model_col.metric("Modelo", model_info.get("modelo", "Random Forest"))
    data_col.metric("Última semana observada", model_info.get("ultima_semana_datos") or "No disponible")
    training_col.metric("Entrenamiento", model_info.get("fecha_entrenamiento") or "No disponible")
    forecast_col.metric(
        "Última semana proyectada",
        predicciones[-1]["semana"] if predicciones else "No disponible",
    )

    # ── Curva epidemiológica ──
    st.markdown("#### Casos históricos y proyección")

    df_h = pd.DataFrame(hist_data["historico"])
    df_p = pd.DataFrame(hist_data["prediccion"]).head(horizonte)

    if df_h.empty:
        st.info("No hay semanas históricas disponibles para la región y enfermedad seleccionadas.")
    elif df_p.empty:
        st.info("El backend no devolvió una proyección para esta selección.")
    else:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df_h.semana, y=df_h.casos,
            mode="lines+markers", name="Casos históricos observados",
            line=dict(color="#003366", width=3), marker=dict(size=6),
        ))
        fig.add_trace(go.Scatter(
            x=[df_h.semana.iloc[-1], df_p.semana.iloc[0]],
            y=[df_h.casos.iloc[-1], df_p.casos.iloc[0]],
            mode="lines", line=dict(color="#d32f2f", width=2, dash="dot"), showlegend=False,
        ))
        fig.add_trace(go.Scatter(
            x=df_p.semana, y=df_p.casos,
            mode="lines+markers", name="Proyección (no confirmada)",
            line=dict(color="#d32f2f", width=3, dash="dash"),
            marker=dict(size=8, symbol="diamond", color="#d32f2f"),
        ))
        fig.update_layout(
            xaxis_title="Semana epidemiológica", yaxis_title="Casos",
            template="plotly_white", hovermode="x unified", height=370,
            legend=dict(orientation="h", y=1.02, xanchor="right", x=1),
            margin=dict(l=10, r=10, t=20, b=10),
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption(
            "Se muestran las últimas 4 semanas observadas y la proyección solicitada. "
            "Las proyecciones posteriores a la primera son recursivas: actualizan casos y semana, "
            "y mantienen fijos los indicadores de defunciones y edades del último dato. No son casos confirmados."
        )

    # ── Métricas disponibles ──
    st.markdown("#### Evaluación del modelo")
    disease_key = "covid" if enf == "covid-19" else enf
    test_metrics = (
        metricas_modelo.get("test", {})
        .get("municipal", {})
        .get(disease_key, {})
        .get("reparto", {})
        if metricas_modelo
        else {}
    )
    muestras_evaluacion = (
        metricas_modelo.get("test", {}).get("municipal", {}).get(disease_key, {}).get("n")
        if metricas_modelo
        else None
    )
    metric_cols = st.columns(4)
    metric_cols[0].metric("MAE", f"{test_metrics['mae']:.3f}" if "mae" in test_metrics else "No disponible")
    metric_cols[1].metric("RMSE", f"{test_metrics['rmse']:.3f}" if "rmse" in test_metrics else "No disponible")
    metric_cols[2].metric("F1 macro", f"{test_metrics['f1_macro']:.3f}" if "f1_macro" in test_metrics else "No disponible")
    metric_cols[3].metric(
        "Muestras de evaluación",
        f"{muestras_evaluacion:,}" if muestras_evaluacion is not None else "No disponible",
    )
    split = metricas_modelo.get("split", {}) if metricas_modelo else {}
    st.caption(
        f"Métricas de reparto municipal en el conjunto de prueba; corte temporal: "
        f"{split.get('corte_test', 'No disponible')}. No se generan escenarios ni intervalos de confianza."
    )

    # ── SHAP ──
    st.markdown("#### Factores explicativos (SHAP)")
    st.caption("Importancia global de las variables del modelo; el servicio no devuelve el efecto local de cada variable.")

    col_chart, col_info = st.columns([3, 2])

    df_shap = pd.DataFrame(shap_data.get("feature_importance", []))

    with col_chart:
        if df_shap.empty:
            st.info("No hay importancias SHAP disponibles para mostrar.")
        else:
            fig_s = px.bar(
                df_shap.sort_values("shap", ascending=True),
                x="shap", y="feature", orientation="h",
                labels={"shap": "Importancia global SHAP", "feature": ""},
                color_discrete_sequence=["#4e9577"],
            )
            fig_s.update_layout(
                template="plotly_white", height=320,
                margin=dict(l=10, r=10, t=10, b=10),
                showlegend=False,
            )
            st.plotly_chart(fig_s, use_container_width=True)

    with col_info:
        if df_p.empty:
            st.info("No hay una proyección disponible para esta selección.")
        else:
            forecast = df_p.iloc[0]
            st.markdown(f"**{MUNICIPIOS_JALISCO[mun]['nombre']} · {enf.upper()}**")
            st.metric("Casos esperados (proyección)", f"{float(forecast['casos']):,.1f}")
            if "nivel" in forecast:
                st.metric("Nivel de riesgo proyectado", str(forecast["nivel"]).capitalize())
            st.caption("La importancia global SHAP no indica por sí sola si una variable aumenta o reduce el riesgo.")
