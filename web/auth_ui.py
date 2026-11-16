"""
Módulo de interfaz de autenticación con identidad oficial del Gobierno de Jalisco.
"""

import base64
from pathlib import Path

import streamlit as st
from api_client import api

def _logo(filename: str) -> str:
    image = (Path(__file__).parent / "assets" / filename).read_bytes()
    return "data:image/png;base64," + base64.b64encode(image).decode("ascii")


def render_auth_page():
    """Renderiza el portal de acceso institucional con diseño oficial de Jalisco."""

    st.markdown("""
<style>
header[data-testid="stHeader"], section[data-testid="stSidebar"] { display: none !important; }
.stApp { background: #f7f6f9 !important; }
[data-testid="stAppViewContainer"] {
    background:
        radial-gradient(circle at 0% 100%, transparent 238px, rgba(116, 55, 139, .08) 239px, rgba(116, 55, 139, .08) 240px, transparent 241px),
        radial-gradient(circle at 0% 100%, transparent 290px, rgba(116, 55, 139, .05) 291px, rgba(116, 55, 139, .05) 292px, transparent 293px),
        radial-gradient(circle at 100% 0%, transparent 210px, rgba(116, 55, 139, .07) 211px, rgba(116, 55, 139, .07) 212px, transparent 213px),
        radial-gradient(ellipse at 5% 15%, rgba(116, 55, 139, .12), transparent 48%),
        radial-gradient(ellipse at 95% 85%, rgba(164, 139, 184, .17), transparent 48%),
        radial-gradient(circle, rgba(101, 35, 121, .07) .8px, transparent 1px),
        #f7f6f9 !important;
    background-size: auto, auto, auto, auto, auto, 24px 24px !important;
    background-attachment: fixed !important;
}
[data-testid="stMainBlockContainer"] {
    box-sizing: border-box;
    width: 100%;
    max-width: 520px !important;
    margin-inline: auto;
    padding: clamp(1.5rem, 5vh, 4rem) 1rem 2rem !important;
}
.st-key-auth_card {
    background: #fff; border: 1px solid #e9e5ed; border-radius: 24px;
    padding: clamp(1.25rem, 5vw, 2rem); box-shadow: 0 12px 45px rgba(48, 24, 62, .05);
    box-sizing: border-box; min-width: 0;
}
.auth-identity { text-align: center; margin-bottom: 1.7rem; }
.auth-identity img { width: 190px; max-width: 75%; height: auto; }
.auth-identity p { color: #716979; font-size: .88rem; margin: .7rem 0 0; }
.st-key-auth_card h3 { color: #302537; font-size: 1.45rem; letter-spacing: -.035em; }
.st-key-auth_card [data-testid="stCaptionContainer"] { color: #797180; }
.st-key-auth_card [data-testid="stForm"] { border: 0; padding: .4rem 0 0; }
.st-key-auth_card [data-testid="stTextInput"] label { color: #493e50; font-size: .85rem; }
.st-key-auth_card [data-baseweb="input"] { background: #fcfbfd; border-radius: 10px; border-color: #e3dfe7; }
.st-key-auth_card [data-baseweb="input"]:focus-within { border-color: #79388b; }
.st-key-auth_card input { min-height: 44px; color: #302537; font-size: 16px; }
.st-key-auth_card [data-testid="stFormSubmitButton"] button {
    background: #652379; color: #fff; border: 1px solid #652379;
    min-height: 46px; border-radius: 10px; margin-top: .5rem; font-weight: 600;
}
.st-key-auth_card [data-testid="stFormSubmitButton"] button:hover { background: #511a63; border-color: #511a63; color: #fff; }
.st-key-auth_card button:focus-visible { outline: 3px solid #cba9d6; outline-offset: 3px; }
.auth-institution { border-top: 1px solid #eeeaf1; margin-top: 1.8rem; padding-top: 1.35rem; text-align: center; }
.auth-institution img { width: 145px; max-width: 60%; height: auto; }
.auth-institution p { color: #797180; font-size: .75rem; margin: .4rem 0 0; }
.auth-footnote { text-align: center; color: #716979; font-size: .75rem; margin: 1rem 0; line-height: 1.7; overflow-wrap: anywhere; }
@media (max-width: 480px) {
    [data-testid="stAppViewContainer"] {
        background:
            radial-gradient(ellipse at 0% 0%, rgba(116, 55, 139, .10), transparent 60%),
            radial-gradient(ellipse at 100% 100%, rgba(164, 139, 184, .13), transparent 60%),
            #f7f6f9 !important;
        background-size: auto !important;
        background-attachment: scroll !important;
    }
    .st-key-auth_card { padding: 1.5rem 1.15rem 1.25rem; border-radius: 18px; }
    .auth-identity img { width: 160px; }
}
@media (max-height: 740px) {
    [data-testid="stMainBlockContainer"] { padding-top: 1rem !important; }
    .auth-identity { margin-bottom: 1rem; }
    .auth-institution { margin-top: 1rem; padding-top: 1rem; }
}
</style>
    """, unsafe_allow_html=True)

    with st.container(key="auth_card"):
        st.markdown(
            f'<div class="auth-identity"><img src="{_logo("Virales.png")}" alt="VIRALES">'
            '<p>Vigilancia epidemiológica · Jalisco</p></div>',
            unsafe_allow_html=True,
        )

        st.markdown("### Bienvenido de nuevo")
        st.caption("Ingresa con tu cuenta para acceder al panel.")
        with st.form("form_login"):
            email = st.text_input("Correo electrónico", placeholder="nombre@institucion.gob.mx")
            password = st.text_input("Contraseña", type="password")
            btn_submit = st.form_submit_button("Iniciar sesión", use_container_width=True)

            if btn_submit:
                if not email.strip() or not password:
                    st.warning("Por favor completa tu correo y contraseña.")
                else:
                    with st.spinner("Iniciando sesión…"):
                        result = api.login(email.strip(), password)
                    if result["success"]:
                        st.rerun()
                    else:
                        st.error(result.get("error", "No se pudo iniciar sesión. Intenta de nuevo."))

        st.markdown(
            f'<div class="auth-institution"><img src="{_logo("jalisco.png")}" alt="Jalisco, Gobierno del Estado">'
            '<p>Secretaría de Salud</p></div>',
            unsafe_allow_html=True,
        )

    st.markdown(
        '<p class="auth-footnote">Plataforma de vigilancia de dengue, influenza y COVID-19.<br>'
        'LFPDPPP · NOM-017-SSA2-2012</p>',
        unsafe_allow_html=True,
    )
