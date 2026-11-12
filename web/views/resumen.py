"""Vista: panorama estatal por enfermedad."""

import streamlit as st


def render_resumen_view():
    st.markdown(
        '<div class="page-heading">Panorama epidemiológico</div>'
        '<div class="page-description">Estado general de vigilancia en Jalisco.</div>',
        unsafe_allow_html=True,
    )

    enfermedades = [
        {
            "nombre": "Dengue",
            "nivel": "Alto",
            "color": "#b54755",
            "fondo": "#f7e9eb",
            "descripcion": (
                "Focos en la zona costera y el área metropolitana. "
                "Se mantiene vigilancia reforzada y control del vector."
            ),
        },
        {
            "nombre": "Influenza",
            "nivel": "Medio",
            "color": "#bd9b43",
            "fondo": "#f6f1df",
            "descripcion": (
                "Actividad estacional en seguimiento. "
                "Continúa la campaña de vacunación en unidades de salud."
            ),
        },
        {
            "nombre": "COVID-19",
            "nivel": "Bajo",
            "color": "#4e9577",
            "fondo": "#e9f3ed",
            "descripcion": (
                "Comportamiento estable. "
                "Se mantiene la vigilancia epidemiológica habitual."
            ),
        },
    ]

    columnas = st.columns(3, gap="medium")
    for columna, enfermedad in zip(columnas, enfermedades):
        with columna:
            st.markdown(
                f"""
                <article class="disease-card" style="--disease-color:{enfermedad['color']}">
                    <div class="disease-heading">
                        <span class="disease-symbol" aria-hidden="true"></span>
                        <h2>{enfermedad['nombre']}</h2>
                    </div>
                    <p>{enfermedad['descripcion']}</p>
                    <span class="disease-status"
                          style="color:{enfermedad['color']};background:{enfermedad['fondo']}">
                        <span class="status-dot" style="background:{enfermedad['color']}"></span>
                        Riesgo {enfermedad['nivel'].lower()}
                    </span>
                </article>
                """,
                unsafe_allow_html=True,
            )

    st.markdown(
        """
        <div class="overview-note">
            <strong>Lectura epidemiológica</strong>
            <span>El nivel resume señales regionales y no sustituye la valoración clínica.</span>
        </div>
        <div class="disclaimer-box">
            NOM-004-SSA3-2012: esta plataforma es una herramienta de orientación epidemiológica.
            Las proyecciones no sustituyen el diagnóstico clínico individual.
        </div>
        """,
        unsafe_allow_html=True,
    )
