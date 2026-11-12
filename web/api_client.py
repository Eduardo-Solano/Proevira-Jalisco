"""
Cliente centralizado para interactuar con la API REST y WebSockets de FastAPI.
Maneja autenticación JWT, llamadas a endpoints de vigilancia epidemiológica
y datos de demostración para visualización si el backend está fuera de línea.
"""

import os
import requests
import streamlit as st
from typing import Dict, Any, List, Optional

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000/api/v1")
WS_BASE_URL = os.getenv("WS_BASE_URL", "ws://127.0.0.1:8000/ws/alerts")
DEMO_MODE = os.getenv("PROEVIRA_DEMO_MODE", "true").strip().lower() in {"1", "true", "yes"}

# Municipios principales de Jalisco para datos de demostración
MUNICIPIOS_JALISCO = {
    "14039": {"nombre": "Guadalajara", "lat": 20.6767, "lon": -103.3475},
    "14120": {"nombre": "Zapopan", "lat": 20.7236, "lon": -103.3848},
    "14098": {"nombre": "Tlaquepaque", "lat": 20.6409, "lon": -103.3128},
    "14101": {"nombre": "Tonalá", "lat": 20.6244, "lon": -103.2343},
    "14097": {"nombre": "Tlajomulco de Zúñiga", "lat": 20.4742, "lon": -103.4447},
    "14067": {"nombre": "Puerto Vallarta", "lat": 20.6534, "lon": -105.2253},
    "14023": {"nombre": "Ciudad Guzmán (Zapotlán el Grande)", "lat": 19.7047, "lon": -103.4619},
    "14053": {"nombre": "Lagos de Moreno", "lat": 21.3533, "lon": -101.9317},
    "14093": {"nombre": "Tepatitlán de Morelos", "lat": 20.8172, "lon": -102.7636},
    "14015": {"nombre": "Autlán de Navarro", "lat": 19.7719, "lon": -104.3644},
}

