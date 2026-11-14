"""Aplicación principal de VIRALES Jalisco."""
import base64
from html import escape
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
from views.datos import render_datos_view
from views.reportes import render_reportes_view
from auth_ui import render_auth_page
from api_client import DEMO_MODE, ApiError

LOGO_PATH = os.path.join(BASE_DIR, "assets", "jalisco.png")
with open(LOGO_PATH, "rb") as logo_file:
    LOGO_BASE64 = base64.b64encode(logo_file.read()).decode("ascii")


def _salir_del_panel():
    if DEMO_MODE:
        st.session_state["demo_exit"] = True
    else:
        from api_client import api
        api.logout()


_ROLES_ETIQUETAS = {
    "medico": "Personal médico",
    "admin": "Administrador",
    "ciudadano": "Vigilancia ciudadana",
}


def _perfil_lateral():
    if DEMO_MODE:
        correo = "Usuario de demostración"
        rol_texto = "Modo demostración"
    else:
        correo = st.session_state.get("user_email") or "Usuario autenticado"
        rol_raw = (st.session_state.get("user_role") or "").strip().lower()
        rol_texto = _ROLES_ETIQUETAS.get(rol_raw, "Sesión activa")

    usuario = correo.split("@", 1)[0].strip()
    iniciales = "".join(parte[0] for parte in usuario.replace("_", " ").replace(".", " ").split() if parte)
    iniciales = (iniciales[:2] or "US").upper()
    return (
        '<div class="sidebar-profile">'
        f'<div class="profile-avatar" role="img" aria-label="Perfil de usuario">{escape(iniciales)}</div>'
        '<div class="profile-meta">'
        f'<span class="profile-role">{escape(rol_texto)}</span>'
        f'<strong class="profile-email" title="{escape(correo, quote=True)}">{escape(correo)}</strong>'
        '</div>'
        '</div>'
    )


