"""
Vista: Consola de Alertas Epidemiológicas.
"""

from datetime import date
import html

import streamlit as st
from api_client import ApiError, api, MUNICIPIOS_JALISCO

NIVELES_ALERTA = ["bajo", "medio", "alto", "crítico"]

ESTILO_NIVEL = {
    "crítico": {"color": "#d32f2f", "bg": "#ffebee"},
    "alto":    {"color": "#f57c00", "bg": "#fff3e0"},
    "medio":   {"color": "#fbc02d", "bg": "#fffde7"},
    "bajo":    {"color": "#388e3c", "bg": "#e8f5e9"},
}


def _fecha_inicio_semana(semana: str) -> str:
    try:
        anio, numero = semana.split("-W", 1)
        return date.fromisocalendar(int(anio), int(numero), 1).strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return semana


def render_alertas_view():
    puede_gestionar = (st.session_state.get("user_role") or "").strip().lower() in {
        "funcionario",
        "medico",
        "admin",
        "administrador",
    }

    col_feed, col_emit = st.columns([3, 2])

    # ── Feed de alertas ──
    with col_feed:
        st.markdown("##### Alertas vigentes")

        f1, f2 = st.columns([2, 1])
        with f1:
            filtro = st.selectbox(
                "Municipio",
                ["todos"] + list(MUNICIPIOS_JALISCO.keys()),
                format_func=lambda k: "Todos" if k == "todos" else MUNICIPIOS_JALISCO[k]["nombre"],
                key="al_filtro",
            )
        with f2:
            solo_act = st.checkbox("Solo activas", True, key="al_act")

        filtro_sig = (filtro, solo_act)
        if st.session_state.get("_alerts_filter_sig") != filtro_sig:
            st.session_state["_alerts_filter_sig"] = filtro_sig
            st.session_state.pop("confirm_delete_alert_id", None)

        alertas = api.get_alerts(
            municipio_id=None if filtro == "todos" else filtro,
            activa=solo_act,
        )

        # Un único contenedor con key dependiente del filtro evita que Streamlit
        # conserve tarjetas atenuadas del municipio anterior al cambiar de selección.
        feed_slot = st.empty()
        with feed_slot.container(key=f"alerts_feed_{filtro}_{solo_act}"):
            if not alertas:
                st.info("Sin alertas activas para los filtros seleccionados.")
            else:
                confirm_delete_id = st.session_state.get("confirm_delete_alert_id")
                for a in alertas:
                    alert_id = a.get("id")
                    niv = str(a.get("nivel", "medio")).lower()
                    s = ESTILO_NIVEL.get(niv, ESTILO_NIVEL["medio"])
                    municipio_texto = html.escape(str(a.get("municipio", "")))
                    mensaje_texto = html.escape(str(a.get("mensaje", "")))
                    ts_texto = html.escape(str(a.get("ts", "")))
                    activa = bool(a.get("activa", True))
                    estado_tag = "" if activa else " · INACTIVA"

                    with st.container(key=f"alert_card_{filtro}_{solo_act}_{alert_id}"):
                        st.markdown(f"""
                        <div style="border-left:5px solid {s['color']};background:{s['bg']};
                                    padding:0.9rem 1rem;border-radius:6px;margin-bottom:0.35rem;">
                            <div style="display:flex;justify-content:space-between;align-items:center;">
                                <span style="font-weight:700;color:{s['color']};font-size:0.88rem;">
                                    <span style="display:inline-block;width:8px;height:8px;border-radius:50%;
                                                 margin-right:5px;background:{s['color']};"></span>
                                    {html.escape(niv.upper())} · {municipio_texto}{estado_tag}
                                </span>
                                <span style="font-size:0.76rem;color:#666;">{ts_texto}</span>
                            </div>
                            <div style="color:#334155;font-size:0.88rem;margin-top:4px;">{mensaje_texto}</div>
                        </div>""", unsafe_allow_html=True)

                        if puede_gestionar and alert_id is not None:
                            act_col, del_col, cancel_col = st.columns([1.2, 1.2, 2.6])
                            toggle_label = "Desactivar" if activa else "Reactivar"
                            if act_col.button(toggle_label, key=f"toggle_alert_{alert_id}", use_container_width=True):
                                res = api.toggle_alert(alert_id, not activa)
                                if res.get("success"):
                                    st.session_state.pop("confirm_delete_alert_id", None)
                                    st.rerun()
                                else:
                                    st.error(res.get("error", "No se pudo actualizar la alerta."))

                            if confirm_delete_id == alert_id:
                                if del_col.button(
                                    "Confirmar borrado",
                                    key=f"confirm_del_alert_{alert_id}",
                                    type="primary",
                                    use_container_width=True,
                                ):
                                    res = api.delete_alert(alert_id)
                                    if res.get("success"):
                                        st.session_state.pop("confirm_delete_alert_id", None)
                                        st.success("Alerta eliminada.")
                                        st.rerun()
                                    else:
                                        st.error(res.get("error", "No se pudo eliminar la alerta."))
                                if cancel_col.button("Cancelar", key=f"cancel_del_alert_{alert_id}"):
                                    st.session_state.pop("confirm_delete_alert_id", None)
                                    st.rerun()
                            else:
                                if del_col.button(
                                    "Eliminar",
                                    key=f"delete_alert_{alert_id}",
                                    use_container_width=True,
                                ):
                                    st.session_state["confirm_delete_alert_id"] = alert_id
                                    st.rerun()

                        st.markdown("<div style='margin-bottom:0.45rem'></div>", unsafe_allow_html=True)

    # ── Emisión de alerta personalizada ──
    with col_emit:
        st.markdown("##### Emitir nueva alerta")
        st.caption("Redacta el aviso personalizado; al guardar se difunde por WebSocket a la red médica y ciudadana.")

        with st.form("form_alerta"):
            mun_opciones = ["__todas__"] + list(MUNICIPIOS_JALISCO.keys())
            mun_id = st.selectbox(
                "Municipio",
                mun_opciones,
                index=1 if len(mun_opciones) > 1 else 0,
                format_func=lambda k: (
                    "Toda la Región Centro (general)"
                    if k == "__todas__"
                    else MUNICIPIOS_JALISCO[k]["nombre"]
                ),
            )
            nivel = st.select_slider("Severidad", NIVELES_ALERTA, value="alto")
            mensaje = st.text_area("Mensaje personalizado", placeholder="Foco, protocolo o medidas...", height=100)
            enviar = st.form_submit_button("Emitir alerta", use_container_width=True)

            if enviar:
                if not mensaje.strip():
                    st.warning("Escribe el mensaje antes de emitir.")
                else:
                    target_mun = None if mun_id == "__todas__" else mun_id
                    res = api.create_alert(target_mun, nivel, mensaje.strip())
                    if res.get("success"):
                        nombre_dest = (
                            "toda la Región Centro"
                            if target_mun is None
                            else MUNICIPIOS_JALISCO[target_mun]["nombre"]
                        )
                        st.success(f"Alerta emitida para {nombre_dest}.")
                        st.rerun()
                    else:
                        st.error(res.get("error", "Error al emitir."))

    if puede_gestionar:
        st.divider()
        with st.container(border=True):
            st.markdown("##### Borradores predictivos para revisión")
            st.caption(
                "Se detectan con las proyecciones municipales de las próximas cuatro semanas "
                "(niveles medio, alto y crítico). Personaliza la severidad y el mensaje antes de emitir; "
                "nada se publica con formato automático."
            )

            if not st.session_state.get("_predictive_drafts_auto_attempted"):
                result = api.generate_predicted_alert_drafts()
                st.session_state["_predictive_drafts_auto_attempted"] = True
                if result.get("success"):
                    st.session_state["_predictive_drafts_generation_error"] = None
                else:
                    st.session_state["_predictive_drafts_generation_error"] = result.get(
                        "error", "No se pudieron generar los borradores."
                    )

            generation_error = st.session_state.get("_predictive_drafts_generation_error")
            if generation_error:
                st.warning(f"No se generaron borradores automáticamente: {generation_error}")

            if st.button("Actualizar borradores desde las proyecciones", key="refresh_predictive_drafts"):
                result = api.generate_predicted_alert_drafts()
                if result.get("success"):
                    st.session_state["_predictive_drafts_generation_error"] = None
                    st.success(
                        "Borradores actualizados: "
                        f"{result['data'].get('borradores_creados', 0)} nuevos, "
                        f"{result['data'].get('borradores_actualizados', 0)} actualizados."
                    )
                    st.rerun()
                else:
                    st.error(result.get("error", "No se pudieron generar los borradores."))

            try:
                borradores = api.get_predicted_alert_drafts()
                borradores_disponibles = True
            except ApiError as error:
                st.error(f"No se pudieron cargar los borradores predictivos: {error}")
                borradores = []
                borradores_disponibles = False

            if borradores_disponibles and not borradores:
                st.info("No hay borradores pendientes de revisión para la Región Centro.")
            elif borradores:
                st.caption(f"{len(borradores)} borrador(es) pendiente(s) de revisión.")
                for borrador in borradores:
                    draft_id = borrador["id"]
                    nivel_sugerido = str(borrador.get("nivel", "medio")).lower()
                    if nivel_sugerido not in NIVELES_ALERTA:
                        nivel_sugerido = "medio"
                    municipio_id = str(borrador.get("municipio", ""))
                    municipio_nombre = MUNICIPIOS_JALISCO.get(
                        municipio_id, {"nombre": municipio_id or "Municipio"}
                    )["nombre"]
                    enfermedad = str(borrador.get("enfermedad", "")).upper()
                    fecha = _fecha_inicio_semana(borrador.get("semana", ""))

                    with st.container(border=True):
                        st.markdown(
                            f"**{municipio_nombre} · {enfermedad}** (nivel sugerido: **{nivel_sugerido.upper()}**)  \n"
                            f"Semana que inicia el **{fecha}** · "
                            f"**{int(round(float(borrador.get('casos_esperados', 0)))):,} casos estimados**"
                        )
                        nivel_editado = st.selectbox(
                            "Severidad de la alerta",
                            NIVELES_ALERTA,
                            index=NIVELES_ALERTA.index(nivel_sugerido),
                            key=f"draft_nivel_{draft_id}",
                        )
                        mensaje_personalizado = st.text_area(
                            "Mensaje personalizado de la alerta",
                            value="",
                            placeholder=f"Redacta el aviso y medidas recomendadas para {municipio_nombre} ({enfermedad})...",
                            key=f"draft_mensaje_{draft_id}",
                            height=90,
                        )
                        aprobar_col, descartar_col = st.columns(2)
                        if aprobar_col.button(
                            "Aprobar y emitir",
                            key=f"approve_predictive_draft_{draft_id}",
                            type="primary",
                            use_container_width=True,
                        ):
                            if not mensaje_personalizado.strip():
                                st.warning("Escribe un mensaje personalizado antes de aprobar y emitir la alerta.")
                            else:
                                result = api.review_predicted_alert_draft(
                                    draft_id,
                                    "aprobar",
                                    nivel=nivel_editado,
                                    mensaje=mensaje_personalizado.strip(),
                                )
                                if result.get("success"):
                                    st.success("Alerta personalizada aprobada y emitida.")
                                    st.rerun()
                                else:
                                    st.error(result.get("error", "No se pudo aprobar el borrador."))
                        if descartar_col.button(
                            "Descartar",
                            key=f"discard_predictive_draft_{draft_id}",
                            use_container_width=True,
                        ):
                            result = api.review_predicted_alert_draft(draft_id, "descartar")
                            if result.get("success"):
                                st.success("Borrador descartado.")
                                st.rerun()
                            else:
                                st.error(result.get("error", "No se pudo descartar el borrador."))
