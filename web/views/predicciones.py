"""
Vista: Predicciones Temporales y Explicabilidad SHAP.
"""

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from api_client import api, MUNICIPIOS_JALISCO


def render_predicciones_view():
    # ── Filtros ──
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
            "Patología",
            ["dengue", "influenza", "covid-19"],
            format_func=lambda x: {"dengue": "Dengue", "influenza": "Influenza", "covid-19": "COVID-19"}[x],
            key="pred_enf",
        )

    with f3:
        semanas = st.slider("Semanas históricas", 8, 24, 12, 2, key="pred_sem")

    st.markdown("---")

    hist_data = api.get_prediction_history(mun, enfermedad=enf, semanas=semanas)
    shap_data = api.get_prediction_explain(mun)

    # ── Curva epidemiológica ──
    st.markdown("##### Tendencia histórica y proyección a 4 semanas")

    df_h = pd.DataFrame(hist_data["historico"])
    df_p = pd.DataFrame(hist_data["prediccion"])

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_h.semana, y=df_h.casos,
        mode="lines+markers", name="Observado",
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
        mode="lines+markers", name="Proyección (Random Forest)",
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

    st.markdown("---")

    # ── SHAP ──
    st.markdown("##### Factores determinantes del riesgo (SHAP)")
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
