"""
Módulo de interfaz de autenticación con identidad oficial del Gobierno de Jalisco.
"""

import streamlit as st
from api_client import api

def render_auth_page():
    """Renderiza el portal de acceso institucional con diseño oficial de Jalisco."""
    
    st.markdown("""
        <style>
        .jal-top-bar {
            background-color: #082142;
            color: #ffffff;
            font-size: 0.75rem;
            padding: 6px 16px;
            font-weight: 600;
            letter-spacing: 1px;
            border-bottom: 3px solid #EAA824; /* Oro Jalisco */
            margin-bottom: 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .jal-card {
            background: #ffffff;
            border-radius: 8px;
            padding: 2.2rem 2rem;
            border: 1px solid #e2e8f0;
            box-shadow: 0 4px 16px rgba(0, 40, 85, 0.08);
            border-top: 4px solid #003366; /* Azul Jalisco */
        }
        .jal-title {
            color: #003366;
            font-size: 1.6rem;
            font-weight: 800;
            margin: 0.2rem 0;
            letter-spacing: -0.5px;
        }
        .jal-gold-badge {
            display: inline-block;
            background-color: #fff8e6;
            color: #b47504;
            border: 1px solid #fed7aa;
            font-size: 0.72rem;
            font-weight: 700;
            padding: 3px 10px;
            border-radius: 4px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        </style>
        <div class="jal-top-bar">
            <span>GOBIERNO DEL ESTADO DE JALISCO • SECRETARÍA DE SALUD</span>
            <span>PORTAL OFICIAL</span>
        </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1.8, 1])
    
    with col2:
        st.markdown("""
            <div style="text-align: center; margin-bottom: 1.5rem;">
                <span class="jal-gold-badge">Sistema Estatal de Salud</span>
                <div class="jal-title">VIRALES JALISCO</div>
                <p style="color: #64748b; font-size: 0.88rem; margin-top: 4px;">
                    Plataforma de Vigilancia Epidemiológica y Alerta Temprana<br>
                    <strong>Dengue • Influenza • COVID-19</strong>
                </p>
            </div>
        """, unsafe_allow_html=True)
        
        tab_login, tab_registro = st.tabs(["🔐 Acceso al Portal", "📝 Registro de Médico"])
        
        with tab_login:
            st.markdown("##### Iniciar Sesión")
            with st.form("form_login"):
                email = st.text_input("Correo Institucional", placeholder="usuario@saludjalisco.gob.mx")
                password = st.text_input("Contraseña", type="password")
                btn_submit = st.form_submit_button("Ingresar al Sistema", use_container_width=True)
                
                if btn_submit:
                    if not email or not password:
                        st.warning("Por favor completa tu correo y contraseña.")
                    else:
                        result = api.login(email, password)
                        if result["success"]:
                            st.success(f"Bienvenido. Rol asignado: {st.session_state.get('user_role', '').capitalize()}")
                            st.rerun()
                        else:
                            st.error(result.get("error", "Error de autenticación"))
            
        with tab_registro:
            st.markdown("##### Solicitud de Alta de Personal Médico")
            st.caption("El acceso médico requiere verificación posterior de su cédula profesional ante el registro estatal.")
            with st.form("form_registro_medico"):
                reg_email = st.text_input("Correo Electrónico", placeholder="medico@hospital.org")
                reg_pass = st.text_input("Contraseña", type="password")
                reg_inst = st.text_input("Unidad de Salud (CLUES)", placeholder="Ej. Centro de Salud Guadalajara 1")
                reg_cedula = st.text_input("Cédula Profesional", placeholder="Ej. 12345678")
                btn_reg = st.form_submit_button("Enviar Solicitud de Registro", use_container_width=True)
                
                if btn_reg:
                    if not reg_email or not reg_pass or not reg_cedula:
                        st.warning("Completa los datos obligatorios.")
                    else:
                        res = api.register_medico(reg_email, reg_pass, reg_inst, reg_cedula)
                        if res["success"]:
                            st.info("✅ Registro enviado. Su cuenta iniciará con estatus `verificado: false`.")
                        else:
                            st.error(res.get("error", "No se pudo procesar la solicitud."))

        st.markdown("""
            <div style="text-align: center; margin-top: 2rem; font-size: 0.75rem; color: #94a3b8;">
                Conforme a la <strong>LFPDPPP</strong> y <strong>NOM-017-SSA2-2012</strong>.<br>
                Gobierno del Estado de Jalisco | Secretaría de Salud.
            </div>
        """, unsafe_allow_html=True)
