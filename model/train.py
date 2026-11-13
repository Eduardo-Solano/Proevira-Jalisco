"""Entrenamiento reproducible: pronóstico SEMANAL directo por municipio y enfermedad (t+1).

Arquitectura sin reparto regional ni fuga de datos:
  1. Un RandomForestRegressor dedicado por enfermedad (dengue, influenza, covid)
     sobre log1p(casos_municipio) de la semana t+1.
  2. Features construidas exclusivamente hasta la semana t dentro de cada serie
     (municipio_id, enfermedad) y en el rango real de fechas de esa patología.
  3. Split cronológico independiente por enfermedad (último 20% de semanas como test)
     garantizando fecha_train < cut - 7 días para que el objetivo t+1 no toque test.
  4. Riesgo (bajo/medio/alto/crítico) derivado de int(round(casos_esperados)) frente a
     cuantiles 50/75/90 de las últimas 104 semanas de train del mismo municipio y enfermedad.
  5. Comparación directa por municipio contra persistencia y SARIMA(1,0,1).

Uso: python model/train.py
Salidas: model/artifacts/{modelo_rf.pkl,feature_names.json,metricas.json}, model/docs/shap_summary.png
"""
import json
import os
import warnings
from datetime import datetime

import joblib
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    HAS_PLT = True
except ImportError:
    plt = None
    HAS_PLT = False
import numpy as np
import pandas as pd
import shap
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
)
from sklearn.model_selection import TimeSeriesSplit
try:
    from statsmodels.tsa.statespace.sarimax import SARIMAX
    HAS_SARIMA = True
except ImportError:
    SARIMAX = None
    HAS_SARIMA = False

warnings.filterwarnings("ignore")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "clean", "casos_municipio_semana.csv")
ART = os.path.join(ROOT, "model", "artifacts")
DOCS = os.path.join(ROOT, "model", "docs")

ENFERMEDADES = ("dengue", "influenza", "covid")
LABELS = ["bajo", "medio", "alto", "crítico"]
EDADES = ["edad_0_14", "edad_15_44", "edad_45_64", "edad_65_mas"]
TEST_FRAC = 0.2
QS = (0.5, 0.75, 0.9)
WINDOW = 104
SEED = 42
WEEK = pd.Timedelta(days=7)

FEATURES = (
    [f"lag{k}" for k in range(8)]
    + [f"log_lag{k}" for k in range(8)]
    + ["media_4s", "media_8s", "max_8s", "std_8s", "tendencia", "tendencia_rel", "def_4s"]
    + [f"tasa_{e}" for e in EDADES]
    + ["sem_sin", "sem_cos", "mun_cod"]
)

GRID_PARAMS = [
    {"max_depth": d, "min_samples_leaf": l, "max_features": f}
    for d in (None, 8, 12)
    for l in (1, 3, 5)
    for f in ("sqrt", 0.5)
]


def load_raw(path: str = DATA) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"municipio_id": str}, parse_dates=["fecha_inicio_semana"])
    df["municipio_id"] = df["municipio_id"].astype(str).str.zfill(5)
    df["enfermedad"] = df["enfermedad"].astype(str).str.lower()
    return df.sort_values(["enfermedad", "municipio_id", "fecha_inicio_semana"]).reset_index(drop=True)


def build_mun_map(raw: pd.DataFrame) -> dict:
    mids = sorted(raw["municipio_id"].astype(str).unique())
    return {mid: idx for idx, mid in enumerate(mids)}