class ApiClient:
    def __init__(self, base_url: str = API_BASE_URL):
        self.base_url = base_url.rstrip("/")

    def _get_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        token = st.session_state.get("auth_token")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def check_health(self) -> bool:
        """Verifica si el backend está respondiendo."""
        if DEMO_MODE:
            return False
        try:
            resp = requests.get(f"{self.base_url.replace('/api/v1', '')}/health", timeout=1.5)
            return resp.status_code == 200
        except Exception:
            return False

    # ------------------ AUTENTICACIÓN ------------------
    def login(self, email: str, password: str) -> Dict[str, Any]:
        """Inicia sesión contra /auth/login."""
        if DEMO_MODE:
            return {"success": False, "error": "La autenticación está deshabilitada en modo de demostración."}
        try:
            resp = requests.post(
                f"{self.base_url}/auth/login",
                json={"email": email, "password": password},
                headers={"Content-Type": "application/json"},
                timeout=3.0
            )
            if resp.status_code == 200:
                data = resp.json()
                st.session_state["auth_token"] = data.get("token")
                st.session_state["user_role"] = data.get("role")
                st.session_state["user_email"] = email
                st.session_state["user_uid"] = data.get("uid")
                st.session_state["municipio_id"] = data.get("municipio_id")
                st.session_state["backend_offline"] = False
                return {"success": True, "data": data}
            return {"success": False, "error": resp.json().get("detail", "Error de autenticación")}
        except Exception:
            # Fallback modo demo si no hay backend activo
            role = "funcionario" if "salud" in email or "jalisco" in email or "admin" in email else "medico"
            st.session_state["auth_token"] = "demo-mock-jwt-token"
            st.session_state["user_role"] = role
            st.session_state["user_email"] = email
            st.session_state["user_uid"] = "mock-user-123"
            st.session_state["municipio_id"] = "14039"
            st.session_state["backend_offline"] = True
            return {"success": True, "data": {"role": role, "email": email, "mock": True}}

    def register_medico(self, email: str, password: str, institucion: str, cedula: str) -> Dict[str, Any]:
        """Registra a un médico solicitando verificación posterior."""
        if DEMO_MODE:
            return {"success": False, "error": "El registro está deshabilitado en modo de demostración."}
        try:
            resp = requests.post(
                f"{self.base_url}/auth/register-medico",
                json={"email": email, "password": password, "institucion": institucion, "cedula": cedula},
                headers={"Content-Type": "application/json"},
                timeout=3.0
            )
            if resp.status_code in [200, 201]:
                return {"success": True, "data": resp.json()}
            return {"success": False, "error": resp.json().get("detail", "Error al registrar médico")}
        except Exception:
            return {"success": True, "data": {"uid": "mock-reg-1", "role": "medico", "verificado": False, "mock": True}}

    def logout(self):
        """Cierra sesión localmente."""
        keys = ["auth_token", "user_role", "user_email", "user_uid", "municipio_id", "backend_offline"]
        for k in keys:
            if k in st.session_state:
                del st.session_state[k]

    # ------------------ DASHBOARD Y KPIS ------------------
    def get_kpis(self) -> Dict[str, Any]:
        """Obtiene KPIs de vigilancia epidemiológica para la cabecera."""
        if DEMO_MODE:
            return {
                "casos_semana": 1248,
                "casos_variacion_pct": "+12.4%",
                "municipios_riesgo_alto": 6,
                "alertas_activas": 4,
                "hospitalizaciones_est": 82
            }
        try:
            resp = requests.get(f"{self.base_url}/dashboard/kpis", headers=self._get_headers(), timeout=2.0)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        # Mock de datos representativos de Jalisco
        return {
            "casos_semana": 1248,
            "casos_variacion_pct": "+12.4%",
            "municipios_riesgo_alto": 6,
            "alertas_activas": 4,
            "hospitalizaciones_est": 82
        }

    # ------------------ MAPA Y PREDICCIONES BULK ------------------
    def get_predictions_bulk(self, semana: str = "2026-W20", enfermedad: str = "dengue") -> List[Dict[str, Any]]:
        """Obtiene predicciones a nivel municipal para el mapa de calor."""
        if not DEMO_MODE:
            try:
                resp = requests.get(
                    f"{self.base_url}/predictions/bulk",
                    params={"semana": semana, "enfermedad": enfermedad},
                    headers=self._get_headers(),
                    timeout=3.0
                )
                if resp.status_code == 200:
                    return resp.json()
            except Exception:
                pass

        # Datos sintéticos para visualización inmediata en Streamlit
        niveles = {
            "14039": ("crítico", 480),   # Guadalajara
            "14120": ("alto", 310),      # Zapopan
            "14098": ("alto", 195),      # Tlaquepaque
            "14101": ("medio", 110),     # Tonalá
            "14097": ("medio", 85),      # Tlajomulco
            "14067": ("crítico", 140),   # Puerto Vallarta (zona costera dengue)
            "14023": ("medio", 34),      # Ciudad Guzmán
            "14053": ("bajo", 18),       # Lagos de Moreno
            "14093": ("bajo", 14),       # Tepatitlán
            "14015": ("alto", 62),       # Autlán
        }
        res = []
        for mun_id, meta in MUNICIPIOS_JALISCO.items():
            riesgo, casos = niveles.get(mun_id, ("bajo", 10))
            res.append({
                "municipio_id": mun_id,
                "municipio": meta["nombre"],
                "lat": meta["lat"],
                "lon": meta["lon"],
                "nivel_riesgo": riesgo,
                "casos_esperados": casos,
                "enfermedad": enfermedad,
                "semana": semana
            })
        return res

    # ------------------ DETALLE Y EXPLICABILIDAD SHAP ------------------
    def get_prediction_history(self, municipio_id: str, enfermedad: str = "dengue", semanas: int = 12) -> Dict[str, Any]:
        """Obtiene serie histórica + predicción futura."""
        if not DEMO_MODE:
            try:
                resp = requests.get(
                    f"{self.base_url}/predictions/history",
                    params={"municipio": municipio_id, "enfermedad": enfermedad, "semanas": semanas},
                    headers=self._get_headers(),
                    timeout=3.0
                )
                if resp.status_code == 200:
                    return resp.json()
            except Exception:
                pass

        # Mock de 12 semanas históricas y 4 proyectadas
        historico = []
        base = 25 if enfermedad == "dengue" else 40
        for i in range(1, 13):
            historico.append({
                "semana": f"2026-W{i:02d}",
                "casos": int(base + (i * 4.2) + ((i % 3) * 7))
            })
        prediccion = [
            {"semana": "2026-W13", "casos": int(base + 55), "nivel": "medio"},
            {"semana": "2026-W14", "casos": int(base + 68), "nivel": "alto"},
            {"semana": "2026-W15", "casos": int(base + 74), "nivel": "alto"},
            {"semana": "2026-W16", "casos": int(base + 89), "nivel": "crítico"},
        ]
        return {"historico": historico, "prediccion": prediccion}

    def get_prediction_explain(self, municipio_id: str, semana: str = "2026-W20") -> Dict[str, Any]:
        """Obtiene valores SHAP de la inferencia para explicabilidad médica."""
        if not DEMO_MODE:
            try:
                resp = requests.get(
                    f"{self.base_url}/predictions/explain",
                    params={"municipio": municipio_id, "semana": semana},
                    headers=self._get_headers(),
                    timeout=3.0
                )
                if resp.status_code == 200:
                    return resp.json()
            except Exception:
                pass

        return {
            "base_value": 0.25,
            "feature_importance": [
                {"feature": "Precipitación acumulada (mm) [t-2]", "shap": 0.28, "impacto": "Aumenta riesgo"},
                {"feature": "Temperatura media (°C) [t-1]", "shap": 0.21, "impacto": "Aumenta riesgo"},
                {"feature": "Casos confirmados semana anterior", "shap": 0.17, "impacto": "Aumenta riesgo"},
                {"feature": "Humedad relativa promedio (%)", "shap": 0.09, "impacto": "Aumenta riesgo"},
                {"feature": "Operativos de descacharrización activos", "shap": -0.14, "impacto": "Disminuye riesgo"},
                {"feature": "Cobertura de vacunación / fumigación", "shap": -0.08, "impacto": "Disminuye riesgo"}
            ]
        }

    # ------------------ ALERTAS ------------------
    def get_alerts(self, municipio_id: Optional[str] = None, activa: bool = True) -> List[Dict[str, Any]]:
        """Lista alertas activas con filtro opcional por municipio."""
        if not DEMO_MODE:
            try:
                params = {"activa": str(activa).lower()}
                if municipio_id:
                    params["municipio"] = municipio_id
                resp = requests.get(f"{self.base_url}/alerts", params=params, headers=self._get_headers(), timeout=3.0)
                if resp.status_code == 200:
                    return resp.json()
            except Exception:
                pass

        return [
            {
                "id": "alt-001",
                "municipio_id": "14039",
                "municipio": "Guadalajara",
                "nivel": "crítico",
                "mensaje": "Brote activo de Dengue Serotipo 3 en zona oriente. Refuerzo de brigadas de nebulización.",
                "ts": "2026-11-11 18:30",
                "activa": True
            },
            {
                "id": "alt-002",
                "municipio_id": "14067",
                "municipio": "Puerto Vallarta",
                "nivel": "alto",
                "mensaje": "Incremento de casos sospechosos posterior a lluvias atípicas. Monitoreo en centros de salud.",
                "ts": "2026-11-11 14:15",
                "activa": True
            },
            {
                "id": "alt-003",
                "municipio_id": "14120",
                "municipio": "Zapopan",
                "nivel": "medio",
                "mensaje": "Aumento estacional de cuadros respiratorios tipo Influenza.",
                "ts": "2026-11-10 09:00",
                "activa": True
            }
        ]

    def create_alert(self, municipio_id: str, nivel: str, mensaje: str) -> Dict[str, Any]:
        """Crea una nueva alerta (Rol: funcionario)."""
        if DEMO_MODE:
            return {"success": False, "error": "Modo de demostración: la alerta no se envió."}
        try:
            resp = requests.post(
                f"{self.base_url}/alerts",
                json={"municipio_id": municipio_id, "nivel": nivel, "mensaje": mensaje},
                headers=self._get_headers(),
                timeout=3.0
            )
            if resp.status_code in [200, 201]:
                return {"success": True, "data": resp.json()}
            return {"success": False, "error": resp.json().get("detail", "Error al emitir alerta")}
        except Exception:
            return {"success": True, "data": {"id": "mock-alt-new", "emitida": True, "mock": True}}

    def toggle_alert(self, alert_id: str, activa: bool) -> Dict[str, Any]:
        """Activa o desactiva una alerta existente."""
        if DEMO_MODE:
            return {"success": False, "error": "Modo de demostración: no se modificaron alertas."}
        try:
            resp = requests.patch(
                f"{self.base_url}/alerts/{alert_id}",
                json={"activa": activa},
                headers=self._get_headers(),
                timeout=3.0
            )
            if resp.status_code == 200:
                return {"success": True, "data": resp.json()}
            return {"success": False, "error": "No se pudo actualizar la alerta"}
        except Exception:
            return {"success": True, "data": {"id": alert_id, "activa": activa, "mock": True}}

# Instancia singleton para importar en las páginas
api = ApiClient()
