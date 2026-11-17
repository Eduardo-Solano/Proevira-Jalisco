"""
Módulo de interfaz de autenticación con identidad oficial del Gobierno de Jalisco.
"""

import base64
from pathlib import Path

import streamlit as st
from api_client import MUNICIPIOS_JALISCO, api

def _logo(filename: str) -> str:
    image = (Path(__file__).parent / "assets" / filename).read_bytes()
    return "data:image/png;base64," + base64.b64encode(image).decode("ascii")


def _show_auth_view(view: str):
    st.session_state["auth_view"] = view
    st.session_state.pop("_password_reset_token", None)
    st.query_params.pop("reset_token", None)
    if view == "login":
        st.session_state.pop("_recovery_email", None)


def _render_login():
    st.markdown("### Bienvenido de nuevo")
    st.caption("Ingresa con tu cuenta para acceder al panel.")
    if st.session_state.pop("_password_reset_success", False):
        st.success("Tu contraseña fue actualizada. Inicia sesión con tu nueva contraseña.")
    with st.form("form_login"):
        email = st.text_input("Correo electrónico", placeholder="nombre@institucion.gob.mx")
        password = st.text_input("Contraseña", type="password")
        submitted = st.form_submit_button("Iniciar sesión", use_container_width=True)
        if submitted:
            if not email.strip() or not password:
                st.warning("Por favor completa tu correo y contraseña.")
            else:
                with st.spinner("Iniciando sesión…"):
                    result = api.login(email.strip(), password)
                if result["success"]:
                    st.rerun()
                else:
                    st.error(result.get("error", "No se pudo iniciar sesión. Intenta de nuevo."))
    st.markdown('<a class="auth-link" href="?auth=recovery" target="_self">¿Olvidaste tu contraseña?</a>', unsafe_allow_html=True)
    st.markdown('¿Aún no tienes cuenta? <a class="auth-link" href="?auth=register" target="_self">Registrarse como médico</a>', unsafe_allow_html=True)


def _render_register():
    st.markdown("### Registro de médicos")
    st.caption("Envía tus datos para revisión. Administración deberá aprobar tu solicitud antes de que puedas acceder.")
    if st.session_state.get("_registration_sent"):
        st.success("Solicitud enviada. Tus datos están en Administración, pendientes de verificación. Podrás iniciar sesión cuando tu cuenta sea aprobada.")
    else:
        with st.form("form_register_medico", clear_on_submit=False):
            email = st.text_input("Correo electrónico", key="register_email", max_chars=150)
            institucion = st.text_input("Institución", key="register_institucion", max_chars=150)
            cedula = st.text_input("Cédula profesional", key="register_cedula", max_chars=50)
            municipio = st.selectbox("Municipio de atención", list(MUNICIPIOS_JALISCO), format_func=lambda k: MUNICIPIOS_JALISCO[k]["nombre"], key="register_municipio")
            password = st.text_input("Contraseña", type="password", key="register_password", help="Al menos 8 caracteres.")
            confirmation = st.text_input("Confirmar contraseña", type="password", key="register_confirmation")
            submitted = st.form_submit_button("Enviar solicitud de registro", use_container_width=True)
            if submitted:
                email = email.strip().lower()
                if "@" not in email or "." not in email.split("@", 1)[-1] or any(c.isspace() for c in email):
                    st.warning("Ingresa un correo electrónico válido.")
                elif not institucion.strip() or not cedula.strip():
                    st.warning("Completa tu institución y cédula profesional.")
                elif len(password) < 8 or len(password.encode("utf-8")) > 72:
                    st.warning("Usa una contraseña de al menos 8 caracteres y hasta 72 bytes.")
                elif password != confirmation:
                    st.warning("Las contraseñas no coinciden.")
                else:
                    with st.spinner("Enviando solicitud…"):
                        result = api.register_medico(email, password, institucion.strip(), cedula.strip(), municipio_id=municipio)
                    if result.get("success"):
                        st.session_state["_registration_sent"] = True
                        st.rerun()
                    else:
                        st.error(result.get("error", "No se pudo enviar la solicitud."))
    st.markdown('<a class="auth-link" href="?auth=login" target="_self">Volver a iniciar sesión</a>', unsafe_allow_html=True)


def _render_recovery():
    st.markdown("### Recupera tu acceso")
    st.caption("Ingresa el correo de tu cuenta. Te enviaremos un código de 6 dígitos para recuperar tu acceso.")
    with st.form("form_password_recovery"):
        email = st.text_input("Correo electrónico", placeholder="nombre@institucion.gob.mx", key="recovery_email")
        submitted = st.form_submit_button("Enviar código de recuperación", use_container_width=True)
        if submitted:
            email = email.strip()
            if "@" not in email or "." not in email.split("@", 1)[-1] or any(c.isspace() for c in email):
                st.warning("Ingresa un correo electrónico válido.")
            else:
                with st.spinner("Solicitando código de recuperación…"):
                    result = api.request_password_reset(email)
                if result["success"]:
                    st.session_state["_recovery_email"] = email.lower()
                    st.session_state["auth_view"] = "code"
                    st.session_state["_recovery_sent"] = True
                    st.rerun()
                else:
                    st.error(result["error"])
    st.button("Volver a iniciar sesión", key="back_from_recovery", on_click=_show_auth_view, args=("login",))