def build_features(raw: pd.DataFrame, mun_cod_map: dict, with_target: bool = True) -> pd.DataFrame:
    """Construye features municipales hasta la semana t dentro de cada (municipio_id, enfermedad)."""
    df = raw.sort_values(["enfermedad", "municipio_id", "fecha_inicio_semana"]).copy()
    g = df.groupby(["enfermedad", "municipio_id"], sort=False)

    for k in range(8):
        df[f"lag{k}"] = g["casos"].shift(k)
        df[f"log_lag{k}"] = np.log1p(df[f"lag{k}"])

    df["media_4s"] = g["casos"].transform(lambda s: s.rolling(4).mean())
    df["media_8s"] = g["casos"].transform(lambda s: s.rolling(8).mean())
    df["max_8s"] = g["casos"].transform(lambda s: s.rolling(8).max())
    df["std_8s"] = g["casos"].transform(lambda s: s.rolling(8).std(ddof=0))
    df["tendencia"] = df["log_lag0"] - df["log_lag4"]
    df["tendencia_rel"] = (df["media_4s"] - df["media_8s"]) / (df["media_8s"] + 1.0)
    df["def_4s"] = g["defunciones"].transform(lambda s: s.rolling(4).sum())

    tot4 = g["casos"].transform(lambda s: s.rolling(4).sum()).replace(0, np.nan)
    for e in EDADES:
        df[f"tasa_{e}"] = (g[e].transform(lambda s: s.rolling(4).sum()) / tot4).fillna(0.0)

    df["sem_sin"] = np.sin(2.0 * np.pi * df["sem"] / 52.0)
    df["sem_cos"] = np.cos(2.0 * np.pi * df["sem"] / 52.0)
    df["mun_cod"] = df["municipio_id"].map(mun_cod_map).astype(float)

    if with_target:
        df["casos_next"] = g["casos"].shift(-1)
        df["log_next"] = np.log1p(df["casos_next"])

    return df


def thresholds(df_hist: pd.DataFrame, window: int = WINDOW) -> dict:
    """Cortes [b1, b2, b3] por 'municipio_id|enfermedad' sobre cuantiles QS de train."""
    out = {}
    for (mid, enf), s in df_hist.sort_values("fecha_inicio_semana").groupby(["municipio_id", "enfermedad"])["casos"]:
        b1, b2, b3 = np.quantile(s.tail(window), QS)
        b1 = float(b1)
        b2 = float(max(b2, b1 + 1.0))
        b3 = float(max(b3, b2 + 1.0))
        out[f"{mid}|{enf}"] = [b1, b2, b3]
    return out


def to_class(casos, keys, th: dict) -> np.ndarray:
    return np.array([int(np.searchsorted(th[k], c, side="left")) for c, k in zip(casos, keys)])


def mkey(df: pd.DataFrame) -> np.ndarray:
    return (df["municipio_id"] + "|" + df["enfermedad"]).values


