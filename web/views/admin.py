"""
Vista: Panel de Administración (Usuarios, Validación Médica, Señales Móviles y Estado).
"""

import pandas as pd
import streamlit as st

from api_client import DEMO_MODE, MUNICIPIOS_JALISCO, ApiError, api

ROLES_ADMIN_WEB = {"funcionario", "admin", "administrador"}
ROLES_OPCIONES = ["paciente", "medico", "funcionario"]
ROL_ETIQUETAS = {
    "paciente": "Paciente",
    "medico": "Médico",
    "funcionario": "Administrador / Funcionario",
    "admin": "Administrador",
    "administrador": "Administrador",
}


def _nombre_municipio(municipio_id) -> str:
    if not municipio_id:
        return "Sin asignar / Región"
    mid = str(municipio_id)
    return MUNICIPIOS_JALISCO.get(mid, {"nombre": mid})["nombre"]


def _render_usuarios_tab(current_uid: str) -> None:
    try:
        todos_usuarios = api.get_users()
    except ApiError as error:
        st.error(f"No se pudo cargar el padrón de usuarios: {error}")
        return

    pendientes = [
        u for u in todos_usuarios
        if str(u.get("role", "")).lower() == "medico" and not bool(u.get("verificado", False))
    ]
    medicos_activos = sum(
        1 for u in todos_usuarios
        if str(u.get("role", "")).lower() == "medico" and bool(u.get("verificado", False))
    )
    pacientes = sum(1 for u in todos_usuarios if str(u.get("role", "")).lower() == "paciente")
    admins = sum(1 for u in todos_usuarios if str(u.get("role", "")).lower() in ROLES_ADMIN_WEB)

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Total usuarios", len(todos_usuarios))
    k2.metric("Médicos pendientes", len(pendientes))
    k3.metric("Médicos activos", medicos_activos)
    k4.metric("Pacientes (app)", pacientes)
    k5.metric("Administradores", admins)

    # ── Bandeja de verificación médica ──
    with st.container(border=True):
        st.markdown("##### Solicitudes médicas pendientes de verificación")
        if not pendientes:
            st.info("No hay solicitudes médicas pendientes por aprobar.")
        else:
            confirm_reject_uid = st.session_state.get("confirm_reject_medico_uid")
            for med in pendientes:
                uid = med["uid"]
                with st.container(border=True):
                    info_col, btn_col1, btn_col2 = st.columns([3.2, 1.1, 1.1])
                    info_col.markdown(
                        f"**{med.get('email', '')}**  \n"
                        f"Institución: `{med.get('institucion') or 'No especificada'}` · "
                        f"Cédula: `{med.get('cedula') or 'Sin cédula'}` · "
                        f"Municipio: **{_nombre_municipio(med.get('municipio_id'))}**"
                    )
                    if btn_col1.button(
                        "Aprobar médico",
                        key=f"approve_med_{uid}",
                        type="primary",
                        use_container_width=True,
                    ):
                        res = api.verify_medico(uid)
                        if res.get("success"):
                            st.session_state.pop("confirm_reject_medico_uid", None)
                            st.success(f"Médico {med.get('email')} verificado.")
                            st.rerun()
                        else:
                            st.error(res.get("error", "No se pudo aprobar la solicitud."))

                    if confirm_reject_uid == uid:
                        if btn_col2.button(
                            "Confirmar rechazo",
                            key=f"confirm_reject_med_{uid}",
                            use_container_width=True,
                        ):
                            res = api.delete_user(uid)
                            if res.get("success"):
                                st.session_state.pop("confirm_reject_medico_uid", None)
                                st.success("Solicitud rechazada y eliminada.")
                                st.rerun()
                            else:
                                st.error(res.get("error", "No se pudo eliminar la solicitud."))
                    else:
                        if btn_col2.button(
                            "Rechazar",
                            key=f"reject_med_{uid}",
                            use_container_width=True,
                        ):
                            st.session_state["confirm_reject_medico_uid"] = uid
                            st.rerun()

    # ── Directorio y edición de usuarios ──
    with st.container(border=True):
        st.markdown("##### Directorio de usuarios")
        f1, f2, f3 = st.columns([1.2, 1.2, 2])
        filtro_rol = f1.selectbox(
            "Filtrar por rol",
            ["todos", "paciente", "medico", "funcionario"],
            format_func=lambda r: "Todos los roles" if r == "todos" else ROL_ETIQUETAS.get(r, r.capitalize()),
            key="admin_user_role_filter",
        )
        filtro_estado = f2.selectbox(
            "Estado",
            ["todos", "verificado", "pendiente"],
            format_func=lambda s: {"todos": "Todos", "verificado": "Verificados", "pendiente": "Pendientes"}[s],
            key="admin_user_status_filter",
        )
        busqueda = f3.text_input(
            "Buscar por correo, cédula o institución",
            placeholder="ej. medico@salud.jalisco.gob.mx",
            key="admin_user_search",
        ).strip().lower()

        filtrados = []
        for u in todos_usuarios:
            rol = str(u.get("role", "")).lower()
            verif = bool(u.get("verificado", False))
            if filtro_rol != "todos":
                if filtro_rol == "funcionario" and rol not in ROLES_ADMIN_WEB:
                    continue
                if filtro_rol != "funcionario" and rol != filtro_rol:
                    continue
            if filtro_estado == "verificado" and not verif:
                continue
            if filtro_estado == "pendiente" and verif:
                continue
            if busqueda:
                texto = " ".join([
                    str(u.get("email") or ""),
                    str(u.get("cedula") or ""),
                    str(u.get("institucion") or ""),
                ]).lower()
                if busqueda not in texto:
                    continue
            filtrados.append(u)

        if not filtrados:
            st.info("No hay usuarios que coincidan con los filtros seleccionados.")
        else:
            tabla = pd.DataFrame([
                {
                    "Correo": u.get("email", ""),
                    "Rol": ROL_ETIQUETAS.get(str(u.get("role", "")).lower(), u.get("role", "")),
                    "Estado": "Verificado" if u.get("verificado") else "Pendiente",
                    "Municipio": _nombre_municipio(u.get("municipio_id")),
                    "Institución": u.get("institucion") or "—",
                    "Cédula": u.get("cedula") or "—",
                }
                for u in filtrados
            ])
            st.dataframe(tabla, hide_index=True, use_container_width=True)

            opciones_uid = [u["uid"] for u in filtrados]
            mapa_usuarios = {u["uid"]: u for u in filtrados}
            sel_uid = st.selectbox(
                "Seleccionar usuario para administrar",
                opciones_uid,
                format_func=lambda uid: (
                    f"{mapa_usuarios[uid].get('email')} "
                    f"({ROL_ETIQUETAS.get(str(mapa_usuarios[uid].get('role', '')).lower(), mapa_usuarios[uid].get('role'))})"
                ),
                key="admin_selected_user_uid",
            )
            sel_user = mapa_usuarios[sel_uid]
            es_mismo = sel_uid == current_uid

            with st.form(f"form_edit_user_{sel_uid}"):
                e1, e2, e3 = st.columns([1.2, 1.4, 0.9])
                rol_actual = str(sel_user.get("role", "paciente")).lower()
                rol_para_select = "funcionario" if rol_actual in {"admin", "administrador"} else rol_actual
                if rol_para_select not in ROLES_OPCIONES:
                    rol_para_select = "paciente"

                nuevo_rol = e1.selectbox(
                    "Rol",
                    ROLES_OPCIONES,
                    index=ROLES_OPCIONES.index(rol_para_select),
                    format_func=lambda r: ROL_ETIQUETAS.get(r, r.capitalize()),
                )
                mun_keys = ["__none__"] + list(MUNICIPIOS_JALISCO.keys())
                mun_actual = str(sel_user.get("municipio_id") or "")
                mun_idx = mun_keys.index(mun_actual) if mun_actual in mun_keys else 0
                nuevo_mun = e2.selectbox(
                    "Municipio",
                    mun_keys,
                    index=mun_idx,
                    format_func=lambda k: "Sin asignar / Región" if k == "__none__" else MUNICIPIOS_JALISCO[k]["nombre"],
                )
                nuevo_verif = e3.checkbox("Verificado", value=bool(sel_user.get("verificado", True)))

                d1, d2 = st.columns(2)
                nueva_inst = d1.text_input("Institución", value=sel_user.get("institucion") or "")
                nueva_cedula = d2.text_input("Cédula profesional", value=sel_user.get("cedula") or "")

                guardar_btn = st.form_submit_button("Guardar cambios", use_container_width=True)
                if guardar_btn:
                    res = api.update_user(
                        sel_uid,
                        role=nuevo_rol,
                        municipio_id=None if nuevo_mun == "__none__" else nuevo_mun,
                        clear_municipio=(nuevo_mun == "__none__"),
                        institucion=nueva_inst,
                        cedula=nueva_cedula,
                        verificado=nuevo_verif,
                    )
                    if res.get("success"):
                        st.success(f"Usuario {sel_user.get('email')} actualizado.")
                        st.rerun()
                    else:
                        st.error(res.get("error", "No se pudo actualizar el usuario."))

            if es_mismo:
                st.caption("Esta es tu sesión activa actual; no puedes eliminarla desde aquí.")
            else:
                if st.session_state.get("confirm_delete_user_uid") == sel_uid:
                    c1, c2, _ = st.columns([1.4, 1.1, 2.5])
                    if c1.button(
                        "Confirmar eliminación de usuario",
                        key=f"confirm_del_usr_{sel_uid}",
                        type="primary",
                        use_container_width=True,
                    ):
                        res = api.delete_user(sel_uid)
                        if res.get("success"):
                            st.session_state.pop("confirm_delete_user_uid", None)
                            st.success("Usuario eliminado del sistema.")
                            st.rerun()
                        else:
                            st.error(res.get("error", "No se pudo eliminar el usuario."))
                    if c2.button("Cancelar", key=f"cancel_del_usr_{sel_uid}", use_container_width=True):
                        st.session_state.pop("confirm_delete_user_uid", None)
                        st.rerun()
                else:
                    if st.button("Eliminar usuario seleccionado", key=f"del_usr_{sel_uid}"):
                        st.session_state["confirm_delete_user_uid"] = sel_uid
                        st.rerun()

    # ── Crear usuario manualmente ──
    with st.expander("Registrar nuevo usuario manualmente"):
        with st.form("form_admin_create_user"):
            c1, c2 = st.columns(2)
            new_email = c1.text_input("Correo electrónico", placeholder="usuario@salud.jalisco.gob.mx")
            new_password = c2.text_input("Contraseña inicial (mín. 6 caracteres)", type="password")

            c3, c4, c5 = st.columns([1.2, 1.3, 0.9])
            new_role = c3.selectbox(
                "Rol",
                ["medico", "funcionario", "paciente"],
                format_func=lambda r: ROL_ETIQUETAS.get(r, r.capitalize()),
            )
            mun_opts = ["__none__"] + list(MUNICIPIOS_JALISCO.keys())
            new_mun = c4.selectbox(
                "Municipio (opcional)",
                mun_opts,
                format_func=lambda k: "Sin asignar / Región" if k == "__none__" else MUNICIPIOS_JALISCO[k]["nombre"],
            )
            new_verif = c5.checkbox("Verificado", value=True)

            c6, c7 = st.columns(2)
            new_inst = c6.text_input("Institución (opcional)", placeholder="Ej. Hospital General de Occidente")
            new_ced = c7.text_input("Cédula profesional (opcional)", placeholder="Ej. MED-123456")

            crear = st.form_submit_button("Crear usuario", use_container_width=True)
            if crear:
                if not new_email.strip() or len(new_password) < 6:
                    st.warning("Ingresa un correo válido y una contraseña de al menos 6 caracteres.")
                else:
                    res = api.create_user(
                        email=new_email.strip(),
                        password=new_password,
                        role=new_role,
                        municipio_id=None if new_mun == "__none__" else new_mun,
                        institucion=new_inst.strip() or None,
                        cedula=new_ced.strip() or None,
                        verificado=new_verif,
                    )
                    if res.get("success"):
                        st.success(f"Usuario {new_email.strip().lower()} creado.")
                        st.rerun()
                    else:
                        st.error(res.get("error", "No se pudo crear el usuario."))


