"""
Página 1: Mapa de Riesgo Epidemiológico Municipal (Folium).
"""

import os
import sys
import streamlit as st

# Resolver rutas para importación
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from views.mapa import render_mapa_view

st.set_page_config(page_title="Mapa de Riesgo - Jalisco", page_icon="🗺️", layout="wide")

if "auth_token" not in st.session_state:
    st.warning("⚠️ Debes iniciar sesión en la página principal.")
    st.stop()

render_mapa_view()