def cls_report(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    return {
        "exactitud": float(accuracy_score(y_true, y_pred)),
        "f1_macro": float(f1_score(y_true, y_pred, average="macro", labels=range(4), zero_division=0)),
        "f1_por_clase": dict(
            zip(LABELS, map(float, f1_score(y_true, y_pred, average=None, labels=range(4), zero_division=0)))
        ),
        "matriz_confusion": confusion_matrix(y_true, y_pred, labels=range(4)).tolist(),
    }


def mae(a, b) -> float:
    return float(mean_absolute_error(a, b))


def rmse(a, b) -> float:
    return float(np.sqrt(mean_squared_error(a, b)))


def make_reg(params: dict, n_estimators: int = 300) -> RandomForestRegressor:
    return RandomForestRegressor(n_estimators=n_estimators, n_jobs=-1, random_state=SEED, **params)


def tune_disease(tr: pd.DataFrame) -> tuple:
    """Selección de hiperparámetros por TimeSeriesSplit (sin fuga) minimizando MAE en log1p."""
    tr_s = tr.sort_values(["fecha_inicio_semana", "municipio_id"]).reset_index(drop=True)
    results = []
    for params in GRID_PARAMS:
        fold_scores = []
        for idx_tr, idx_val in TimeSeriesSplit(n_splits=5).split(tr_s):
            m = make_reg(params, n_estimators=150).fit(tr_s.loc[idx_tr, FEATURES], tr_s.loc[idx_tr, "log_next"])
            pred_val = m.predict(tr_s.loc[idx_val, FEATURES])
            fold_scores.append(mae(tr_s.loc[idx_val, "log_next"], pred_val))
        results.append({**params, "cv_mae_log": float(np.mean(fold_scores))})
    best = min(results, key=lambda r: r["cv_mae_log"])
    return {k: best[k] for k in ("max_depth", "min_samples_leaf", "max_features")}, results


def fit_disease(tr: pd.DataFrame, params: dict) -> RandomForestRegressor:
    return make_reg(params, n_estimators=300).fit(tr[FEATURES], tr["log_next"])


def sarima_municipal(raw_enf: pd.DataFrame, cut: pd.Timestamp) -> pd.DataFrame:
    """SARIMA(1,0,1) por municipio ajustado solo con las últimas WINDOW semanas < cut."""
    rows = []
    for mid, s in raw_enf.groupby("municipio_id"):
        s = s.sort_values("fecha_inicio_semana")
        y = s["casos"].astype(float).values
        n_tr = int((s["fecha_inicio_semana"] < cut).sum())
        train_slice = y[max(0, n_tr - WINDOW):n_tr]
        try:
            if not HAS_SARIMA or np.std(train_slice) == 0:
                nxt = np.append(y[1:], y[-1])
            else:
                res = SARIMAX(train_slice, order=(1, 0, 1), trend="c").fit(disp=False)
                applied = res.apply(y)
                fitted = np.asarray(applied.fittedvalues)
                nxt = np.append(fitted[1:], np.asarray(applied.forecast(1))[0])
        except Exception:
            nxt = np.append(y[1:], y[-1])
        rows.append(
            pd.DataFrame(
                {
                    "municipio_id": mid,
                    "fecha_inicio_semana": s["fecha_inicio_semana"].values,
                    "pred_sarima": np.clip(nxt, 0.0, None),
                }
            )
        )
    return pd.concat(rows, ignore_index=True)


def evaluate_predictions(df_eval: pd.DataFrame, th_m: dict) -> dict:
    """Calcula MAE, RMSE, Exactitud y F1 macro por patología y global."""
    ym = to_class(df_eval["casos_next"], mkey(df_eval), th_m)

    def block(mask: np.ndarray) -> dict:
        d = df_eval[mask]
        y = ym[mask]
        k = mkey(d)
        pred_rf_round = np.round(d["pred_rf"])
        out = {
            "n": int(mask.sum()),
            "casos_medios": float(d["casos_next"].mean()),
            "rf": {
                "mae": mae(d["casos_next"], d["pred_rf"]),
                "rmse": rmse(d["casos_next"], d["pred_rf"]),
                **cls_report(y, to_class(pred_rf_round, k, th_m)),
            },
            "persistencia": {
                "mae": mae(d["casos_next"], d["lag0"]),
                "rmse": rmse(d["casos_next"], d["lag0"]),
                **cls_report(y, to_class(d["lag0"], k, th_m)),
            },
        }
        if "pred_sarima" in d and d["pred_sarima"].notna().all():
            out["sarima"] = {
                "mae": mae(d["casos_next"], d["pred_sarima"]),
                "rmse": rmse(d["casos_next"], d["pred_sarima"]),
                **cls_report(y, to_class(np.round(d["pred_sarima"]), k, th_m)),
            }
        return out

    municipal = {"global": block(np.ones(len(df_eval), dtype=bool))}
    for enf in ENFERMEDADES:
        mask = (df_eval["enfermedad"] == enf).values
        if mask.any():
            municipal[enf] = block(mask)
    return {"municipal": municipal}


def compute_shap_importance(models: dict, test_frames: dict) -> tuple:
    """Calcula mean(|SHAP|) en test para cada patología y promedio global."""
    shap_por_enf = {}
    for enf, model in models.items():
        te = test_frames[enf]
        muestra = te[FEATURES].sample(min(300, len(te)), random_state=SEED)
        sv = np.array(shap.TreeExplainer(model).shap_values(muestra))
        assert sv.shape == (len(muestra), len(FEATURES)), sv.shape
        vals = np.abs(sv).mean(axis=0)
        shap_por_enf[enf] = dict(sorted(zip(FEATURES, map(float, vals)), key=lambda x: -x[1]))

    global_mean = {
        feat: float(np.mean([shap_por_enf[enf][feat] for enf in models]))
        for feat in FEATURES
    }
    shap_global = dict(sorted(global_mean.items(), key=lambda x: -x[1]))
    return shap_por_enf, shap_global


def plot_shap_summary(shap_por_enf: dict, shap_global: dict, out_path: str):
    """Genera resumen visual SHAP por patología y promedio global."""
    if not HAS_PLT:
        return
    top_feats = list(shap_global.keys())[:15][::-1]
    fig, axes = plt.subplots(1, 3, figsize=(15, 6), sharey=True)
    colors = {"dengue": "#b54755", "influenza": "#bd9b43", "covid": "#4e9577"}
    for ax, enf in zip(axes, ENFERMEDADES):
        vals = [shap_por_enf[enf].get(f, 0.0) for f in top_feats]
        ax.barh(top_feats, vals, color=colors[enf])
        ax.set_title(enf.upper(), fontsize=11, fontweight="bold")
        ax.set_xlabel("mean(|SHAP|) en log1p(casos)")
        ax.grid(axis="x", alpha=0.25)
    fig.suptitle("Importancia SHAP por enfermedad - Modelos municipales (test)", fontsize=13, fontweight="bold")
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close(fig)


def main():
    os.makedirs(ART, exist_ok=True)
    os.makedirs(DOCS, exist_ok=True)

    raw = load_raw(DATA)
    mun_cod_map = build_mun_map(raw)
    featured = build_features(raw, mun_cod_map, with_target=True)
    labeled = featured.dropna(subset=FEATURES + ["log_next"]).reset_index(drop=True)

    best_params = {}
    grid_summary = {}
    split_info = {}
    th_test_all = {}
    test_models = {}
    test_frames = {}
    eval_parts = []

    for enf in ENFERMEDADES:
        d_raw = raw[raw["enfermedad"] == enf]
        d_enf = labeled[labeled["enfermedad"] == enf].copy()
        weeks = np.sort(d_enf["fecha_inicio_semana"].unique())
        cut = pd.Timestamp(weeks[int(len(weeks) * (1.0 - TEST_FRAC))])

        # Regla estricta anti-fuga: solo filas cuyo objetivo t+1 ocurre antes del corte
        tr = d_enf[d_enf["fecha_inicio_semana"] < cut - WEEK].copy()
        te = d_enf[d_enf["fecha_inicio_semana"] >= cut].copy()

        th_enf = thresholds(d_raw[d_raw["fecha_inicio_semana"] < cut])
        th_test_all.update(th_enf)

        params, grid_res = tune_disease(tr)
        best_params[enf] = params
        grid_summary[enf] = grid_res
        print(f"[{enf}] mejores hiperparámetros: {params} | train={len(tr)}, test={len(te)}, cut={cut.date()}")

        model = fit_disease(tr, params)
        test_models[enf] = model
        test_frames[enf] = te

        te["pred_rf"] = np.clip(np.expm1(model.predict(te[FEATURES])), 0.0, None)
        assert np.isfinite(te["pred_rf"]).all()

        sar = sarima_municipal(d_raw, cut)
        te = te.merge(sar, on=["municipio_id", "fecha_inicio_semana"], how="left")
        eval_parts.append(te)

        split_info[enf] = {
            "corte_test": str(cut.date()),
            "filas_train": int(len(tr)),
            "filas_test": int(len(te)),
            "rango_raw": f"{d_raw['semana'].min()} -> {d_raw['semana'].max()}",
        }

    eval_df = pd.concat(eval_parts, ignore_index=True)
    ev = evaluate_predictions(eval_df, th_test_all)

    shap_por_enf, shap_global = compute_shap_importance(test_models, test_frames)
    plot_shap_summary(shap_por_enf, shap_global, os.path.join(DOCS, "shap_summary.png"))

    # Modelos finales congelados con todo el histórico etiquetado de cada enfermedad
    models_final = {}
    native_por_enf = {}
    ultima_fecha_enf = {}
    ultima_iso_enf = {}
    for enf in ENFERMEDADES:
        d_full = labeled[labeled["enfermedad"] == enf]
        m_final = fit_disease(d_full, best_params[enf])
        models_final[enf] = m_final
        native_por_enf[enf] = dict(sorted(zip(FEATURES, map(float, m_final.feature_importances_)), key=lambda x: -x[1]))

        d_raw = raw[raw["enfermedad"] == enf]
        last_dt = pd.Timestamp(d_raw["fecha_inicio_semana"].max())
        ultima_fecha_enf[enf] = str(last_dt.date())
        ultima_iso_enf[enf] = str(
            d_raw.loc[d_raw["fecha_inicio_semana"] == last_dt, "semana"].iloc[0]
        )

    native_global = dict(
        sorted(
            {
                feat: float(np.mean([native_por_enf[enf][feat] for enf in ENFERMEDADES]))
                for feat in FEATURES
            }.items(),
            key=lambda x: -x[1],
        )
    )

    th_m_all = thresholds(raw)
    ultima_semana_global = str(pd.Timestamp(raw["fecha_inicio_semana"].max()).date())

    artifact = {
        "arquitectura": "rf-municipal-v2",
        "modelos": models_final,
        "thresholds_municipio": th_m_all,
        "features": FEATURES,
        "mun_cod_map": mun_cod_map,
        "labels": LABELS,
        "edades": EDADES,
        "hiperparametros": best_params,
        "ultima_semana_por_enfermedad": ultima_fecha_enf,
        "ultima_semana_iso_por_enfermedad": ultima_iso_enf,
        "ultima_semana": ultima_semana_global,
    }
    joblib.dump(artifact, os.path.join(ART, "modelo_rf.pkl"))

    with open(os.path.join(ART, "feature_names.json"), "w", encoding="utf-8") as f:
        json.dump({"municipal": FEATURES}, f, indent=2)

    metricas = {
        "fecha_entrenamiento": datetime.now().isoformat(timespec="seconds"),
        "arquitectura": "rf-municipal-v2",
        "split": {
            "por_enfermedad": split_info,
            "filas_muni_train": int(sum(v["filas_train"] for v in split_info.values())),
            "filas_muni_test": int(len(eval_df)),
        },
        "seleccion": {
            "hiperparametros": best_params,
            "grid": grid_summary,
        },
        "test": ev,
        "shap_importancia_global": shap_global,
        "shap_por_enfermedad": shap_por_enf,
        "importancia_nativa": native_global,
    }
    with open(os.path.join(ART, "metricas.json"), "w", encoding="utf-8") as f:
        json.dump(metricas, f, indent=2, ensure_ascii=False, default=str)

    print("\n== EVALUACIÓN MUNICIPAL DIRECTA (semana t+1) ==")
    for k, d in ev["municipal"].items():
        r = d["rf"]
        p = d["persistencia"]
        s = d["sarima"]
        print(
            f"{k:10s} n={d['n']:4d} medios={d['casos_medios']:6.2f} | "
            f"MAE RF {r['mae']:.3f} persist {p['mae']:.3f} SARIMA {s['mae']:.3f} | "
            f"Acc RF {r['exactitud']*100:5.1f}% persist {p['exactitud']*100:5.1f}% | "
            f"F1 RF {r['f1_macro']:.3f} persist {p['f1_macro']:.3f} SARIMA {s['f1_macro']:.3f}"
        )


if __name__ == "__main__":
    main()
