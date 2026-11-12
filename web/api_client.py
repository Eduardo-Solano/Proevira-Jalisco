"""Cliente para la API de FastAPI y datos explícitos de demostración."""

import os
from typing import Any, Dict, List, Optional

import requests
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000/api/v1").rstrip("/")
WS_BASE_URL = os.getenv("WS_BASE_URL", "ws://127.0.0.1:8000/ws/alerts")
DEMO_MODE = os.getenv("PROEVIRA_DEMO_MODE", "false").strip().lower() in {"1", "true", "yes"}
REQUEST_TIMEOUT = 5.0

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

ENFERMEDADES_API = {"covid-19": "covid", "covid": "covid"}


class ApiError(RuntimeError):
    """Error explícito al solicitar o interpretar una respuesta del backend."""


class ApiClient:
    def __init__(self, base_url: str = API_BASE_URL):
        self.base_url = base_url.rstrip("/")
        self.root_url = self.base_url.removesuffix("/api/v1")

    def _get_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        token = st.session_state.get("auth_token")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    @staticmethod
    def _enfermedad_api(enfermedad: str) -> str:
        return ENFERMEDADES_API.get(enfermedad.lower(), enfermedad.lower())

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        root_path: bool = False,
    ) -> Any:
        url = f"{self.root_url if root_path else self.base_url}/{path.lstrip('/')}"
        try:
            response = requests.request(
                method,
                url,
                params=params,
                json=json,
                headers=headers or self._get_headers(),
                timeout=REQUEST_TIMEOUT,
            )
        except requests.RequestException as error:
            raise ApiError(f"No se pudo conectar con la API ({url}): {error}") from error

        if not response.ok:
            try:
                body = response.json()
            except ValueError:
                body = {}
            detail = body.get("detail") if isinstance(body, dict) else None
            detail = detail or response.text or f"HTTP {response.status_code}"
            raise ApiError(f"API {response.status_code} en {path}: {detail}")

        if response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except ValueError as error:
            raise ApiError(f"La API devolvió una respuesta JSON inválida en {path}.") from error

    def check_health(self) -> bool:
        if DEMO_MODE:
            return False
        try:
            health = self._request("GET", "/health", root_path=True)
        except ApiError:
            return False
        return health.get("status") == "ok"

    def login(self, email: str, password: str) -> Dict[str, Any]:
        if DEMO_MODE:
            return {"success": False, "error": "El inicio de sesión no está disponible en modo de demostración."}
        try:
            data = self._request(
                "POST",
                "/auth/login",
                json={"email": email, "password": password},
                headers={"Content-Type": "application/json"},
            )
        except ApiError as error:
            return {"success": False, "error": str(error)}

        if not data.get("token"):
            return {"success": False, "error": "La respuesta del backend no contiene un token de acceso."}
        st.session_state["auth_token"] = data["token"]
        st.session_state["user_role"] = data.get("role")
        st.session_state["user_email"] = data.get("email", email)
        st.session_state["user_uid"] = data.get("uid")
        st.session_state["municipio_id"] = data.get("municipio_id")
        return {"success": True, "data": data}

    def register_medico(self, email: str, password: str, institucion: str, cedula: str) -> Dict[str, Any]:
        if DEMO_MODE:
            return {"success": False, "error": "El registro está deshabilitado en modo de demostración."}
        try:
            data = self._request(
                "POST",
                "/auth/register-medico",
                json={"email": email, "password": password, "institucion": institucion, "cedula": cedula},
                headers={"Content-Type": "application/json"},
            )
            return {"success": True, "data": data}
        except ApiError as error:
            return {"success": False, "error": str(error)}

    def logout(self) -> None:
        for key in ("auth_token", "user_role", "user_email", "user_uid", "municipio_id", "backend_offline"):
            st.session_state.pop(key, None)

    def get_kpis(self) -> Dict[str, Any]:
        if DEMO_MODE:
            return {
                "casos_semana": 1248,
                "casos_variacion_pct": "+12.4%",
                "municipios_riesgo_alto": 6,
                "alertas_activas": 4,
                "hospitalizaciones_est": 82,
            }
        return self._request("GET", "/dashboard/kpis")

    def get_dashboard_summary(self, semana: Optional[str] = None) -> Dict[str, Any]:
        if DEMO_MODE:
            dengue = self.get_predictions_bulk(semana=semana, enfermedad="dengue")
            influenza = self.get_predictions_bulk(semana=semana, enfermedad="influenza")
            covid = self.get_predictions_bulk(semana=semana, enfermedad="covid")
            influenza_por_id = {item["municipio_id"]: item for item in influenza}
            covid_por_id = {item["municipio_id"]: item for item in covid}
            por_municipio = [
                {
                    "municipio_id": item["municipio_id"],
                    "nombre": item["municipio"],
                    "lat": item["lat"],
                    "lon": item["lon"],
                    "dengue_casos": item["casos_esperados"],
                    "dengue_riesgo": item["nivel_riesgo"],
                    "influenza_casos": influenza_por_id[item["municipio_id"]]["casos_esperados"],
                    "covid_casos": covid_por_id[item["municipio_id"]]["casos_esperados"],
                }
                for item in dengue
            ]
            historia = self.get_prediction_history("14039", semanas=12)
            tendencia = [
                {
                    "semana": item["semana"],
                    "dengue": item["casos"],
                    "influenza": item["casos"],
                    "covid": item["casos"],
                }
                for item in historia["historico"]
            ]
            return {
                "semana": semana or dengue[0]["semana"],
                "totales": {
                    "dengue": sum(item["casos_esperados"] for item in dengue),
                    "influenza": sum(item["casos_esperados"] for item in influenza),
                    "covid": sum(item["casos_esperados"] for item in covid),
                },
                "tendencia": tendencia,
                "por_municipio": por_municipio,
            }

        params = {"semana": semana} if semana else None
        return self._request("GET", "/dashboard/summary", params=params)

    def get_model_info(self) -> Dict[str, Any]:
        if DEMO_MODE:
            return {
                "modelo": "Random Forest (demostración)",
                "fecha_entrenamiento": None,
                "ultima_semana_datos": None,
                "semana_prediccion": None,
            }
        return self._request("GET", "/version", root_path=True)

    def get_model_metrics(self) -> Optional[Dict[str, Any]]:
        if DEMO_MODE:
            return None
        return self._request("GET", "/model/metrics")

    def get_predictions_bulk(self, semana: Optional[str] = None, enfermedad: str = "dengue") -> List[Dict[str, Any]]:
        enfermedad_api = self._enfermedad_api(enfermedad)
        if DEMO_MODE:
            niveles = {
                "14039": ("crítico", 480),
                "14120": ("alto", 310),
                "14098": ("alto", 195),
                "14101": ("medio", 110),
                "14097": ("medio", 85),
                "14067": ("crítico", 140),
                "14023": ("medio", 34),
                "14053": ("bajo", 18),
                "14093": ("bajo", 14),
                "14015": ("alto", 62),
            }
            return [
                {
                    "municipio_id": mid,
                    "municipio": meta["nombre"],
                    "nombre": meta["nombre"],
                    "lat": meta["lat"],
                    "lon": meta["lon"],
                    "nivel_riesgo": niveles.get(mid, ("bajo", 10))[0],
                    "casos_esperados": niveles.get(mid, ("bajo", 10))[1],
                    "enfermedad": enfermedad.lower(),
                    "semana": semana or "Demostración",
                }
                for mid, meta in MUNICIPIOS_JALISCO.items()
            ]

        params = {"enfermedad": enfermedad_api}
        if semana:
            params["semana"] = semana
        data = self._request("GET", "/predictions/bulk", params=params)
        return [
            {
                **item,
                "municipio_id": str(item["municipio"]),
                "municipio": item.get("nombre") or str(item["municipio"]),
                "municipio_nombre": item.get("nombre") or str(item["municipio"]),
                "enfermedad": enfermedad.lower(),
            }
            for item in data
        ]

    def get_prediction_history(
        self,
        municipio_id: str,
        enfermedad: str = "dengue",
        semanas: int = 12,
    ) -> Dict[str, Any]:
        enfermedad_api = self._enfermedad_api(enfermedad)
        if DEMO_MODE:
            base = 25 if enfermedad_api == "dengue" else 40
            historico = [
                {
                    "semana": f"2026-W{i:02d}",
                    "casos": int(base + i * 4.2 + (i % 3) * 7),
                }
                for i in range(1, 13)
            ]
            prediccion = [
                {"semana": "2026-W13", "casos": base + 55, "nivel": "medio"},
                {"semana": "2026-W14", "casos": base + 68, "nivel": "alto"},
                {"semana": "2026-W15", "casos": base + 74, "nivel": "alto"},
                {"semana": "2026-W16", "casos": base + 89, "nivel": "crítico"},
            ]
            return {"historico": historico[-semanas:], "prediccion": prediccion}

        return self._request(
            "GET",
            "/predictions/history",
            params={"municipio": municipio_id, "enfermedad": enfermedad_api, "semanas": semanas},
        )

    def get_prediction_explain(
        self,
        municipio_id: str,
        semana: Optional[str] = None,
        enfermedad: str = "dengue",
    ) -> Dict[str, Any]:
        enfermedad_api = self._enfermedad_api(enfermedad)
        if DEMO_MODE:
            return {
                "base_value": 0.25,
                "feature_importance": [
                    {"feature": "Precipitación acumulada (mm) [t-2]", "shap": 0.28, "impacto": "Demostración"},
                    {"feature": "Temperatura media (°C) [t-1]", "shap": 0.21, "impacto": "Demostración"},
                    {"feature": "Casos confirmados semana anterior", "shap": 0.17, "impacto": "Demostración"},
                    {"feature": "Humedad relativa promedio (%)", "shap": 0.09, "impacto": "Demostración"},
                ],
            }
        params: Dict[str, Any] = {"municipio": municipio_id, "enfermedad": enfermedad_api}
        if semana:
            params["semana"] = semana
        return self._request("GET", "/predictions/explain", params=params)

    def get_alerts(self, municipio_id: Optional[str] = None, activa: bool = True) -> List[Dict[str, Any]]:
        if DEMO_MODE:
            return [
                {
                    "id": "alt-001",
                    "municipio_id": "14039",
                    "municipio": "Guadalajara",
                    "nivel": "crítico",
                    "mensaje": "Brote activo de Dengue Serotipo 3 en zona oriente. Refuerzo de brigadas de nebulización.",
                    "ts": "2026-11-11 18:30",
                    "activa": True,
                },
                {
                    "id": "alt-002",
                    "municipio_id": "14067",
                    "municipio": "Puerto Vallarta",
                    "nivel": "alto",
                    "mensaje": "Incremento de casos sospechosos posterior a lluvias atípicas. Monitoreo en centros de salud.",
                    "ts": "2026-11-11 14:15",
                    "activa": True,
                },
                {
                    "id": "alt-003",
                    "municipio_id": "14120",
                    "municipio": "Zapopan",
                    "nivel": "medio",
                    "mensaje": "Aumento estacional de cuadros respiratorios tipo Influenza.",
                    "ts": "2026-11-10 09:00",
                    "activa": True,
                },
            ]

        params: Dict[str, Any] = {"activa": activa}
        if municipio_id:
            params["municipio"] = municipio_id
        alerts = self._request("GET", "/alerts", params=params)
        return [
            {
                **alert,
                "municipio_id": str(alert["municipio"]) if alert.get("municipio") else None,
                "municipio": MUNICIPIOS_JALISCO.get(
                    str(alert.get("municipio")),
                    {"nombre": alert.get("municipio") or "Región"},
                )["nombre"],
            }
            for alert in alerts
        ]

    def create_alert(self, municipio_id: str, nivel: str, mensaje: str) -> Dict[str, Any]:
        if DEMO_MODE:
            return {"success": False, "error": "Modo de demostración: la alerta no se envió."}
        try:
            data = self._request(
                "POST",
                "/alerts",
                json={"municipio_id": municipio_id, "nivel": nivel, "mensaje": mensaje},
            )
            return {"success": True, "data": data}
        except ApiError as error:
            return {"success": False, "error": str(error)}

    def toggle_alert(self, alert_id: str, activa: bool) -> Dict[str, Any]:
        if DEMO_MODE:
            return {"success": False, "error": "Modo de demostración: no se modificaron alertas."}
        try:
            data = self._request("PATCH", f"/alerts/{alert_id}", json={"activa": activa})
            return {"success": True, "data": data}
        except ApiError as error:
            return {"success": False, "error": str(error)}


api = ApiClient()
