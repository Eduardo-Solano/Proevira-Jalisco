"""Cliente para la API de FastAPI y datos explícitos de demostración."""

import copy
import hashlib
import os
import time
from typing import Any, Dict, List, Optional

import requests
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000/api/v1").rstrip("/")
WS_BASE_URL = os.getenv("WS_BASE_URL", "ws://127.0.0.1:8000/ws/alerts")
DEMO_MODE = os.getenv("PROEVIRA_DEMO_MODE", "false").strip().lower() in {"1", "true", "yes"}
REQUEST_TIMEOUT = 60.0

MUNICIPIOS_JALISCO = {
    "14039": {"nombre": "Guadalajara", "lat": 20.676470, "lon": -103.347811},
    "14120": {"nombre": "Zapopan", "lat": 20.716405, "lon": -103.416947},
    "14098": {"nombre": "San Pedro Tlaquepaque", "lat": 20.610214, "lon": -103.320670},
    "14101": {"nombre": "Tonalá", "lat": 20.630600, "lon": -103.251448},
    "14097": {"nombre": "Tlajomulco de Zúñiga", "lat": 20.521658, "lon": -103.432591},
    "14070": {"nombre": "El Salto", "lat": 20.542290, "lon": -103.282728},
    "14124": {"nombre": "Zapotlanejo", "lat": 20.622212, "lon": -103.068761},
    "14044": {"nombre": "Ixtlahuacán de los Membrillos", "lat": 20.385805, "lon": -103.191998},
    "14045": {"nombre": "Ixtlahuacán del Río", "lat": 20.863757, "lon": -103.210450},
    "14051": {"nombre": "Juanacatlán", "lat": 20.507934, "lon": -103.167543},
    "14029": {"nombre": "Cuquío", "lat": 20.930300, "lon": -103.028588},
    "14071": {"nombre": "San Cristóbal de la Barranca", "lat": 21.046300, "lon": -103.427390},
}

ENFERMEDADES_API = {"covid-19": "covid", "covid": "covid"}


class ApiError(RuntimeError):
    """Error explícito al solicitar o interpretar una respuesta del backend."""


def _http_error_message(status_code: int, path: str) -> str:
    """Traduce errores del servicio sin exponer su respuesta ni datos internos."""
    if path == "/auth/reset-password" and status_code in {400, 422}:
        return "No se pudo cambiar la contraseña. Revisa sus requisitos o solicita un nuevo código si la verificación ya venció."
    if path == "/auth/verify-recovery-code" and status_code in {400, 422}:
        return "El código es incorrecto, venció o alcanzó el límite de intentos. Revisa el código o solicita uno nuevo."
    if path == "/auth/forgot-password" and status_code == 503:
        return "La recuperación por correo no está disponible en este momento. Contacta al administrador."
    if status_code == 401:
        if path == "/auth/login":
            return "El correo o la contraseña son incorrectos. Revisa tus datos e intenta de nuevo."
        return "Tu sesión venció o ya no es válida. Cierra sesión e inicia sesión nuevamente."
    return {
        400: "No se pudo procesar la solicitud. Revisa los datos ingresados e intenta de nuevo.",
        403: "No tienes permiso para realizar esta acción. Si eres personal médico, verifica que tu cuenta esté aprobada.",
        404: "No se encontró la información solicitada. Actualiza la página e intenta de nuevo.",
        409: "La información ya existe o fue modificada. Actualiza la página antes de volver a intentarlo.",
        413: "El archivo es demasiado grande. Selecciona un archivo de menor tamaño.",
        422: "Hay datos incompletos o con un formato incorrecto. Revisa los campos e intenta de nuevo.",
        429: "Se han realizado demasiadas solicitudes. Espera un momento antes de volver a intentarlo.",
    }.get(status_code, "El servicio no está disponible en este momento. Intenta de nuevo más tarde.")


