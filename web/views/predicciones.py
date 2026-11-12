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
        horizonte = st.selectbox("Horizonte de predicción", [1, 2, 3, 4], index=3, format_func=lambda n: f"{n} semana{'s' if n != 1 else ''}", key="pred_horizon")

    semanas = st.slider("Semanas históricas para comparar", 8, 24, 12, 2, key="pred_sem")

    hist_data = api.get_prediction_history(mun, enfermedad=enf, semanas=semanas)
    shap_data = api.get_prediction_explain(mun)
    st.markdown("#### Modelo y horizonte")
    model_col, training_col, updated_col = st.columns(3)
    model_col.metric("Modelo", "Random Forest")
    training_col.metric("Periodo de entrenamiento", "No disponible")
    updated_col.metric("Última actualización", "No disponible")
    st.caption(
        "La fuente conectada no expone fechas de entrenamiento/actualización ni intervalos de confianza."
    )

    # ── Curva epidemiológica ──
    st.markdown("#### Casos históricos y proyección")

    df_h = pd.DataFrame(hist_data["historico"])
    df_p = pd.DataFrame(hist_data["prediccion"]).head(horizonte)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_h.semana, y=df_h.casos,
        mode="lines+markers", name="Histórico reportado",
        line=dict(color="#003366", width=3), marker=dict(size=6),
    ))
    # Línea de conexión
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
    st.caption("La línea continua representa valores históricos; la línea discontinua son proyecciones, no casos confirmados.")

    # ── Métricas disponibles ──
    st.markdown("#### Evaluación del modelo")
    evaluacion = st.columns(4)
    for columna, metrica in zip(evaluacion, ("R²", "MAE", "RMSE", "Otras métricas")):
        columna.metric(metrica, "No disponible")
    st.caption("La API actual no proporciona métricas de evaluación ni escenarios comparativos.")

    # ── SHAP ──
    st.markdown("#### Factores explicativos (SHAP)")
    st.caption("Contribución de cada variable al nivel de riesgo predicho por el modelo.")

    col_chart, col_info = st.columns([3, 2])

    df_shap = pd.DataFrame(shap_data["feature_importance"])

    with col_chart:
        fig_s = px.bar(
            df_shap.sort_values("shap", ascending=True),
            x="shap", y="feature", orientation="h",
            labels={"shap": "Valor SHAP", "feature": ""},
            color="impacto",
            color_discrete_map={"Aumenta riesgo": "#d32f2f", "Disminuye riesgo": "#2e7d32"},
        )
        fig_s.update_layout(
            template="plotly_white", height=320,
            margin=dict(l=10, r=10, t=10, b=10),
            legend=dict(orientation="h", y=1.06, xanchor="right", x=1),
        )
        st.plotly_chart(fig_s, use_container_width=True)

    with col_info:
        st.markdown(f"""
        **{MUNICIPIOS_JALISCO[mun]['nombre']}**

        - **Mayor factor de riesgo:** Precipitación pluvial acumulada y rezago de casos confirmados.
        - **Factor protector:** Operativos activos de control de vectores y fumigación.

        *Acción sugerida:* Reforzar vigilancia en unidades de primer nivel y muestreo intensivo en pacientes febriles.
        """)
