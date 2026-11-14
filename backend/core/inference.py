import json
import os
import joblib
import numpy as np
import pandas as pd
import shap
from typing import Dict, Any, List, Optional, Tuple

from backend.config import settings


def _iso_to_monday(semana_str: str) -> pd.Timestamp:
    """Convierte 'YYYY-WXX' al lunes ISO correspondiente."""
    parts = semana_str.strip().upper().split("-W")
    if len(parts) != 2:
        raise ValueError(f"Formato de semana ISO inválido: {semana_str}. Esperado YYYY-WXX")
    year, week = int(parts[0]), int(parts[1])
    return pd.Timestamp.fromisocalendar(year, week, 1)


def _monday_to_iso(ts: pd.Timestamp) -> Tuple[str, int]:
    """Devuelve ('YYYY-WXX', iso_week) para un Timestamp."""
    iso = ts.isocalendar()
    return f"{iso.year}-W{iso.week:02d}", int(iso.week)


class InferenceEngine:
    def __init__(self):
        self.loaded = False
        self.modelos: Dict[str, Any] = {}
        self.explainers: Dict[str, Any] = {}
        self.thresholds_municipio: Dict[str, List[float]] = {}
        self.features: List[str] = []
        self.mun_cod_map: Dict[str, int] = {}
        self.labels: List[str] = ["bajo", "medio", "alto", "crítico"]
        self.edades: List[str] = ["edad_0_14", "edad_15_44", "edad_45_64", "edad_65_mas"]
        self.ultima_semana_por_enfermedad: Dict[str, str] = {}
        self.ultima_semana_iso_por_enfermedad: Dict[str, str] = {}
        self.raw_data: Optional[pd.DataFrame] = None
        self.municipios_info: Dict[str, Dict[str, Any]] = {}

    def load(self, force: bool = False):
        """Carga modelos municipales entrenados, CSV histórico unificado y GeoJSON."""
        if self.loaded and not force:
            return

        model_path = os.path.join(settings.MODEL_ARTIFACTS_DIR, "modelo_rf.pkl")
        csv_path = os.path.join(settings.CLEAN_DATA_DIR, "casos_municipio_semana.csv")
        geojson_path = os.path.join(settings.CLEAN_DATA_DIR, "municipios.geojson")

        if os.path.exists(model_path):
            art = joblib.load(model_path)
            self.modelos = art.get("modelos", {})
            self.thresholds_municipio = art.get("thresholds_municipio", {})
            self.features = art.get("features", [])
            self.mun_cod_map = art.get("mun_cod_map", {})
            self.labels = art.get("labels", self.labels)
            self.edades = art.get("edades", self.edades)
            self.ultima_semana_por_enfermedad = art.get("ultima_semana_por_enfermedad", {})
            self.ultima_semana_iso_por_enfermedad = art.get("ultima_semana_iso_por_enfermedad", {})
        else:
            print(f"[WARNING] No se encontró el modelo en {model_path}")

        if os.path.exists(csv_path):
            df = pd.read_csv(
                csv_path,
                dtype={"municipio_id": str},
                parse_dates=["fecha_inicio_semana"],
            )
            df["municipio_id"] = df["municipio_id"].astype(str).str.zfill(5)
            df["enfermedad"] = df["enfermedad"].astype(str).str.lower()
            self.raw_data = df.sort_values(
                ["enfermedad", "municipio_id", "fecha_inicio_semana"]
            ).reset_index(drop=True)
        else:
            print(f"[WARNING] No se encontró la data histórica en {csv_path}")

        if os.path.exists(geojson_path):
            with open(geojson_path, "r", encoding="utf-8") as f:
                geo = json.load(f)
                for feat in geo.get("features", []):
                    props = feat.get("properties", {})
                    mid = str(props.get("municipio_id")).zfill(5)
                    coords = feat.get("geometry", {}).get("coordinates", [0, 0])
                    self.municipios_info[mid] = {
                        "nombre": props.get("nombre", mid),
                        "lon": float(coords[0]),
                        "lat": float(coords[1]),
                    }

        self.loaded = True

    def reload(self):
        """Recarga modelos y series históricas desde disco tras actualizar datasets."""
        self.explainers.clear()
        self.load(force=True)

    def _normalize_enfermedad(self, enfermedad: str) -> str:
        enf = (enfermedad or "dengue").strip().lower()
        return "covid" if enf in ("covid-19", "covid19") else enf

    def _get_explainer(self, enf: str):
        if enf not in self.explainers and enf in self.modelos:
            self.explainers[enf] = shap.TreeExplainer(self.modelos[enf])
        return self.explainers.get(enf)

    def _classify_risk(self, municipio_id: str, enf: str, pred_cases: float) -> Tuple[int, str, List[float]]:
        th = self.thresholds_municipio.get(f"{municipio_id}|{enf}", [0.0, 1.0, 2.0])
        casos_redondeados = int(np.round(max(0.0, pred_cases)))
        idx = int(np.searchsorted(th, casos_redondeados, side="left"))
        idx = max(0, min(idx, len(self.labels) - 1))
        return casos_redondeados, self.labels[idx], [float(x) for x in th]

    def _build_feature_vector(self, series_df: pd.DataFrame, municipio_id: str, sem_iso: int) -> pd.DataFrame:
        """Calcula el vector exacto de features municipales usando las últimas 8 semanas."""
        tail8 = series_df.tail(8)
        casos_arr = tail8["casos"].astype(float).values
        if len(casos_arr) < 8:
            casos_arr = np.pad(casos_arr, (8 - len(casos_arr), 0), mode="edge")

        def_arr = tail8["defunciones"].astype(float).values
        if len(def_arr) < 4:
            def_arr = np.pad(def_arr, (4 - len(def_arr), 0), mode="constant")

        lags = [float(casos_arr[-1 - k]) for k in range(8)]
        log_lags = [float(np.log1p(v)) for v in lags]
        media_4s = float(np.mean(casos_arr[-4:]))
        media_8s = float(np.mean(casos_arr[-8:]))
        max_8s = float(np.max(casos_arr[-8:]))
        std_8s = float(np.std(casos_arr[-8:], ddof=0))
        tendencia = float(log_lags[0] - log_lags[4])
        tendencia_rel = float((media_4s - media_8s) / (media_8s + 1.0))
        def_4s = float(np.sum(def_arr[-4:]))

        tail4 = series_df.tail(4)
        tot4 = float(tail4["casos"].sum())
        tasas = {}
        for edad_col in self.edades:
            if tot4 > 0 and edad_col in tail4.columns:
                tasas[f"tasa_{edad_col}"] = float(tail4[edad_col].sum() / tot4)
            else:
                tasas[f"tasa_{edad_col}"] = 0.0

        row_dict = {
            **{f"lag{k}": lags[k] for k in range(8)},
            **{f"log_lag{k}": log_lags[k] for k in range(8)},
            "media_4s": media_4s,
            "media_8s": media_8s,
            "max_8s": max_8s,
            "std_8s": std_8s,
            "tendencia": tendencia,
            "tendencia_rel": tendencia_rel,
            "def_4s": def_4s,
            **tasas,
            "sem_sin": float(np.sin(2.0 * np.pi * sem_iso / 52.0)),
            "sem_cos": float(np.cos(2.0 * np.pi * sem_iso / 52.0)),
            "mun_cod": float(self.mun_cod_map.get(municipio_id, 0)),
        }
        return pd.DataFrame([[row_dict[f] for f in self.features]], columns=self.features)

    def _predict_step(self, enf: str, x_vec: pd.DataFrame) -> float:
        model = self.modelos[enf]
        pred_log = float(model.predict(x_vec)[0])
        return float(max(0.0, np.expm1(pred_log)))

    def _compute_shap_items(self, enf: str, x_vec: pd.DataFrame) -> Tuple[float, List[Dict[str, Any]]]:
        explainer = self._get_explainer(enf)
        if explainer is None:
            return 0.0, []
        sv = np.asarray(explainer.shap_values(x_vec)).reshape(-1)
        expected = explainer.expected_value
        base_val = float(np.asarray(expected).reshape(-1)[0])
        items = [
            {"feature": feat, "shap": round(float(val), 4)}
            for feat, val in zip(self.features, sv)
        ]
        items.sort(key=lambda d: abs(d["shap"]), reverse=True)
        return base_val, items

    def _forecast_to_target(
        self, sub_df: pd.DataFrame, municipio_id: str, enf: str, target_monday: Optional[pd.Timestamp]
    ) -> Tuple[float, str, pd.DataFrame]:
        """Predice 1 paso o recursivamente hasta `target_monday` para `(municipio_id, enf)`."""
        max_date = pd.Timestamp(sub_df["fecha_inicio_semana"].max())
        if target_monday is None:
            ref_date = max_date
            target_monday = max_date + pd.Timedelta(days=7)
        else:
            ref_date = target_monday - pd.Timedelta(days=7)

        if ref_date <= max_date:
            hist_cut = sub_df[sub_df["fecha_inicio_semana"] <= ref_date]
            if len(hist_cut) == 0:
                hist_cut = sub_df.head(8)
            _, sem_iso = _monday_to_iso(pd.Timestamp(hist_cut["fecha_inicio_semana"].iloc[-1]))
            x_vec = self._build_feature_vector(hist_cut, municipio_id, sem_iso)
            pred_val = self._predict_step(enf, x_vec)
            semana_iso, _ = _monday_to_iso(target_monday)
            return pred_val, semana_iso, x_vec

        # Proyección recursiva cuando se solicita una semana futura más allá de max_date + 7 días
        sim = sub_df.copy()
        steps = int((target_monday - max_date).days // 7)
        steps = max(1, min(steps, 12))
        last_pred = 0.0
        last_x = None
        curr_date = max_date
        for _ in range(steps):
            _, sem_iso = _monday_to_iso(curr_date)
            last_x = self._build_feature_vector(sim, municipio_id, sem_iso)
            last_pred = self._predict_step(enf, last_x)

            next_date = curr_date + pd.Timedelta(days=7)
            next_iso, next_sem = _monday_to_iso(next_date)

            tot4 = float(sim.tail(4)["casos"].sum())
            new_row = {
                "municipio_id": municipio_id,
                "enfermedad": enf,
                "fecha_inicio_semana": next_date,
                "sem": next_sem,
                "semana": next_iso,
                "casos": last_pred,
                "defunciones": 0.0,
            }
            for edad_col in self.edades:
                share = float(sim.tail(4)[edad_col].sum() / tot4) if tot4 > 0 else 0.25
                new_row[edad_col] = last_pred * share

            sim = pd.concat([sim, pd.DataFrame([new_row])], ignore_index=True)
            curr_date = next_date

        semana_iso, _ = _monday_to_iso(curr_date)
        return last_pred, semana_iso, last_x

    def predict_municipio(
        self,
        municipio_id: str,
        semana: Optional[str] = None,
        enfermedad: str = "dengue",
    ) -> Dict[str, Any]:
        """Predicción municipal directa t+1 con riesgo y SHAP top-3."""
        if not self.loaded:
            self.load()

        municipio_id = str(municipio_id).zfill(5)
        enf = self._normalize_enfermedad(enfermedad)

        if not self.modelos or enf not in self.modelos or self.raw_data is None:
            raise ValueError(f"Modelo o datos no disponibles para la enfermedad '{enf}'.")

        sub = self.raw_data[
            (self.raw_data["municipio_id"] == municipio_id)
            & (self.raw_data["enfermedad"] == enf)
        ].sort_values("fecha_inicio_semana")

        if sub.empty:
            raise ValueError(f"No hay serie histórica para el municipio '{municipio_id}' y enfermedad '{enf}'.")

        target_monday = _iso_to_monday(semana) if semana else None
        pred_val, semana_pred, x_vec = self._forecast_to_target(sub, municipio_id, enf, target_monday)
        casos_red, nivel_riesgo, th = self._classify_risk(municipio_id, enf, pred_val)

        _, shap_all = self._compute_shap_items(enf, x_vec)
        shap_top3 = [
            {"feature": item["feature"], "valor": item["shap"]}
            for item in shap_all[:3]
        ]

        info = self.municipios_info.get(municipio_id, {"nombre": municipio_id})
        return {
            "municipio": municipio_id,
            "municipio_nombre": info.get("nombre", municipio_id),
            "semana": semana_pred,
            "enfermedad": enf,
            "casos_esperados": round(float(pred_val), 2),
            "casos_esperados_redondeados": casos_red,
            "umbrales": th,
            "prediccion_regional": None,
            "participacion_pct": None,
            "nivel_riesgo": nivel_riesgo,
            "shap_top3": shap_top3,
        }

    def explain_municipio(
        self,
        municipio_id: str,
        semana: Optional[str] = None,
        enfermedad: str = "dengue",
    ) -> Dict[str, Any]:
        """Explicabilidad SHAP local completa para un municipio, semana y enfermedad."""
        if not self.loaded:
            self.load()

        municipio_id = str(municipio_id).zfill(5)
        enf = self._normalize_enfermedad(enfermedad)
        sub = self.raw_data[
            (self.raw_data["municipio_id"] == municipio_id)
            & (self.raw_data["enfermedad"] == enf)
        ].sort_values("fecha_inicio_semana")

        if sub.empty:
            raise ValueError(f"No hay serie histórica para '{municipio_id}' y '{enf}'.")

        target_monday = _iso_to_monday(semana) if semana else None
        pred_val, semana_pred, x_vec = self._forecast_to_target(sub, municipio_id, enf, target_monday)
        _, nivel_riesgo, _ = self._classify_risk(municipio_id, enf, pred_val)
        base_val, shap_all = self._compute_shap_items(enf, x_vec)

        return {
            "municipio": municipio_id,
            "semana": semana_pred,
            "enfermedad": enf,
            "casos_esperados": round(float(pred_val), 2),
            "nivel_riesgo": nivel_riesgo,
            "base_value": round(float(base_val), 4),
            "feature_importance": shap_all[:10],
        }

    def predict_bulk(self, semana: Optional[str] = None, enfermedad: str = "dengue") -> List[Dict[str, Any]]:
        """Predicciones municipales para los 12 municipios de la Región Centro."""
        if not self.loaded:
            self.load()

        results = []
        for mid, info in self.municipios_info.items():
            try:
                pred = self.predict_municipio(mid, semana=semana, enfermedad=enfermedad)
                results.append(
                    {
                        "municipio": mid,
                        "nombre": info["nombre"],
                        "lat": info["lat"],
                        "lon": info["lon"],
                        "semana": pred["semana"],
                        "enfermedad": pred["enfermedad"],
                        "casos_esperados": pred["casos_esperados"],
                        "casos_esperados_redondeados": pred["casos_esperados_redondeados"],
                        "nivel_riesgo": pred["nivel_riesgo"],
                    }
                )
            except Exception:
                continue
        return results

    def get_history(
        self,
        municipio_id: str,
        enfermedad: str = "dengue",
        semanas: int = 12,
        horizonte: int = 4,
    ) -> Dict[str, Any]:
        """Serie histórica observada y proyección recursiva de 1..4 semanas por municipio."""
        if not self.loaded:
            self.load()

        municipio_id = str(municipio_id).zfill(5)
        enf = self._normalize_enfermedad(enfermedad)

        if self.raw_data is None:
            return {"municipio": municipio_id, "enfermedad": enf, "historico": [], "prediccion": []}

        sub = self.raw_data[
            (self.raw_data["municipio_id"] == municipio_id)
            & (self.raw_data["enfermedad"] == enf)
        ].sort_values("fecha_inicio_semana")

        if sub.empty:
            return {"municipio": municipio_id, "enfermedad": enf, "historico": [], "prediccion": []}

        tail_hist = sub.tail(semanas)
        historico = [
            {"semana": str(row["semana"]), "casos": int(row["casos"])}
            for _, row in tail_hist.iterrows()
        ]

        horizonte = max(1, min(int(horizonte), 8))
        sim = sub.copy()
        curr_date = pd.Timestamp(sim["fecha_inicio_semana"].max())
        prediccion = []

        for _ in range(horizonte):
            _, sem_iso = _monday_to_iso(curr_date)
            x_vec = self._build_feature_vector(sim, municipio_id, sem_iso)
            pred_val = self._predict_step(enf, x_vec)
            _, nivel, _ = self._classify_risk(municipio_id, enf, pred_val)

            next_date = curr_date + pd.Timedelta(days=7)
            next_iso, next_sem = _monday_to_iso(next_date)
            prediccion.append(
                {
                    "semana": next_iso,
                    "casos": round(float(pred_val), 2),
                    "nivel": nivel,
                }
            )

            tot4 = float(sim.tail(4)["casos"].sum())
            new_row = {
                "municipio_id": municipio_id,
                "enfermedad": enf,
                "fecha_inicio_semana": next_date,
                "sem": next_sem,
                "semana": next_iso,
                "casos": pred_val,
                "defunciones": 0.0,
            }
            for edad_col in self.edades:
                share = float(sim.tail(4)[edad_col].sum() / tot4) if tot4 > 0 else 0.25
                new_row[edad_col] = pred_val * share

            sim = pd.concat([sim, pd.DataFrame([new_row])], ignore_index=True)
            curr_date = next_date

        return {
            "municipio": municipio_id,
            "enfermedad": enf,
            "historico": historico,
            "prediccion": prediccion,
        }

    def get_region_history(
        self,
        enfermedad: str = "dengue",
        semanas: int = 12,
        horizonte: int = 4,
    ) -> Dict[str, Any]:
        """Agrega el histórico y las proyecciones municipales de la Región Centro."""
        if not self.loaded:
            self.load()

        enf = self._normalize_enfermedad(enfermedad)
        if self.raw_data is None:
            return {
                "region": "Centro",
                "enfermedad": enf,
                "municipios_incluidos": 0,
                "historico": [],
                "prediccion": [],
            }

        region_data = self.raw_data[self.raw_data["enfermedad"] == enf]
        if region_data.empty:
            return {
                "region": "Centro",
                "enfermedad": enf,
                "municipios_incluidos": 0,
                "historico": [],
                "prediccion": [],
            }

        history_rows = (
            region_data.groupby(["semana", "fecha_inicio_semana"], as_index=False)["casos"]
            .sum()
            .sort_values("fecha_inicio_semana")
            .tail(semanas)
        )
        historico = [
            {"semana": str(row["semana"]), "casos": int(round(float(row["casos"])))}
            for _, row in history_rows.iterrows()
        ]

        municipios = sorted(region_data["municipio_id"].astype(str).unique())
        forecast_totals: Dict[str, float] = {}
        municipios_con_datos = 0
        for municipio_id in municipios:
            history = self.get_history(
                municipio_id,
                enfermedad=enf,
                semanas=semanas,
                horizonte=horizonte,
            )
            if not history["historico"]:
                continue
            municipios_con_datos += 1
            for point in history["prediccion"]:
                semana = point["semana"]
                forecast_totals[semana] = forecast_totals.get(semana, 0.0) + float(point["casos"])

        prediccion = [
            {"semana": semana, "casos": round(casos, 2)}
            for semana, casos in sorted(forecast_totals.items(), key=lambda item: _iso_to_monday(item[0]))
        ]
        return {
            "region": "Centro",
            "enfermedad": enf,
            "municipios_incluidos": municipios_con_datos,
            "historico": historico,
            "prediccion": prediccion,
        }


inference_engine = InferenceEngine()