def _render_code():
    st.markdown("### Revisa tu correo")
    if st.session_state.pop("_recovery_sent", False):
        st.success("Código de recuperación enviado.")
    st.caption("Escribe el código de 6 dígitos que recibiste. Revisa también la carpeta de correo no deseado.")
    with st.form("form_recovery_code"):
        code = st.text_input("Código de recuperación", placeholder="000000", max_chars=6, key="recovery_code")
        submitted = st.form_submit_button("Verificar código", use_container_width=True)
        if submitted:
            code = code.strip()
            if len(code) != 6 or not code.isascii() or not code.isdigit():
                st.warning("Ingresa los 6 dígitos del código que recibiste.")
            else:
                with st.spinner("Verificando código…"):
                    result = api.verify_recovery_code(st.session_state["_recovery_email"], code)
                if result["success"]:
                    st.session_state["_password_reset_token"] = result["reset_token"]
                    st.rerun()
                else:
                    st.error(result["error"])
    st.caption("Tienes hasta 5 intentos. Para recibir otro código, espera al menos un minuto; usa siempre el más reciente.")
    if st.button("Reenviar código", key="resend_recovery_code"):
        with st.spinner("Solicitando otro código…"):
            result = api.request_password_reset(st.session_state["_recovery_email"])
        if result["success"]:
            st.success("Código solicitado. Si ya pasó un minuto, recibirás uno nuevo; de lo contrario, usa el último que recibiste.")
        else:
            st.error(result["error"])
    st.button("Cambiar correo", key="change_recovery_email", on_click=_show_auth_view, args=("recovery",))
    st.button("Volver a iniciar sesión", key="back_from_code", on_click=_show_auth_view, args=("login",))


def _render_reset():
    st.markdown("### Elige una nueva contraseña")
    st.caption("Usa al menos 8 caracteres. Confirma tu nueva contraseña para guardar el cambio.")
    with st.form("form_reset_password"):
        password = st.text_input("Nueva contraseña", type="password", key="reset_password")
        confirmation = st.text_input("Confirmar contraseña", type="password", key="reset_confirmation")
        submitted = st.form_submit_button("Guardar nueva contraseña", use_container_width=True)
        if submitted:
            if len(password) < 8:
                st.warning("La contraseña debe tener al menos 8 caracteres.")
            elif len(password.encode("utf-8")) > 72:
                st.warning("La contraseña es demasiado larga. Usa una más corta; las letras con acentos y los símbolos pueden ocupar más espacio.")
            elif password != confirmation:
                st.warning("Las contraseñas no coinciden. Revísalas e intenta de nuevo.")
            else:
                with st.spinner("Actualizando contraseña…"):
                    result = api.reset_password(st.session_state["_password_reset_token"], password)
                if result["success"]:
                    api.logout()
                    _show_auth_view("login")
                    st.session_state["_password_reset_success"] = True
                    st.rerun()
                else:
                    st.error(result["error"])
    st.button("Solicitar un nuevo código", key="request_new_reset", on_click=_show_auth_view, args=("recovery",))
    st.button("Volver a iniciar sesión", key="back_from_reset", on_click=_show_auth_view, args=("login",))


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
.st-key-auth_card [data-testid="stButton"] button {
    background: #652379; border: 1px solid #652379; color: #fff; padding: .5rem 1rem;
    min-height: 44px; border-radius: 10px; font-weight: 600;
}
.st-key-auth_card [data-testid="stButton"] button:hover { background: #511a63; border-color: #511a63; color: #fff; }
.st-key-auth_card a.auth-link { color: #652379; text-decoration: underline; }
.st-key-auth_card a.auth-link:hover { color: #511a63; }
.st-key-auth_card a.auth-link:focus-visible { outline: 3px solid #cba9d6; outline-offset: 3px; }
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

        requested_view = st.query_params.get("auth")
        if requested_view in {"login", "recovery", "register"}:
            _show_auth_view(requested_view)
            st.query_params.pop("auth", None)
        if st.session_state.get("auth_view") != "register":
            st.session_state.pop("_registration_sent", None)
            for key in ("register_password", "register_confirmation"):
                st.session_state.pop(key, None)

        # Los correos anteriores con enlace se sustituyen por el flujo de código.
        if st.query_params.get("reset_token"):
            _show_auth_view("recovery")
            st.info("Ahora puedes recuperar tu acceso con un código por correo. Solicita uno aquí.")
        if st.session_state.get("_password_reset_token"):
            _render_reset()
        elif st.session_state.get("auth_view") == "code" and st.session_state.get("_recovery_email"):
            _render_code()
        elif st.session_state.get("auth_view") == "register":
            _render_register()
        elif st.session_state.get("auth_view") == "recovery":
            _render_recovery()
        else:
            _render_login()

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
