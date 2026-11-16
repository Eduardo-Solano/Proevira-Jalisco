"""Estado de conexión independiente de la navegación del dashboard."""

import streamlit as st

from api_client import DEMO_MODE, api


@st.fragment(run_every="15s")
def render_connection_status():
    if DEMO_MODE:
        return

    was_offline = st.session_state.get("backend_offline")
    # El botón se procesa antes de la comprobación para que un reintento
    # ejecute una sola consulta y nunca repita operaciones de escritura.
    if was_offline:
        st.button("Reintentar conexión", key="retry_backend_connection")

    with st.spinner("Revisando conexión con el servidor…"):
        online = api.check_health()

    st.session_state["backend_offline"] = not online
    if not online:
        st.error(
            "No podemos comunicarnos con el servidor en este momento. "
            "Tu sesión sigue abierta. Revisa tu conexión a internet o espera unos momentos. "
            "Volveremos a revisar automáticamente; también puedes reintentar la conexión."
        )
        if was_offline is None:
            st.button("Reintentar conexión", key="retry_backend_connection")
    else:
        st.caption("Conexión con el servidor disponible")

    if was_offline is not None and was_offline != (not online):
        api._clear_read_cache()
        # Actualiza también la vista principal cuando la conexión cambia.
        st.rerun()