def _connection_error_message(error: requests.RequestException) -> str:
    if isinstance(error, requests.Timeout):
        return "La solicitud tardó demasiado. Intenta de nuevo en unos momentos. Si estabas guardando información, revisa si se guardó antes de repetir la acción."
    return "No se pudo conectar con el servicio. Revisa tu conexión e intenta de nuevo en unos momentos."


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
    def _clear_read_cache() -> None:
        st.session_state.pop("_api_read_cache", None)

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
        use_cache: bool = True,
        timeout: Any = REQUEST_TIMEOUT,
    ) -> Any:
        method_upper = method.upper()
        cache = None
        cache_key = None
        cache_ttl = 45
        if method_upper == "GET" and use_cache:
            cache = st.session_state.setdefault("_api_read_cache", {})
            params_key = tuple(sorted((str(key), str(value)) for key, value in (params or {}).items()))
            token = st.session_state.get("auth_token", "")
            token_key = hashlib.sha256(token.encode("utf-8")).hexdigest() if token else ""
            cache_key = (self.base_url, root_path, path, params_key, token_key)
            if path in {"/version", "/model/metrics"}:
                cache_ttl = 300
            elif path.startswith("/alerts"):
                cache_ttl = 15

            cached = cache.get(cache_key)
            if cached and time.monotonic() - cached[0] < cache_ttl:
                return copy.deepcopy(cached[1])

        url = f"{self.root_url if root_path else self.base_url}/{path.lstrip('/')}"
        try:
            response = requests.request(
                method,
                url,
                params=params,
                json=json,
                headers=headers or self._get_headers(),
                timeout=timeout,
            )
        except requests.RequestException as error:
            raise ApiError(_connection_error_message(error)) from error

        if not response.ok:
            raise ApiError(_http_error_message(response.status_code, path))

        if response.status_code == 204 or not response.content:
            result = None
        else:
            try:
                result = response.json()
            except ValueError as error:
                raise ApiError("No se pudo interpretar la respuesta del servicio. Intenta de nuevo más tarde.") from error

        if cache is not None and cache_key is not None:
            cache[cache_key] = (time.monotonic(), copy.deepcopy(result))
            if len(cache) > 128:
                oldest_key = min(cache, key=lambda key: cache[key][0])
                del cache[oldest_key]
        elif method_upper in {"POST", "PATCH", "PUT", "DELETE"}:
            self._clear_read_cache()

        return result

    def check_health(self) -> bool:
        if DEMO_MODE:
            return False
        try:
            health = self._request("GET", "/health", root_path=True, use_cache=False, timeout=(3.0, 5.0))
        except ApiError:
            return False
        return isinstance(health, dict) and health.get("status") == "ok"

    def get_system_health(self) -> Dict[str, Any]:
        if DEMO_MODE:
            return {"status": "demo", "modelo_cargado": True, "db": "demo"}
        return self._request("GET", "/health", root_path=True)

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

        if not isinstance(data, dict) or not data.get("token"):
            return {"success": False, "error": "No se pudo iniciar sesión. Intenta de nuevo más tarde."}
        st.session_state["auth_token"] = data["token"]
        st.session_state["user_role"] = data.get("role")
        st.session_state["user_email"] = data.get("email", email)
        st.session_state["user_uid"] = data.get("uid")
        st.session_state["municipio_id"] = data.get("municipio_id")
        st.session_state.pop("_predictive_drafts_auto_attempted", None)
        st.session_state.pop("_predictive_drafts_generation_error", None)
        return {"success": True, "data": data}

    def request_password_reset(self, email: str) -> Dict[str, Any]:
        return self._password_recovery_request("/auth/forgot-password", {"email": email})

    def reset_password(self, token: str, password: str) -> Dict[str, Any]:
        return self._password_recovery_request("/auth/reset-password", {"token": token, "password": password})

    def verify_recovery_code(self, email: str, code: str) -> Dict[str, Any]:
        if DEMO_MODE:
            return {"success": False, "error": "La recuperación no está disponible en modo demostración."}
        try:
            data = self._request("POST", "/auth/verify-recovery-code", json={"email": email, "code": code}, headers={"Content-Type": "application/json"})
        except ApiError as error:
            return {"success": False, "error": str(error)}
        if not isinstance(data, dict) or not isinstance(data.get("reset_token"), str) or not data["reset_token"]:
            return {"success": False, "error": "No se pudo confirmar la verificación. Intenta de nuevo."}
        return {"success": True, "reset_token": data["reset_token"]}

    def _password_recovery_request(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if DEMO_MODE:
            return {"success": False, "error": "La recuperación de contraseña no está disponible en modo demostración."}
        try:
            data = self._request("POST", path, json=payload, headers={"Content-Type": "application/json"})
        except ApiError as error:
            return {"success": False, "error": str(error)}
        if not isinstance(data, dict) or not isinstance(data.get("message"), str):
            return {"success": False, "error": "No se pudo confirmar la solicitud. Intenta de nuevo más tarde."}
        return {"success": True, "message": data["message"]}

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
        self._clear_read_cache()
        for key in (
            "auth_token",
            "user_role",
            "user_email",
            "user_uid",
            "municipio_id",
            "backend_offline",
            "_predictive_drafts_auto_attempted",
            "_predictive_drafts_generation_error",
        ):
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

    def get_prediction(
        self,
        municipio_id: str,
        semana: Optional[str] = None,
        enfermedad: str = "dengue",
    ) -> Dict[str, Any]:
        enfermedad_api = self._enfermedad_api(enfermedad)
        if DEMO_MODE:
            meta = MUNICIPIOS_JALISCO.get(str(municipio_id), {"nombre": str(municipio_id)})
            return {
                "municipio": str(municipio_id),
                "municipio_nombre": meta["nombre"],
                "semana": semana or "Demostración",
                "enfermedad": enfermedad_api,
                "casos_esperados": 12.0,
                "casos_esperados_redondeados": 12,
                "umbrales": [2.0, 6.0, 15.0],
                "nivel_riesgo": "alto",
                "shap_top3": [],
            }
        params: Dict[str, Any] = {"municipio": municipio_id, "enfermedad": enfermedad_api}
        if semana:
            params["semana"] = semana
        return self._request("GET", "/predictions", params=params)

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
        horizonte: int = 1,
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
            return {"historico": historico[-semanas:], "prediccion": prediccion[:horizonte]}

        return self._request(
            "GET",
            "/predictions/history",
            params={
                "municipio": municipio_id,
                "enfermedad": enfermedad_api,
                "semanas": semanas,
                "horizonte": horizonte,
            },
        )

    def get_region_prediction_history(
        self,
        enfermedad: str = "dengue",
        semanas: int = 4,
        horizonte: int = 4,
    ) -> Dict[str, Any]:
        enfermedad_api = self._enfermedad_api(enfermedad)
        if DEMO_MODE:
            historico_por_semana: Dict[str, int] = {}
            prediccion_por_semana: Dict[str, float] = {}
            for municipio_id in MUNICIPIOS_JALISCO:
                data = self.get_prediction_history(
                    municipio_id,
                    enfermedad=enfermedad_api,
                    semanas=semanas,
                    horizonte=horizonte,
                )
                for point in data["historico"]:
                    historico_por_semana[point["semana"]] = (
                        historico_por_semana.get(point["semana"], 0) + int(point["casos"])
                    )
                for point in data["prediccion"]:
                    prediccion_por_semana[point["semana"]] = (
                        prediccion_por_semana.get(point["semana"], 0.0) + float(point["casos"])
                    )

            return {
                "region": "Centro",
                "enfermedad": enfermedad_api,
                "municipios_incluidos": len(MUNICIPIOS_JALISCO),
                "historico": [
                    {"semana": semana, "casos": casos}
                    for semana, casos in sorted(historico_por_semana.items())[-semanas:]
                ],
                "prediccion": [
                    {"semana": semana, "casos": round(casos, 2)}
                    for semana, casos in sorted(prediccion_por_semana.items())[:horizonte]
                ],
            }

        return self._request(
            "GET",
            "/predictions/history/region",
            params={
                "enfermedad": enfermedad_api,
                "semanas": semanas,
                "horizonte": horizonte,
            },
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

    def generate_predicted_alert_drafts(self) -> Dict[str, Any]:
        if DEMO_MODE:
            return {
                "success": False,
                "error": "La generación de borradores requiere el backend conectado.",
            }
        try:
            data = self._request("POST", "/alerts/predictive-drafts/generate")
            return {"success": True, "data": data}
        except ApiError as error:
            return {"success": False, "error": str(error)}

    def get_predicted_alert_drafts(self, municipio_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if DEMO_MODE:
            raise ApiError("Los borradores predictivos no están disponibles en modo de demostración.")
        params = {"estado": "pendiente"}
        if municipio_id:
            params["municipio"] = municipio_id
        return self._request("GET", "/alerts/predictive-drafts", params=params)

    def review_predicted_alert_draft(
        self,
        draft_id: int,
        decision: str,
        *,
        nivel: Optional[str] = None,
        mensaje: Optional[str] = None,
    ) -> Dict[str, Any]:
        if DEMO_MODE:
            return {"success": False, "error": "El modo demostración no guarda ni publica alertas."}
        payload: Dict[str, Any] = {"decision": decision}
        if nivel is not None:
            payload["nivel"] = nivel
        if mensaje is not None:
            payload["mensaje"] = mensaje
        try:
            data = self._request(
                "PATCH",
                f"/alerts/predictive-drafts/{draft_id}",
                json=payload,
            )
            return {"success": True, "data": data}
        except ApiError as error:
            return {"success": False, "error": str(error)}

    def create_alert(self, municipio_id: Optional[str], nivel: str, mensaje: str) -> Dict[str, Any]:
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

    def toggle_alert(self, alert_id: Any, activa: bool) -> Dict[str, Any]:
        if DEMO_MODE:
            return {"success": False, "error": "Modo de demostración: no se modificaron alertas."}
        try:
            data = self._request("PATCH", f"/alerts/{alert_id}", json={"activa": activa})
            return {"success": True, "data": data}
        except ApiError as error:
            return {"success": False, "error": str(error)}

    def delete_alert(self, alert_id: Any) -> Dict[str, Any]:
        if DEMO_MODE:
            return {"success": False, "error": "Modo de demostración: no se eliminaron alertas."}
        try:
            data = self._request("DELETE", f"/alerts/{alert_id}")
            return {"success": True, "data": data}
        except ApiError as error:
            return {"success": False, "error": str(error)}

    def get_users(
        self,
        *,
        role: Optional[str] = None,
        verificado: Optional[bool] = None,
        search: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if DEMO_MODE:
            return [
                {
                    "uid": "usr_funcionario_001",
                    "email": "admin@proevira.jalisco.gob.mx",
                    "role": "funcionario",
                    "municipio_id": "14039",
                    "institucion": "Secretaría de Salud Jalisco",
                    "cedula": None,
                    "verificado": True,
                    "created_at": "2026-11-01T10:00:00",
                },
                {
                    "uid": "usr_medico_pendiente",
                    "email": "medico.pendiente@salud.jalisco.gob.mx",
                    "role": "medico",
                    "municipio_id": "14120",
                    "institucion": "Centro de Salud Zapopan Norte",
                    "cedula": "MED-87654321",
                    "verificado": False,
                    "created_at": "2026-11-10T09:30:00",
                },
            ]
        params: Dict[str, Any] = {}
        if role:
            params["role"] = role
        if verificado is not None:
            params["verificado"] = verificado
        if search:
            params["search"] = search
        return self._request("GET", "/auth/users", params=params)

    def verify_medico(self, uid: str) -> Dict[str, Any]:
        if DEMO_MODE:
            return {"success": False, "error": "Modo de demostración: no se verificó el médico."}
        try:
            data = self._request("POST", f"/auth/verify-medico/{uid}")
            return {"success": True, "data": data}
        except ApiError as error:
            return {"success": False, "error": str(error)}

    def create_user(
        self,
        *,
        email: str,
        password: str,
        role: str,
        municipio_id: Optional[str] = None,
        institucion: Optional[str] = None,
        cedula: Optional[str] = None,
        verificado: bool = True,
    ) -> Dict[str, Any]:
        if DEMO_MODE:
            return {"success": False, "error": "Modo de demostración: no se crean usuarios."}
        payload: Dict[str, Any] = {
            "email": email,
            "password": password,
            "role": role,
            "verificado": verificado,
        }
        if municipio_id:
            payload["municipio_id"] = municipio_id
        if institucion:
            payload["institucion"] = institucion
        if cedula:
            payload["cedula"] = cedula
        try:
            data = self._request("POST", "/auth/users", json=payload)
            return {"success": True, "data": data}
        except ApiError as error:
            return {"success": False, "error": str(error)}

    def update_user(
        self,
        uid: str,
        *,
        role: Optional[str] = None,
        municipio_id: Optional[str] = None,
        clear_municipio: bool = False,
        institucion: Optional[str] = None,
        cedula: Optional[str] = None,
        verificado: Optional[bool] = None,
    ) -> Dict[str, Any]:
        if DEMO_MODE:
            return {"success": False, "error": "Modo de demostración: no se modificaron usuarios."}
        payload: Dict[str, Any] = {"clear_municipio": clear_municipio}
        if role is not None:
            payload["role"] = role
        if not clear_municipio and municipio_id is not None:
            payload["municipio_id"] = municipio_id
        if institucion is not None:
            payload["institucion"] = institucion
        if cedula is not None:
            payload["cedula"] = cedula
        if verificado is not None:
            payload["verificado"] = verificado
        try:
            data = self._request("PATCH", f"/auth/users/{uid}", json=payload)
            return {"success": True, "data": data}
        except ApiError as error:
            return {"success": False, "error": str(error)}

    def delete_user(self, uid: str) -> Dict[str, Any]:
        if DEMO_MODE:
            return {"success": False, "error": "Modo de demostración: no se eliminaron usuarios."}
        try:
            data = self._request("DELETE", f"/auth/users/{uid}")
            return {"success": True, "data": data}
        except ApiError as error:
            return {"success": False, "error": str(error)}

    def get_symptoms_summary(self) -> Dict[str, Any]:
        if DEMO_MODE:
            return {
                "total_reportes": 0,
                "ultimos_7_dias": 0,
                "por_sospecha": {"dengue": 0, "influenza": 0, "covid": 0, "indeterminado": 0},
                "por_municipio": [],
                "recientes": [],
            }
        return self._request("GET", "/symptoms/summary")

    def get_datasets(self) -> Dict[str, Any]:
        if DEMO_MODE:
            return {"datasets": [], "imports": []}
        return self._request("GET", "/datasets")

    def import_csv(
        self,
        enfermedad: str,
        fuente: str,
        filename: str,
        file_bytes: bytes,
    ) -> Dict[str, Any]:
        if DEMO_MODE:
            return {"success": False, "error": "Modo de demostración: la importación de CSV no está disponible."}
        url = f"{self.base_url}/datasets/import"
        headers: Dict[str, str] = {}
        token = st.session_state.get("auth_token")
        if token:
            headers["Authorization"] = f"Bearer {token}"

        try:
            response = requests.post(
                url,
                data={"enfermedad": self._enfermedad_api(enfermedad), "fuente": fuente},
                files={"file": (filename, file_bytes, "text/csv")},
                headers=headers,
                timeout=max(REQUEST_TIMEOUT, 60.0),
            )
        except requests.RequestException as error:
            return {"success": False, "error": _connection_error_message(error)}

        if not response.ok:
            return {"success": False, "error": _http_error_message(response.status_code, "/datasets/import")}

        self._clear_read_cache()
        try:
            return {"success": True, "data": response.json()}
        except ValueError:
            return {"success": False, "error": "No se pudo confirmar la importación. Revisa los datos cargados antes de volver a intentarlo."}


api = ApiClient()