def _render_senales_moviles_tab() -> None:
    st.caption(
        "Resumen agregado y anonimizado de los reportes de síntomas enviados por ciudadanos desde la app móvil "
        "(conforme a LFPDPPP; no muestra nombres ni correos)."
    )
    try:
        summary = api.get_symptoms_summary()
    except ApiError as error:
        st.error(f"No se pudo consultar el resumen de reportes ciudadanos: {error}")
        return

    sosp = summary.get("por_sospecha", {})
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total reportes", summary.get("total_reportes", 0))
    c2.metric("Últimos 7 días", summary.get("ultimos_7_dias", 0))
    c3.metric("Sospecha Dengue", sosp.get("dengue", 0))
    c4.metric("Sospecha Influenza", sosp.get("influenza", 0))
    c5.metric("Sospecha COVID-19", sosp.get("covid", 0))

    por_mun = summary.get("por_municipio", [])
    if por_mun:
        st.markdown("**Distribución por municipio**")
        df_mun = pd.DataFrame([
            {
                "Municipio": _nombre_municipio(item.get("municipio_id")),
                "Total": item.get("total", 0),
                "Dengue": item.get("dengue", 0),
                "Influenza": item.get("influenza", 0),
                "COVID-19": item.get("covid", 0),
            }
            for item in por_mun
        ])
        st.dataframe(df_mun, hide_index=True, use_container_width=True)

    recientes = summary.get("recientes", [])
    if not recientes:
        st.info("Aún no hay reportes de síntomas registrados desde la aplicación móvil.")
    else:
        st.markdown("**Últimos reportes ciudadanos (anonimizados)**")
        df_rec = pd.DataFrame([
            {
                "Fecha": str(item.get("ts_registro") or "")[:16].replace("T", " "),
                "Municipio": _nombre_municipio(item.get("municipio_id")),
                "Sospecha": str(item.get("sospecha_enfermedad", "")).capitalize(),
                "Días": item.get("dias_con_sintomas", 1),
                "Temp. (°C)": item.get("temperatura") if item.get("temperatura") is not None else "—",
                "Fiebre": "Sí" if item.get("fiebre") else "No",
                "Tos": "Sí" if item.get("tos") else "No",
                "Dif. resp.": "Sí" if item.get("dificultad_respiratoria") else "No",
            }
            for item in recientes
        ])
        st.dataframe(df_rec, hide_index=True, use_container_width=True)


