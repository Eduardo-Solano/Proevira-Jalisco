"""
Página 3: Consola de Alertas Epidemiológicas.
"""

import os
import sys
import streamlit as st

# Resolver rutas para importación
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from views.alertas import render_alertas_view

st.set_page_config(page_title="Consola de Alertas - Jalisco", page_icon="🚨", layout="wide")

from browser_session import restore_browser_session, watch_session_expiry

restore_browser_session()
if "auth_token" not in st.session_state:
    st.warning("⚠️ Debes iniciar sesión en la página principal.")
    st.stop()

watch_session_expiry()

render_alertas_view()