# ── Configuración de página ──
st.set_page_config(
    page_title="VIRALES Jalisco",
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
[data-testid="stAppViewContainer"], .stApp { background: #eef1f4; }
[data-testid="stMainBlockContainer"] {
    max-width: none;
    padding: 4rem 1.7rem 1rem;
}
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #3e4144 0%, #34373a 100%);
    border-right: 1px solid #2d3033;
}
section[data-testid="stSidebar"]:has(button[aria-label="Collapse sidebar"]) {
    width: 276px !important;
    min-width: 276px !important;
    flex-basis: 276px !important;
}
section[data-testid="stSidebar"] > div {
    background: transparent;
}
section[data-testid="stSidebar"] [data-testid="stSidebarHeader"] {
    height: 36px !important;
    min-height: 36px !important;
    flex: 0 0 36px !important;
    padding: .45rem .85rem 0 !important;
}
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {
    padding: .35rem 1rem 1rem !important;
    min-height: calc(100vh - 38px);
    display: flex;
    flex-direction: column;
}
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] > div,
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] > div > div[data-testid="stVerticalBlock"],
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] > div > div > div[data-testid="stVerticalBlock"] {
    flex: 1 1 auto;
    display: flex;
    flex-direction: column;
    gap: .65rem;
}
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p { color: #eaf1ee; }
button[aria-label="Collapse sidebar"],
button[aria-label="Expand sidebar"] {
    visibility: visible !important;
    opacity: 1 !important;
    color: #477a70 !important;
}
section[data-testid="stSidebar"] button[aria-label="Collapse sidebar"] {
    color: #cbd8d4 !important;
}
.sidebar-brand {
    padding: 0 0 .9rem;
    margin-bottom: .35rem;
    border-bottom: 1px solid rgba(255,255,255,.12);
}
.sidebar-brand-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: .5rem;
}
.sidebar-brand-title {
    color: #f0b65c;
    font-size: 1.24rem;
    font-weight: 800;
    letter-spacing: .09em;
    line-height: 1.1;
}
.sidebar-brand-badge {
    padding: .16rem .48rem;
    border-radius: 999px;
    background: rgba(240,182,92,.14);
    border: 1px solid rgba(240,182,92,.32);
    color: #f5ca82;
    font-size: .62rem;
    font-weight: 700;
    letter-spacing: .05em;
    text-transform: uppercase;
}
.sidebar-brand-sub {
    display: block;
    margin-top: .28rem;
    color: #b7ceca;
    font-size: .72rem;
    font-weight: 500;
    letter-spacing: .01em;
}
.sidebar-profile {
    display: flex;
    align-items: center;
    gap: .7rem;
    min-width: 0;
    margin: .1rem 0 .45rem;
    padding: .7rem .78rem;
    border-radius: 10px;
    background: rgba(255,255,255,.06);
    border: 1px solid rgba(255,255,255,.10);
}
.profile-avatar {
    display: grid;
    flex: 0 0 36px;
    width: 36px;
    height: 36px;
    place-items: center;
    border-radius: 50%;
    background: linear-gradient(135deg, #f3c171 0%, #e09e3e 100%);
    box-shadow: 0 0 0 2px rgba(240,182,92,.22);
    color: #2f3133;
    font-size: .78rem;
    font-weight: 800;
    letter-spacing: .04em;
}
.profile-meta {
    display: flex;
    flex-direction: column;
    min-width: 0;
    gap: .1rem;
}
.profile-role {
    color: #b7ceca;
    font-size: .64rem;
    font-weight: 700;
    letter-spacing: .06em;
    text-transform: uppercase;
}
.profile-email {
    min-width: 0;
    overflow: hidden;
    color: #ffffff;
    font-size: .76rem;
    font-weight: 600;
    text-overflow: ellipsis;
    white-space: nowrap;
}
section[data-testid="stSidebar"] div[data-testid="stRadio"] {
    display: flex !important;
    flex-direction: column !important;
    gap: .5rem !important;
    width: 100% !important;
    margin-top: .25rem !important;
    padding: 0 !important;
}
section[data-testid="stSidebar"] div[data-testid="stRadio"] div[role="radiogroup"] {
    display: flex !important;
    flex-direction: column !important;
    width: 100% !important;
    align-items: stretch !important;
    margin: 0 !important;
    gap: .36rem;
}
section[data-testid="stSidebar"] div[data-testid="stRadio"] [data-testid="stWidgetLabel"] {
    display: block !important;
    min-height: auto !important;
    margin: 0 !important;
    padding: 0 .2rem !important;
}
section[data-testid="stSidebar"] div[data-testid="stRadio"] [data-testid="stWidgetLabel"] p {
    margin: 0 !important;
    color: #9fb0ab !important;
    font-size: .66rem !important;
    font-weight: 700 !important;
    letter-spacing: .1em !important;
    text-transform: uppercase !important;
    line-height: 1.3 !important;
}
section[data-testid="stSidebar"] label[data-testid="stRadioOption"] > div > div:first-child {
    display: none !important;
}
section[data-testid="stSidebar"] label[data-testid="stRadioOption"] {
    display: flex !important;
    width: 100% !important;
    max-width: 100% !important;
    box-sizing: border-box !important;
    min-height: 44px;
    margin: 0 !important;
    padding: .62rem .88rem;
    border: 1px solid transparent;
    border-radius: 9px;
    color: #e4ece9;
    transition: background .15s ease, border-color .15s ease, color .15s ease;
}
section[data-testid="stSidebar"] label[data-testid="stRadioOption"] > div,
section[data-testid="stSidebar"] label[data-testid="stRadioOption"] > div:last-child,
section[data-testid="stSidebar"] label[data-testid="stRadioOption"] [data-testid="stMarkdownContainer"] {
    width: 100% !important;
}
section[data-testid="stSidebar"] label[data-testid="stRadioOption"]:hover {
    background: rgba(255,255,255,.08);
    border-color: rgba(255,255,255,.08);
    color: #ffffff;
}
section[data-testid="stSidebar"] label[data-testid="stRadioOption"][data-selected="true"] {
    background: linear-gradient(90deg, rgba(240,182,92,.20) 0%, rgba(255,255,255,.09) 100%);
    border-color: rgba(240,182,92,.30);
    box-shadow: inset 3.5px 0 0 #f0b65c;
    color: #ffffff;
}
section[data-testid="stSidebar"] label[data-testid="stRadioOption"] p {
    color: inherit !important;
    font-size: .89rem;
    font-weight: 500;
    letter-spacing: .005em;
}
section[data-testid="stSidebar"] label[data-testid="stRadioOption"][data-selected="true"] p {
    font-weight: 600;
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
section[data-testid="stSidebar"] [data-testid="stElementContainer"]:has(.st-key-sidebar_bottom),
section[data-testid="stSidebar"] [data-testid="stLayoutWrapper"]:has(.st-key-sidebar_bottom),
.st-key-sidebar_bottom {
    margin-top: auto !important;
    width: 100%;
}
.st-key-sidebar_bottom {
    padding-top: 1rem;
}
.sidebar-scope {
    margin-bottom: .75rem;
    padding: .62rem .78rem;
    border-radius: 9px;
    background: rgba(255,255,255,.04);
    border: 1px solid rgba(255,255,255,.08);
    color: #b7ceca;
    font-size: .71rem;
    line-height: 1.45;
}
.sidebar-scope strong {
    display: block;
    margin-bottom: .12rem;
    color: #eaf1ee;
    font-size: .73rem;
    font-weight: 600;
}
.sidebar-footer {
    width: 100%;
    padding: .78rem .15rem .55rem;
    border-top: 1px solid rgba(255,255,255,.12);
    color: #aeb8b5;
    font-size: .71rem;
    line-height: 1.45;
}
.sidebar-footer strong {
    display: block;
    color: #ffffff;
    font-size: .79rem;
    font-weight: 650;
}
.st-key-sidebar_exit {
    width: 100%;
}
.st-key-sidebar_exit button {
    width: 100%;
    min-height: 40px;
    border-radius: 9px;
    border: 1px solid rgba(255,255,255,.20);
    color: #eaf1ee;
    background: rgba(255,255,255,.04);
    font-weight: 600;
    transition: background .15s ease, border-color .15s ease, color .15s ease;
}
.st-key-sidebar_exit button:hover {
    border-color: #f0b65c;
    color: #ffffff;
    background: rgba(240,182,92,.14);
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
.overview-signal {
    display: flex;
    justify-content: space-between;
    gap: .7rem;
    margin-top: .55rem;
    padding: .7rem .8rem;
    border-left: 3px solid var(--disease-color);
    border-radius: 6px;
    background: var(--disease-bg);
    color: #526861;
    font-size: .78rem;
}
.overview-signal strong { color: #31544e; }
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
    section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] { min-height: auto; }
    .st-key-sidebar_bottom { padding-top: 1.5rem; }
    .sidebar-profile { max-width: 100%; }
    .risk-legend-note { width: 100%; margin-left: 0; }
}
</style>
""", unsafe_allow_html=True)

st.markdown(f"""
<style>
header[data-testid="stHeader"] {{
    height: 82px !important;
    min-height: 82px;
    z-index: 1000;
    background: #fff;
}}
header[data-testid="stHeader"] [data-testid="stToolbar"] {{
    box-sizing: border-box;
    min-height: 82px;
    padding: .7rem 1rem;
    border-bottom: 1px solid #dfe3e8;
    background: #fff;
    display: flex;
    align-items: center;
}}
header[data-testid="stHeader"] [data-testid="stToolbar"] > div {{
    position: absolute;
    inset: 0;
    display: block !important;
    pointer-events: none;
}}
header[data-testid="stHeader"] [data-testid="stToolbarActions"],
header[data-testid="stHeader"] [data-testid="stStatusWidget"],
header[data-testid="stHeader"] [data-testid="stAppDeployButton"],
header[data-testid="stHeader"] [data-testid="stMainMenu"] {{
    display: none !important;
}}
header[data-testid="stHeader"] [data-testid="stExpandSidebarButton"] {{
    position: absolute;
    top: 27px;
    left: 8px;
    z-index: 1002;
    pointer-events: auto;
}}
header[data-testid="stHeader"]:has([data-testid="stExpandSidebarButton"])
    [data-testid="stToolbar"]::before {{
    margin-left: 40px;
}}
header[data-testid="stHeader"] [data-testid="stToolbar"]::before {{
    content: "VIRALES · Vigilancia epidemiológica\\A Dengue · Influenza · COVID-19";
    white-space: pre-line;
    color: #454545;
    font: 700 1.08rem/1.35 "Segoe UI", "Aptos", sans-serif;
}}
header[data-testid="stHeader"] [data-testid="stToolbar"]::after {{
    content: "";
    display: block;
    flex: 0 0 190px;
    height: 64px;
    margin-left: auto;
    margin-right: 14px;
    background: url("data:image/png;base64,{LOGO_BASE64}") no-repeat right center / contain;
}}
@media (max-width: 760px) {{
    header[data-testid="stHeader"] {{
        height: 70px !important;
        min-height: 70px;
    }}
    header[data-testid="stHeader"] [data-testid="stToolbar"] {{
        min-height: 70px;
        padding: .55rem .75rem;
        background: #fff;
    }}
    header[data-testid="stHeader"] [data-testid="stToolbar"]::before {{
        font-size: .88rem;
    }}
    header[data-testid="stHeader"] [data-testid="stToolbar"]::after {{
        flex-basis: 126px;
        height: 42px;
        margin-right: 8px;
    }}
}}
</style>
""", unsafe_allow_html=True)

NAV = [
    "◫   Panorama",
    "⌖   Mapa epidemiológico",
    "↗   Predicciones",
    "▤   Gestión de datos",
    "▧   Reportes",
    "▲   Alertas",
]

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
            '<div class="sidebar-brand">'
            '<div class="sidebar-brand-top">'
            '<span class="sidebar-brand-title">VIRALES</span>'
            '<span class="sidebar-brand-badge">Jalisco</span>'
            '</div>'
            '<span class="sidebar-brand-sub">Vigilancia epidemiológica estatal</span>'
            '</div>',
            unsafe_allow_html=True,
        )
        st.markdown(_perfil_lateral(), unsafe_allow_html=True)
        seccion = st.radio(
            "Menú principal",
            NAV,
            index=0,
            label_visibility="visible",
            key="main_navigation",
        )
        with st.container(key="sidebar_bottom"):
            st.markdown(
                '<div class="sidebar-scope">'
                '<strong>Cobertura del sistema</strong>'
                '12 municipios · Región Centro'
                '</div>'
                '<div class="sidebar-footer"><strong>Gobierno de Jalisco</strong>'
                'Secretaría de Salud</div>',
                unsafe_allow_html=True,
            )
            with st.container(key="sidebar_exit"):
                if st.button("Cerrar sesión", use_container_width=True):
                    _salir_del_panel()
                    st.rerun()

    try:
        if seccion == NAV[0]:
            render_resumen_view()
        elif seccion == NAV[1]:
            render_mapa_view()
        elif seccion == NAV[2]:
            render_predicciones_view()
        elif seccion == NAV[3]:
            render_datos_view()
        elif seccion == NAV[4]:
            render_reportes_view()
        elif seccion == NAV[5]:
            render_alertas_view()
    except ApiError as error:
        st.error(f"No se pudo consultar la información del backend. {error}")

    st.markdown("""
    <div class="footer">
        NOM-017-SSA2-2012 · LFPDPPP · Datos anonimizados y agregados
    </div>
    """, unsafe_allow_html=True)
