"""
Vista: Consola de Alertas Epidemiológicas.
"""

from datetime import date

import streamlit as st
from api_client import ApiError, api, MUNICIPIOS_JALISCO

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

        alertas = api.get_alerts(
            municipio_id=None if filtro == "todos" else filtro,
            activa=solo_act,
        )

        if not alertas:
            st.info("Sin alertas activas para los filtros seleccionados.")
        else:
            for a in alertas:
                niv = a.get("nivel", "medio").lower()
                s = ESTILO_NIVEL.get(niv, ESTILO_NIVEL["medio"])
                st.markdown(f"""
                <div style="border-left:5px solid {s['color']};background:{s['bg']};
                            padding:0.9rem 1rem;border-radius:6px;margin-bottom:0.7rem;">
                    <div style="display:flex;justify-content:space-between;align-items:center;">
                        <span style="font-weight:700;color:{s['color']};font-size:0.88rem;">
                            <span style="display:inline-block;width:8px;height:8px;border-radius:50%;
                                         margin-right:5px;background:{s['color']};"></span>
                            {niv.upper()} · {a.get('municipio','')}
                        </span>
                        <span style="font-size:0.76rem;color:#666;">{a.get('ts','')}</span>
                    </div>
                    <div style="color:#334155;font-size:0.88rem;margin-top:4px;">{a.get('mensaje','')}</div>
                </div>""", unsafe_allow_html=True)

    # ── Emisión de alerta ──
    with col_emit:
        st.markdown("##### Emitir nueva alerta")
        st.caption("Al guardar se difunde por WebSocket a la red médica y ciudadana.")

        with st.form("form_alerta"):
            mun_id = st.selectbox(
                "Municipio",
                list(MUNICIPIOS_JALISCO.keys()),
                format_func=lambda k: MUNICIPIOS_JALISCO[k]["nombre"],
            )
            nivel = st.select_slider("Severidad", ["bajo", "medio", "alto", "crítico"], value="alto")
            mensaje = st.text_area("Descripción", placeholder="Foco, protocolo o medidas...", height=100)
            enviar = st.form_submit_button("Emitir alerta", use_container_width=True)

            if enviar:
                if not mensaje.strip():
                    st.warning("Escribe el mensaje antes de emitir.")
                else:
                    res = api.create_alert(mun_id, nivel, mensaje)
                    if res.get("success"):
                        st.success(f"Alerta emitida para {MUNICIPIOS_JALISCO[mun_id]['nombre']}.")
                        st.rerun()
                    else:
                        st.error(res.get("error", "Error al emitir."))

    if (st.session_state.get("user_role") or "").strip().lower() in {
        "funcionario",
        "medico",
        "admin",
        "administrador",
    }:
        st.divider()
        with st.container(border=True):
            st.markdown("##### Borradores predictivos para revisión")
            st.caption(
                "Se calculan con las proyecciones municipales de las próximas cuatro semanas. "
                "Solo los niveles medio, alto y crítico generan borradores; nada se publica "
                "hasta que personal autorizado lo apruebe."
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
                    nivel = borrador.get("nivel", "medio").lower()
                    municipio_id = str(borrador.get("municipio", ""))
                    municipio_nombre = MUNICIPIOS_JALISCO.get(
                        municipio_id, {"nombre": municipio_id or "Municipio"}
                    )["nombre"]
                    enfermedad = borrador.get("enfermedad", "").upper()
                    fecha = _fecha_inicio_semana(borrador.get("semana", ""))

                    with st.container(border=True):
                        st.markdown(
                            f"**{nivel.upper()} · {municipio_nombre} · {enfermedad}**  \n"
                            f"Semana que inicia el **{fecha}** · "
                            f"**{int(round(float(borrador.get('casos_esperados', 0)))):,} casos estimados**"
                        )
                        st.caption(borrador.get("mensaje", ""))
                        aprobar_col, descartar_col = st.columns(2)
                        if aprobar_col.button(
                            "Aprobar y emitir",
                            key=f"approve_predictive_draft_{borrador['id']}",
                            type="primary",
                            use_container_width=True,
                        ):
                            result = api.review_predicted_alert_draft(borrador["id"], "aprobar")
                            if result.get("success"):
                                st.success("Alerta aprobada y emitida.")
                                st.rerun()
                            else:
                                st.error(result.get("error", "No se pudo aprobar el borrador."))
                        if descartar_col.button(
                            "Descartar",
                            key=f"discard_predictive_draft_{borrador['id']}",
                            use_container_width=True,
                        ):
                            result = api.review_predicted_alert_draft(borrador["id"], "descartar")
                            if result.get("success"):
                                st.success("Borrador descartado.")
                                st.rerun()
                            else:
                                st.error(result.get("error", "No se pudo descartar el borrador."))
