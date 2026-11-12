"""Aplicación principal de PROEVIRA Jalisco."""
import base64
import os
import sys
import streamlit as st

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from views.resumen import render_resumen_view
from views.mapa import render_mapa_view
from views.predicciones import render_predicciones_view
from views.alertas import render_alertas_view
from auth_ui import render_auth_page
from api_client import DEMO_MODE

LOGO_PATH = os.path.join(BASE_DIR, "assets", "jalisco.png")
with open(LOGO_PATH, "rb") as logo_file:
    LOGO_BASE64 = base64.b64encode(logo_file.read()).decode("ascii")

# ── Configuración de página ──
st.set_page_config(
    page_title="PROEVIRA Jalisco",
    page_icon=LOGO_PATH,
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Estilos globales ──
st.markdown("""
<style>
:root { font-family: "Segoe UI", "Aptos", sans-serif; }
.stApp, .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp p,
.stApp label, .stApp input, .stApp textarea, .stApp button {
    font-family: "Segoe UI", "Aptos", sans-serif !important;
}
[data-testid="stSidebarNav"] { display: none !important; }
[data-testid="stAppDeployButton"], [data-testid="stMainMenu"] { display: none !important; }
[data-testid="stAppViewContainer"], .stApp { background: #f5f7f5; }
[data-testid="stMainBlockContainer"] {
    max-width: none;
    padding: 4rem 1.7rem 1rem;
}
section[data-testid="stSidebar"] {
    background: #183f46;
    border-right: 1px solid #14373d;
}
section[data-testid="stSidebar"]:has(button[aria-label="Collapse sidebar"]) {
    width: 260px !important;
    min-width: 260px !important;
    flex-basis: 260px !important;
}
section[data-testid="stSidebar"] > div { background: #183f46; }
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p { color: #eaf1ee; }
button[aria-label="Collapse sidebar"],
button[aria-label="Expand sidebar"] {
    visibility: visible !important;
    opacity: 1 !important;
    color: #477a70 !important;
}
section[data-testid="stSidebar"] button[aria-label="Collapse sidebar"] {
    color: #d3e2dd !important;
}
.sidebar-brand {
    padding: .2rem 0 1.05rem;
    border-bottom: 1px solid rgba(255,255,255,.16);
    color: #f0b65c;
    font-size: 1.02rem;
    font-weight: 700;
    letter-spacing: .1px;
}
.sidebar-brand span {
    display: block;
    margin-top: .25rem;
    color: #b7ceca;
    font-size: .68rem;
    font-weight: 500;
    letter-spacing: .4px;
}
.sidebar-section {
    margin: 1.35rem 0 .45rem;
    color: #a9c1bc;
    font-size: .66rem;
    font-weight: 700;
    letter-spacing: .8px;
    text-transform: uppercase;
}
section[data-testid="stSidebar"] div[data-testid="stRadio"] {
    padding: 0 !important;
}
section[data-testid="stSidebar"] div[data-testid="stRadio"] > div[role="radiogroup"] {
    gap: .22rem;
}
section[data-testid="stSidebar"] label[data-testid="stRadioOption"] > div > div:first-child {
    display: none !important;
}
section[data-testid="stSidebar"] div[data-testid="stRadio"] label {
    min-height: 40px;
    padding: .55rem .8rem;
    border: 0;
    border-radius: 7px;
    color: #eaf1ee;
    transition: background .15s ease, color .15s ease;
}
section[data-testid="stSidebar"] div[data-testid="stRadio"] label:hover {
    background: rgba(255,255,255,.09);
    color: #fff;
}
section[data-testid="stSidebar"] div[data-testid="stRadio"] label[data-selected="true"] {
    background: #2c5c5c;
    color: #fff;
}
section[data-testid="stSidebar"] div[data-testid="stRadio"] label p {
    color: inherit !important;
    font-size: .88rem;
    font-weight: 550;
}
.st-key-map_modo div[role="radiogroup"] { gap: .4rem; }
.st-key-map_modo label[data-testid="stRadioOption"] > div > div:first-child {
    display: none !important;
}
.st-key-map_modo label[data-testid="stRadioOption"] {
    min-height: 34px;
    padding: .38rem .68rem;
    border: 1px solid #dfe7e2;
    border-radius: 99px;
    background: #fff;
    color: #64746e;
}
.st-key-map_modo label[data-testid="stRadioOption"][data-selected="true"] {
    border-color: #bed4c8;
    background: #eaf3ed;
    color: #315d53;
}
.sidebar-footer {
    position: fixed;
    bottom: 4.5rem;
    width: 208px;
    padding-top: .8rem;
    border-top: 1px solid rgba(255,255,255,.16);
    color: #b7ceca;
    font-size: .72rem;
    line-height: 1.5;
}
.sidebar-footer strong {
    display: block;
    color: #fff;
    font-size: .8rem;
}
.st-key-sidebar_exit { position: fixed; bottom: .8rem; width: 208px; }
.st-key-sidebar_exit button {
    width: 100%;
    justify-content: flex-start;
    border: 1px solid rgba(255,255,255,.2);
    color: #eaf1ee;
    background: transparent;
}
.st-key-sidebar_exit button:hover {
    border-color: #e0a878;
    color: #fff;
    background: rgba(255,255,255,.08);
}
.exit-card {
    max-width: 560px;
    margin: 16vh auto 1rem;
    padding: 2rem;
    border: 1px solid #e1e8e2;
    border-radius: 12px;
    background: #fff;
    text-align: center;
}
.exit-card h1 {
    margin: .7rem 0 .35rem;
    color: #244b4b;
    font-size: 1.4rem;
}
.exit-card p { color: #74857f; font-size: .9rem; }
.exit-mark {
    display: grid;
    width: 42px;
    height: 42px;
    margin: auto;
    place-items: center;
    border-radius: 50%;
    background: #e8f2ed;
    color: #4d8578;
    font-size: 1.2rem;
}
.topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    min-height: 70px;
    margin-bottom: .95rem;
    padding: 0 0 .7rem;
    border-bottom: 1px solid #dfe7e2;
}
.topbar-title {
    color: #244b4b;
    font-size: 1.08rem;
    font-weight: 700;
    letter-spacing: -.2px;
}
.topbar-subtitle {
    margin-top: .12rem;
    color: #758781;
    font-size: .76rem;
}
.topbar-agency {
    display: flex;
    justify-content: flex-end;
    align-items: center;
}
.topbar-logo {
    display: block;
    width: 168px;
    max-height: 52px;
    object-fit: contain;
}
.page-heading {
    margin: .15rem 0 .3rem;
    color: #244b4b;
    font-size: 1.35rem;
    font-weight: 700;
    letter-spacing: -.3px;
}
.page-description {
    margin: 0 0 .9rem;
    color: #74857f;
    font-size: .82rem;
}
.risk-legend {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: .55rem 1.15rem;
    margin: .15rem 0 .85rem;
    padding: .65rem .85rem;
    border: 1px solid #e1e8e2;
    border-radius: 8px;
    background: #fff;
}
.risk-legend-title {
    margin-right: .25rem;
    color: #526861;
    font-size: .76rem;
    font-weight: 650;
}
.risk-legend-item {
    display: flex;
    align-items: center;
    gap: .4rem;
    color: #64746e;
    font-size: .75rem;
}
.risk-dot, .status-dot {
    flex: 0 0 9px;
    width: 9px;
    height: 9px;
    border-radius: 50%;
}
.heat-scale {
    width: 112px;
    height: 8px;
    border-radius: 99px;
    background: linear-gradient(90deg, #4e9577, #e5c76d, #d17d45, #b54755);
}
.risk-legend-note {
    margin-left: auto;
    color: #8a9992;
    font-size: .7rem;
}
.municipal-table {
    width: 100%;
    border-collapse: collapse;
    color: #425852;
    font-size: .78rem;
}
.municipal-table-wrap { max-height: 480px; overflow: auto; }
.municipal-table td:first-child { width: 48%; }
.municipal-table td:last-child, .municipal-table th:last-child { width: 25%; }
.municipal-table th {
    padding: .55rem .35rem;
    border-bottom: 1px solid #e3eae5;
    color: #87958f;
    font-size: .68rem;
    font-weight: 600;
    text-align: left;
}
.municipal-table td {
    padding: .56rem .35rem;
    border-bottom: 1px solid #edf1ed;
    vertical-align: middle;
}
.municipal-table tr:last-child td { border-bottom: 0; }
.risk-pill {
    display: inline-flex;
    align-items: center;
    gap: .35rem;
    padding: .2rem .48rem;
    border-radius: 99px;
    font-size: .67rem;
    font-weight: 650;
    text-transform: capitalize;
    white-space: nowrap;
}
.case-track {
    width: 100%;
    min-width: 42px;
    height: 5px;
    overflow: hidden;
    border-radius: 99px;
    background: #edf1ed;
}
.case-track span {
    display: block;
    height: 100%;
    border-radius: inherit;
}
.panel-title {
    color: #345650;
    font-size: .93rem;
    font-weight: 650;
}
.stDownloadButton button {
    border-color: #d6e2dc;
    color: #315d53;
    font-weight: 600;
}
.stDataFrame [data-testid="stElementToolbar"] { display: none !important; }
.disease-card {
    min-height: 190px;
    padding: 1.15rem;
    border: 1px solid #e1e8e2;
    border-top: 3px solid var(--disease-color);
    border-radius: 10px;
    background: #fff;
}
.disease-heading { display: flex; align-items: center; gap: .65rem; }
.disease-heading h2 {
    margin: 0;
    color: #31544e;
    font-size: 1rem;
    font-weight: 650;
}
.disease-symbol {
    width: 11px;
    height: 11px;
    border: 3px solid var(--disease-color);
    border-radius: 50%;
}
.disease-card p {
    min-height: 62px;
    margin: .85rem 0 1rem;
    color: #6d7e77;
    font-size: .82rem;
    line-height: 1.55;
}
.disease-status {
    display: inline-flex;
    align-items: center;
    gap: .4rem;
    padding: .3rem .6rem;
    border-radius: 99px;
    font-size: .72rem;
    font-weight: 650;
}
.overview-note {
    display: flex;
    flex-wrap: wrap;
    gap: .35rem .7rem;
    margin-top: 1.2rem;
    padding: .85rem 1rem;
    border: 1px solid #e1e8e2;
    border-radius: 8px;
    background: #fff;
    color: #71817a;
    font-size: .78rem;
}
.overview-note strong { color: #31544e; font-weight: 650; }
.metric-card {
    background: #fff;
    border: 1px solid #e1e8e2;
    border-top: 3px solid #4d8578;
    border-radius: 9px;
    padding: .9rem 1rem;
}
.metric-val { margin: 0; color: #315f55; font-size: 1.25rem; font-weight: 700; }
.metric-label {
    color: #667971;
    font-size: .76rem;
    font-weight: 600;
}
.metric-sub { margin-top: 3px; color: #84918b; font-size: .72rem; }
.disclaimer-box {
    margin-top: 2rem;
    padding: .7rem 1rem;
    border-left: 3px solid #d2a65e;
    border-radius: 5px;
    background: #fcf8ef;
    color: #78643d;
    font-size: .78rem;
}
.footer {
    margin-top: 1.3rem;
    padding: .8rem 0 .3rem;
    border-top: 1px solid #dfe7e2;
    color: #8a9992;
    font-size: .72rem;
    text-align: center;
}
div[data-testid="stSelectbox"] label,
div[data-testid="stRadio"] label,
div[data-testid="stSlider"] label { color: #526861; font-weight: 600; }
@media (max-width: 760px) {
    [data-testid="stMainBlockContainer"] { padding: 3.6rem .85rem .9rem; }
    .topbar { align-items: flex-start; }
    .topbar-logo { width: 126px; max-height: 42px; }
    .sidebar-footer { position: static; width: auto; margin-top: 2rem; }
    .st-key-sidebar_exit { position: static; width: auto; }
    .risk-legend-note { width: 100%; margin-left: 0; }
}
</style>
""", unsafe_allow_html=True)

NAV = ["◫   Resumen", "⌖   Mapa de riesgo", "↗   Predicciones", "!   Alertas"]

if DEMO_MODE and st.session_state.get("demo_exit"):
    st.markdown("""
    <div class="exit-card">
        <div class="exit-mark">✓</div>
        <h1>Panel cerrado</h1>
        <p>La demostración terminó. Puedes volver a abrir el panel cuando quieras.</p>
    </div>
    """, unsafe_allow_html=True)
    if st.button("Volver al panel"):
        st.session_state["demo_exit"] = False
        st.rerun()
elif not DEMO_MODE and not st.session_state.get("auth_token"):
    st.markdown(
        "<style>section[data-testid='stSidebar']{display:none!important}</style>",
        unsafe_allow_html=True,
    )
    render_auth_page()
else:
    with st.sidebar:
        st.markdown(
            '<div class="sidebar-brand">PROEVIRA<span>Salud pública · Jalisco</span></div>',
            unsafe_allow_html=True,
        )
        st.markdown('<div class="sidebar-section">Menú principal</div>', unsafe_allow_html=True)
        seccion = st.radio(
            "Navegación",
            NAV,
            index=1,
            label_visibility="collapsed",
            key="main_navigation",
        )
        st.markdown(
            '<div class="sidebar-footer"><strong>Gobierno de Jalisco</strong>'
            'Secretaría de Salud<br>Vigilancia epidemiológica</div>',
            unsafe_allow_html=True,
        )
        with st.container(key="sidebar_exit"):
            if st.button("Salir", use_container_width=True):
                if DEMO_MODE:
                    st.session_state["demo_exit"] = True
                else:
                    from api_client import api
                    api.logout()
                st.rerun()

    st.markdown(f"""
    <div class="topbar">
        <div>
            <div class="topbar-title">Vigilancia epidemiológica</div>
            <div class="topbar-subtitle">Dengue · Influenza · COVID-19</div>
        </div>
        <div class="topbar-agency">
            <img class="topbar-logo" src="data:image/png;base64,{LOGO_BASE64}" alt="Secretaría de Salud de Jalisco">
        </div>
    </div>
    """, unsafe_allow_html=True)

    if seccion == NAV[0]:
        render_resumen_view()
    elif seccion == NAV[1]:
        render_mapa_view()
    elif seccion == NAV[2]:
        render_predicciones_view()
    elif seccion == NAV[3]:
        render_alertas_view()

    st.markdown("""
    <div class="footer">
        NOM-017-SSA2-2012 · LFPDPPP · Datos anonimizados y agregados
    </div>
    """, unsafe_allow_html=True)
