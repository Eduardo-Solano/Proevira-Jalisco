import os
import json
import numpy as np
import pandas as pd
import joblib
import shap
from typing import Dict, Any, List, Optional
from backend.config import settings

ENF_MAP = {"dengue": 0, "influenza": 1, "covid": 2}
EDADES = ["edad_0_14", "edad_15_44", "edad_45_64", "edad_65_mas"]
LABELS = ["bajo", "medio", "alto", "crítico"]


class InferenceEngine:
    def __init__(self):
        self.model_path = os.path.join(settings.MODEL_ARTIFACTS_DIR, "modelo_rf.pkl")
        self.data_path = os.path.join(settings.CLEAN_DATA_DIR, "casos_municipio_semana.parquet")
        self.geojson_path = os.path.join(settings.CLEAN_DATA_DIR, "municipios.geojson")

        self.loaded = False
        self.reg_region = None
        self.thresholds_region = {}
        self.thresholds_municipio = {}
        self.participacion_municipal = {}
        self.features_region = []
        self.labels = LABELS
        self.explainer = None
        self.raw_data = None
        self.municipios_coords = {}

        self.load()

    def load(self):
        if not os.path.exists(self.model_path) or not os.path.exists(self.data_path):
            return

        artifact = joblib.load(self.model_path)
        self.reg_region = artifact["reg_region"]
        self.thresholds_region = artifact["thresholds_region"]
        self.thresholds_municipio = artifact["thresholds_municipio"]
        self.participacion_municipal = artifact["participacion_municipal"]
        self.features_region = artifact["features_region"]
        self.labels = artifact.get("labels", LABELS)
        self.explainer = shap.TreeExplainer(self.reg_region)

        # Cargar datos históricos para features
        self.raw_data = pd.read_parquet(self.data_path)

        # Cargar coordenadas de municipios desde GeoJSON
        if os.path.exists(self.geojson_path):
            with open(self.geojson_path, "r", encoding="utf-8") as f:
                geo = json.load(f)
                for feat in geo.get("features", []):
                    props = feat.get("properties", {})
                    mid = str(props.get("municipio_id"))
                    coords = feat.get("geometry", {}).get("coordinates", [0, 0])
                    self.municipios_coords[mid] = {
                        "nombre": props.get("nombre", ""),
                        "lon": coords[0],
                        "lat": coords[1]
                    }

        self.loaded = True

    def _get_region_features(self, enfermedad: str, target_date: Optional[pd.Timestamp] = None):
        """
        Construye el vector de características regionales para la enfermedad dada
        hasta la fecha de referencia t.
        """
        cols = ["casos", "defunciones"] + EDADES
        enf_data = self.raw_data[self.raw_data["enfermedad"] == enfermedad]
        r = enf_data.groupby(["enfermedad", "fecha_inicio_semana", "sem"], as_index=False)[cols].sum()
        r = r.sort_values("fecha_inicio_semana").reset_index(drop=True)

        if target_date is not None:
            r = r[r["fecha_inicio_semana"] <= target_date].reset_index(drop=True)

        if len(r) == 0:
            raise ValueError(f"No hay datos para la enfermedad {enfermedad}")

        # Calcular variables
        r["rlog"] = np.log1p(r["casos"])
        for k in range(8):
            r[f"rlog_lag{k}"] = r["rlog"].shift(k)

        r["rmedia_4s"] = r["casos"].rolling(4).mean()
        r["rmedia_8s"] = r["casos"].rolling(8).mean()
        r["rmax_8s"] = r["casos"].rolling(8).max()
        r["rtend"] = r["rlog_lag0"] - r["rlog_lag4"]
        r["rtend_rel"] = (r["rmedia_4s"] - r["rmedia_8s"]) / (r["rmedia_8s"] + 1)
        r["rdef_4s"] = r["defunciones"].rolling(4).sum()

        tot4 = r["casos"].rolling(4).sum()
        for e in EDADES:
            r[f"rtasa_{e}"] = (r[e].rolling(4).sum() / tot4.replace(0, np.nan)).fillna(0)

        last_row = r.iloc[-1:].copy()
        sem = int(last_row["sem"].values[0])
        last_row["sem_sin"] = np.sin(2 * np.pi * sem / 52)
        last_row["sem_cos"] = np.cos(2 * np.pi * sem / 52)
        last_row["enfermedad_cod"] = ENF_MAP.get(enfermedad, 0)

        last_row = last_row.fillna(0)
        ref_date = pd.Timestamp(last_row["fecha_inicio_semana"].values[0])
        return last_row[self.features_region], ref_date

    def predict_municipio(self, municipio_id: str, semana: Optional[str] = None, enfermedad: str = "dengue") -> Dict[str, Any]:
        """
        Calcula la predicción semanal de casos y nivel de riesgo para un municipio.
        """
        if not self.loaded:
            self.load()
            if not self.loaded:
                raise RuntimeError("El modelo predictivo no está disponible")

        municipio_id = str(municipio_id)
        if len(municipio_id) == 3:
            municipio_id = f"14{municipio_id}"

        # Obtener features de la región
        X_reg, ref_date = self._get_region_features(enfermedad)

        # Inferencia regional en log1p
        log_pred = float(self.reg_region.predict(X_reg)[0])
        pred_region = max(0.0, float(np.expm1(log_pred)))

        # Reparto municipal
        shares = self.participacion_municipal.get(enfermedad, {})
        share = shares.get(municipio_id, 1.0 / 12.0)
        casos_esperados = round(pred_region * share, 2)

        # Determinar nivel de riesgo con cuantiles del municipio
        th_key = f"{municipio_id}|{enfermedad}"
        th = self.thresholds_municipio.get(th_key)
        if not th:
            th = self.thresholds_region.get(enfermedad, [1.0, 5.0, 15.0])

        idx = int(np.searchsorted(th, casos_esperados, side="left"))
        idx = min(idx, len(self.labels) - 1)
        nivel_riesgo = self.labels[idx]

        # Calcular SHAP local
        shap_top3 = []
        try:
            shap_vals = self.explainer.shap_values(X_reg)
            if isinstance(shap_vals, list):
                shap_vals = shap_vals[0]
            vals = shap_vals[0] if shap_vals.ndim > 1 else shap_vals
            pairs = sorted(zip(self.features_region, vals), key=lambda x: abs(x[1]), reverse=True)[:3]
            shap_top3 = [{"feature": f, "valor": round(float(v), 4)} for f, v in pairs]
        except Exception:
            shap_top3 = []

        if not semana:
            next_date = ref_date + pd.Timedelta(days=7)
            iso = next_date.isocalendar()
            semana = f"{iso.year}-W{str(iso.week).zfill(2)}"

        muni_info = self.municipios_coords.get(municipio_id, {})
        nombre = muni_info.get("nombre", f"Municipio {municipio_id}")

        return {
            "municipio": municipio_id,
            "municipio_nombre": nombre,
            "semana": semana,
            "enfermedad": enfermedad,
            "casos_esperados": casos_esperados,
            "prediccion_regional": round(pred_region, 2),
            "participacion_pct": round(share * 100, 2),
            "nivel_riesgo": nivel_riesgo,
            "shap_top3": shap_top3
        }

    def predict_bulk(self, semana: Optional[str] = None, enfermedad: str = "dengue") -> List[Dict[str, Any]]:
        """
        Genera predicciones en lote para todos los 12 municipios de la región.
        """
        if not self.loaded:
            self.load()
            if not self.loaded:
                raise RuntimeError("El modelo predictivo no está disponible")

        X_reg, ref_date = self._get_region_features(enfermedad)
        log_pred = float(self.reg_region.predict(X_reg)[0])
        pred_region = max(0.0, float(np.expm1(log_pred)))

        semana_prediccion = semana
        if not semana_prediccion:
            next_date = ref_date + pd.Timedelta(days=7)
            iso = next_date.isocalendar()
            semana_prediccion = f"{iso.year}-W{iso.week:02d}"

        shares = self.participacion_municipal.get(enfermedad, {})
        thresholds_region = self.thresholds_region.get(enfermedad, [1.0, 5.0, 15.0])
        results = []
        for mid, info in self.municipios_coords.items():
            casos_esperados = round(pred_region * shares.get(mid, 1.0 / 12.0), 2)
            thresholds = self.thresholds_municipio.get(f"{mid}|{enfermedad}") or thresholds_region
            risk_index = min(
                int(np.searchsorted(thresholds, casos_esperados, side="left")),
                len(self.labels) - 1,
            )
            results.append({
                "municipio": mid,
                "nombre": info.get("nombre", ""),
                "lat": info.get("lat", 0.0),
                "lon": info.get("lon", 0.0),
                "semana": semana_prediccion,
                "enfermedad": enfermedad,
                "casos_esperados": casos_esperados,
                "nivel_riesgo": self.labels[risk_index],
            })

        results.sort(key=lambda x: x["casos_esperados"], reverse=True)
        return results

    def get_history(
        self,
        municipio_id: str,
        enfermedad: str = "dengue",
        semanas: int = 12,
        horizonte: int = 1,
    ) -> Dict[str, Any]:
        """
        Devuelve el histórico reciente y hasta cuatro semanas de proyección recursiva.
        """
        if not self.loaded:
            self.load()
            if not self.loaded:
                raise RuntimeError("El modelo predictivo no está disponible")

        municipio_id = str(municipio_id)
        if len(municipio_id) == 3:
            municipio_id = f"14{municipio_id}"

        df = self.raw_data[
            (self.raw_data["municipio_id"] == municipio_id) &
            (self.raw_data["enfermedad"] == enfermedad)
        ].sort_values("fecha_inicio_semana")

        if df.empty:
            return {
                "municipio": municipio_id,
                "enfermedad": enfermedad,
                "historico": [],
                "prediccion": [],
            }

        ultimas = df.tail(semanas)
        historico = [
            {"semana": row["semana"], "casos": int(row["casos"])}
            for _, row in ultimas.iterrows()
        ]

        features, ref_date = self._get_region_features(enfermedad)
        region = (
            self.raw_data[self.raw_data["enfermedad"] == enfermedad]
            .groupby(["fecha_inicio_semana", "sem"], as_index=False)["casos"]
            .sum()
            .sort_values("fecha_inicio_semana")
        )
        recent_cases = region["casos"].astype(float).tolist()
        shares = self.participacion_municipal.get(enfermedad, {})
        share = shares.get(municipio_id, 1.0 / 12.0)
        thresholds = self.thresholds_municipio.get(f"{municipio_id}|{enfermedad}")
        if not thresholds:
            thresholds = self.thresholds_region.get(enfermedad, [1.0, 5.0, 15.0])

        proyeccion = []
        for offset in range(1, horizonte + 1):
            log_pred = float(self.reg_region.predict(features)[0])
            pred_region = max(0.0, float(np.expm1(log_pred)))
            casos_esperados = round(pred_region * share, 2)
            risk_index = min(
                int(np.searchsorted(thresholds, casos_esperados, side="left")),
                len(self.labels) - 1,
            )
            target_date = ref_date + pd.Timedelta(days=7 * offset)
            iso = target_date.isocalendar()
            proyeccion.append({
                "semana": f"{iso.year}-W{iso.week:02d}",
                "casos": casos_esperados,
                "nivel": self.labels[risk_index],
            })

            recent_cases.append(pred_region)
            case_window = recent_cases[-8:]
            log_window = [float(np.log1p(value)) for value in case_window]
            for lag in range(8):
                lag_value = log_window[-1 - lag] if lag < len(log_window) else 0.0
                features.loc[:, f"rlog_lag{lag}"] = lag_value

            mean_4 = float(np.mean(case_window[-4:]))
            mean_8 = float(np.mean(case_window))
            features.loc[:, "rmedia_4s"] = mean_4
            features.loc[:, "rmedia_8s"] = mean_8
            features.loc[:, "rmax_8s"] = float(np.max(case_window))
            features.loc[:, "rtend"] = (
                float(features["rlog_lag0"].iloc[0]) - float(features["rlog_lag4"].iloc[0])
            )
            features.loc[:, "rtend_rel"] = (mean_4 - mean_8) / (mean_8 + 1)
            sem = int(iso.week)
            features.loc[:, "sem_sin"] = np.sin(2 * np.pi * sem / 52)
            features.loc[:, "sem_cos"] = np.cos(2 * np.pi * sem / 52)

        return {
            "municipio": municipio_id,
            "enfermedad": enfermedad,
            "historico": historico,
            "prediccion": proyeccion
        }


inference_engine = InferenceEngine()
