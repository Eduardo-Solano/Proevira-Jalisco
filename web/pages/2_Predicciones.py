"""
Página 2: Predicciones Temporales y Explicabilidad SHAP (Plotly).
"""

import os
import sys
import streamlit as st

# Resolver rutas para importación
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from views.predicciones import render_predicciones_view

st.set_page_config(page_title="Predicciones y SHAP - Jalisco", page_icon="📈", layout="wide")

if "auth_token" not in st.session_state:
    st.warning("⚠️ Debes iniciar sesión en la página principal.")
    st.stop()

render_predicciones_view()