def _render_estado_sistema_tab() -> None:
    try:
        health = api.get_system_health()
    except ApiError as error:
        health = {"status": f"error ({error})", "modelo_cargado": False, "db": "error"}

    try:
        version = api.get_model_info()
    except ApiError:
        version = {}

    h1, h2, h3, h4 = st.columns(4)
    h1.metric("Estado API", str(health.get("status", "desconocido")).upper())
    h2.metric("Base de datos", str(health.get("db", "desconocido")).upper())
    h3.metric("Motor ML", "Cargado" if health.get("modelo_cargado") else "No disponible")
    h4.metric("Modelo activo", str(version.get("modelo", "rf-municipal-v2")))

    por_enf = version.get("por_enfermedad", {}) if isinstance(version, dict) else {}
    if por_enf:
        st.markdown("**Cobertura temporal por enfermedad**")
        df_enf = pd.DataFrame([
            {
                "Enfermedad": enf.upper(),
                "Última semana observada": info.get("ultima_semana_datos", "—"),
                "Próxima semana predicha": info.get("semana_prediccion", "—"),
            }
            for enf, info in por_enf.items()
        ])
        st.dataframe(df_enf, hide_index=True, use_container_width=True)

    if version.get("fecha_entrenamiento"):
        st.caption(f"Último entrenamiento registrado del modelo: `{version['fecha_entrenamiento']}`")


def render_admin_view():
    st.markdown(
        '<div class="page-heading">Administración del sistema</div>'
        '<div class="page-description">Gestiona usuarios, aprueba solicitudes médicas, monitorea reportes ciudadanos de la app móvil y revisa el estado del ecosistema.</div>',
        unsafe_allow_html=True,
    )

    rol_actual = (st.session_state.get("user_role") or "").strip().lower()
    if not DEMO_MODE and rol_actual not in ROLES_ADMIN_WEB:
        st.warning("Esta sección es exclusiva para administradores / funcionarios autorizados.")
        return

    current_uid = str(st.session_state.get("user_uid") or "")

    tab_usuarios, tab_senales, tab_sistema = st.tabs([
        "Usuarios y solicitudes médicas",
        "Reportes ciudadanos (App móvil)",
        "Estado del sistema",
    ])

    with tab_usuarios:
        _render_usuarios_tab(current_uid)

    with tab_senales:
        _render_senales_moviles_tab()

    with tab_sistema:
        _render_estado_sistema_tab()
