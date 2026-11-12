"""Entrenamiento reproducible: pronóstico SEMANAL regional + reparto municipal, con riesgo derivado del pronóstico.

Diseño (las series municipales semanales son casi todo ceros; la región sí tiene señal):
  1. Modelo regional: RandomForestRegressor sobre log1p(casos de la región Centro) -> casos de t+1.
  2. Municipio: casos_esperados = pronóstico_regional * participación municipal (últimas 12 semanas).
  3. Riesgo (bajo/medio/alto/crítico): se obtiene comparando los casos esperados (redondeados) con cortes
     de cuantiles 50/75/90 de las últimas 104 semanas de train -> siempre coherente con los casos esperados.
  4. Comparación contra persistencia y SARIMA(1,0,1). Todo con información hasta la semana t.

Uso: python model/train.py
Salidas: model/artifacts/{modelo_rf.pkl,feature_names.json,metricas.json}, model/docs/shap_summary.png
"""
import json
import os
import warnings
from datetime import datetime

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shap
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import confusion_matrix, f1_score, mean_absolute_error, mean_squared_error
from sklearn.model_selection import TimeSeriesSplit
from statsmodels.tsa.statespace.sarimax import SARIMAX

warnings.filterwarnings("ignore")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "clean", "casos_municipio_semana.parquet")
ART = os.path.join(ROOT, "model", "artifacts")
DOCS = os.path.join(ROOT, "model", "docs")
LABELS = ["bajo", "medio", "alto", "crítico"]
ENF = {"dengue": 0, "influenza": 1, "covid": 2}
EDADES = ["edad_0_14", "edad_15_44", "edad_45_64", "edad_65_mas"]
TEST_FRAC = 0.2
QS = (0.5, 0.75, 0.9)    # cuantiles de los cortes de riesgo
WINDOW = 104             # semanas recientes de train usadas para los cortes (y para SARIMA)
SHARE_WEEKS = 12         # ventana de la participación municipal
SEED = 42
WEEK = pd.Timedelta(days=7)

# --------------------------------------------------------------------------- features regionales
REG_FEATURES = ([f"rlog_lag{k}" for k in range(8)] + ["rmedia_4s", "rmedia_8s", "rmax_8s", "rtend", "rtend_rel",
                "rdef_4s"] + [f"rtasa_{e}" for e in EDADES] + ["sem_sin", "sem_cos", "enfermedad_cod"])


def build_region(raw: pd.DataFrame) -> pd.DataFrame:
    """Serie semanal de la región (suma de municipios) por enfermedad, con features hasta la semana t."""
    cols = ["casos", "defunciones"] + EDADES
    r = raw.groupby(["enfermedad", "fecha_inicio_semana", "sem"], as_index=False)[cols].sum()
    r = r.sort_values(["enfermedad", "fecha_inicio_semana"]).reset_index(drop=True)
    g = r.groupby("enfermedad", sort=False)
    r["rlog"] = np.log1p(r["casos"])
    for k in range(8):
        r[f"rlog_lag{k}"] = g["rlog"].shift(k)
    r["rmedia_4s"] = g["casos"].transform(lambda s: s.rolling(4).mean())
    r["rmedia_8s"] = g["casos"].transform(lambda s: s.rolling(8).mean())
    r["rmax_8s"] = g["casos"].transform(lambda s: s.rolling(8).max())
    r["rtend"] = r["rlog_lag0"] - r["rlog_lag4"]
    r["rtend_rel"] = (r["rmedia_4s"] - r["rmedia_8s"]) / (r["rmedia_8s"] + 1)
    r["rdef_4s"] = g["defunciones"].transform(lambda s: s.rolling(4).sum())
    tot4 = g["casos"].transform(lambda s: s.rolling(4).sum())
    for e in EDADES:
        r[f"rtasa_{e}"] = (g[e].transform(lambda s: s.rolling(4).sum()) / tot4.replace(0, np.nan)).fillna(0)
    r["sem_sin"] = np.sin(2 * np.pi * r["sem"] / 52)
    r["sem_cos"] = np.cos(2 * np.pi * r["sem"] / 52)
    r["enfermedad_cod"] = r["enfermedad"].map(ENF)
    r["rsum_share"] = g["casos"].transform(lambda s: s.rolling(SHARE_WEEKS).sum())
    r["casos_next"] = g["casos"].shift(-1)
    r["rlog_next"] = g["rlog"].shift(-1)
    return r


def build_muni(raw: pd.DataFrame, region: pd.DataFrame) -> pd.DataFrame:
    """Por municipio: casos actuales (persistencia), participación de las últimas SHARE_WEEKS y objetivo t+1."""
    df = raw.sort_values(["municipio_id", "enfermedad", "fecha_inicio_semana"]).copy()
    g = df.groupby(["municipio_id", "enfermedad"], sort=False)
    df["casos_lag0"] = df["casos"]
    df["sum_share"] = g["casos"].transform(lambda s: s.rolling(SHARE_WEEKS).sum())
    df["casos_next"] = g["casos"].shift(-1)
    df = df.merge(region[["enfermedad", "fecha_inicio_semana", "rsum_share"]], on=["enfermedad", "fecha_inicio_semana"], how="left")
    n_mun = raw["municipio_id"].nunique()
    df["share"] = np.where(df["rsum_share"] > 0, df["sum_share"] / df["rsum_share"].replace(0, np.nan), 1.0 / n_mun)
    return df


def ultima_participacion(raw: pd.DataFrame) -> dict:
    """Participación municipal vigente (última semana disponible) por enfermedad; la usa el backend."""
    out = {}
    for e, d in raw.groupby("enfermedad"):
        ult = d["fecha_inicio_semana"].sort_values().unique()[-SHARE_WEEKS:]
        s = d[d["fecha_inicio_semana"].isin(ult)].groupby("municipio_id")["casos"].sum()
        out[e] = (s / s.sum()).to_dict() if s.sum() > 0 else {m: 1 / len(s) for m in s.index}
    return out


# --------------------------------------------------------------------------- riesgo / métricas
def thresholds(train: pd.DataFrame, by: list, window=WINDOW) -> dict:
    """Cortes [b1,b2,b3] por grupo con cuantiles QS de las últimas `window` semanas."""
    out = {}
    for k, s in train.sort_values("fecha_inicio_semana").groupby(by)["casos"]:
        b1, b2, b3 = np.quantile(s.tail(window), QS)
        b1 = float(b1)
        b2 = float(max(b2, b1 + 1))
        b3 = float(max(b3, b2 + 1))
        out["|".join(k) if isinstance(k, tuple) else k] = [b1, b2, b3]
    return out


def to_class(casos, keys, th) -> np.ndarray:
    return np.array([int(np.searchsorted(th[k], c, side="left")) for c, k in zip(casos, keys)])


def mkey(d):
    return (d["municipio_id"] + "|" + d["enfermedad"]).values


def reporte(y_true, y_pred) -> dict:
    return {"f1_macro": float(f1_score(y_true, y_pred, average="macro", labels=range(4), zero_division=0)),
            "f1_por_clase": dict(zip(LABELS, map(float, f1_score(y_true, y_pred, average=None, labels=range(4), zero_division=0)))),
            "matriz_confusion": confusion_matrix(y_true, y_pred, labels=range(4)).tolist()}


def mae(a, b):
    return float(mean_absolute_error(a, b))


def rmse(a, b):
    return float(np.sqrt(mean_squared_error(a, b)))


# --------------------------------------------------------------------------- modelo
def make_reg(p, n=300):
    return RandomForestRegressor(n_estimators=n, n_jobs=-1, random_state=SEED, **p)


GRID_REG = [{"max_depth": d, "min_samples_leaf": l, "max_features": f}
            for d in (None, 8) for l in (1, 3, 5) for f in ("sqrt", 0.5)]


def tune_region(rtr: pd.DataFrame) -> tuple:
    """Hiperparámetros del modelo regional por TimeSeriesSplit (MAE en log1p), solo con train."""
    rtr = rtr.sort_values("fecha_inicio_semana").reset_index(drop=True)
    res = []
    for p in GRID_REG:
        sc = []
        for a, b in TimeSeriesSplit(n_splits=5).split(rtr):
            m = make_reg(p, 150).fit(rtr.loc[a, REG_FEATURES], rtr.loc[a, "rlog_next"])
            sc.append(mae(rtr.loc[b, "rlog_next"], m.predict(rtr.loc[b, REG_FEATURES])))
        res.append({**p, "cv_mae_log": float(np.mean(sc))})
    best = min(res, key=lambda r: r["cv_mae_log"])
    return {k: best[k] for k in ("max_depth", "min_samples_leaf", "max_features")}, res


def fit_model(rtr, p):
    return make_reg(p).fit(rtr[REG_FEATURES], rtr["rlog_next"])


def predict(model, region_rows, muni_rows):
    """Casos esperados t+1: regional y municipal (reparto)."""
    rp = region_rows[["enfermedad", "fecha_inicio_semana"]].copy()
    rp["pred_region"] = np.clip(np.expm1(model.predict(region_rows[REG_FEATURES])), 0, None)
    m = muni_rows.merge(rp, on=["enfermedad", "fecha_inicio_semana"], how="left")
    m["pred_reparto"] = m["pred_region"] * m["share"]
    assert np.isfinite(m["pred_reparto"]).all() and np.isfinite(rp["pred_region"]).all()
    return rp, m


def sarima_region(region: pd.DataFrame, cut) -> pd.DataFrame:
    """SARIMA(1,0,1) por enfermedad, ajustado con las últimas WINDOW semanas previas a `cut`."""
    rows = []
    for e, s in region.groupby("enfermedad"):
        s = s.sort_values("fecha_inicio_semana")
        y = s["casos"].astype(float).values
        n_tr = int((s["fecha_inicio_semana"] < cut).sum())
        try:
            res = SARIMAX(y[max(0, n_tr - WINDOW):n_tr], order=(1, 0, 1), trend="c").fit(disp=False)
            applied = res.apply(y)
            fitted = np.asarray(applied.fittedvalues)
            nxt = np.append(fitted[1:], np.asarray(applied.forecast(1))[0])
        except Exception:
            nxt = np.append(y[1:], y[-1])
        rows.append(pd.DataFrame({"enfermedad": e, "fecha_inicio_semana": s["fecha_inicio_semana"].values,
                                  "pred_sarima": np.clip(nxt, 0, None)}))
    return pd.concat(rows, ignore_index=True)


def evaluar(rp, m, region_rows, th_r, th_m, sarima=None):
    """Métricas regionales y municipales (global y por enfermedad). Riesgo = f(casos esperados)."""
    rr = region_rows.merge(rp, on=["enfermedad", "fecha_inicio_semana"])
    if sarima is not None:
        rr = rr.merge(sarima, on=["enfermedad", "fecha_inicio_semana"])
    y_true = to_class(rr["casos_next"], rr["enfermedad"].values, th_r)

    def reg_block(mask):
        d, yt = rr[mask], y_true[mask]
        k = d["enfermedad"].values
        out = {"n": int(mask.sum()), "casos_medios": float(d["casos_next"].mean()),
               "rf": {"mae": mae(d["casos_next"], d["pred_region"]), "rmse": rmse(d["casos_next"], d["pred_region"]),
                      **reporte(yt, to_class(np.round(d["pred_region"]), k, th_r))},
               "persistencia": {"mae": mae(d["casos_next"], d["casos"]), "rmse": rmse(d["casos_next"], d["casos"]),
                                **reporte(yt, to_class(d["casos"], k, th_r))}}
        if "pred_sarima" in d:
            out["sarima"] = {"mae": mae(d["casos_next"], d["pred_sarima"]), "rmse": rmse(d["casos_next"], d["pred_sarima"]),
                             **reporte(yt, to_class(np.round(d["pred_sarima"]), k, th_r))}
        return out

    regional = {"global": reg_block(np.ones(len(rr), bool))}
    for e in ENF:
        regional[e] = reg_block((rr["enfermedad"] == e).values)

    ym = to_class(m["casos_next"], mkey(m), th_m)

    def mun_block(mask):
        d, y = m[mask], ym[mask]
        return {"n": int(mask.sum()), "casos_medios": float(d["casos_next"].mean()),
                "reparto": {"mae": mae(d["casos_next"], d["pred_reparto"]), "rmse": rmse(d["casos_next"], d["pred_reparto"]),
                            **reporte(y, to_class(np.round(d["pred_reparto"]), mkey(d), th_m))},
                "persistencia": {"mae": mae(d["casos_next"], d["casos_lag0"]), "rmse": rmse(d["casos_next"], d["casos_lag0"]),
                                 **reporte(y, to_class(d["casos_lag0"], mkey(d), th_m))}}

    municipal = {"global": mun_block(np.ones(len(m), bool))}
    for e in ENF:
        municipal[e] = mun_block((m["enfermedad"] == e).values)
    return {"regional": regional, "municipal": municipal}


def main():
    os.makedirs(ART, exist_ok=True)
    os.makedirs(DOCS, exist_ok=True)
    raw = pd.read_parquet(DATA)
    region = build_region(raw)
    muni = build_muni(raw, region)
    rall = region.dropna(subset=REG_FEATURES + ["rlog_next"]).reset_index(drop=True)
    mall = muni.dropna(subset=["share", "casos_next"]).reset_index(drop=True)

    weeks = np.sort(rall["fecha_inicio_semana"].unique())
    cut = pd.Timestamp(weeks[int(len(weeks) * (1 - TEST_FRAC))])

    def split(d, c):  # train: filas cuyo objetivo (t+1) cae antes de `c` -> sin fuga hacia test
        return d[d["fecha_inicio_semana"] < c - WEEK], d[d["fecha_inicio_semana"] >= c]

    rtr, rte = split(rall, cut)
    _, mte = split(mall, cut)
    th_r = thresholds(region[region["fecha_inicio_semana"] < cut], ["enfermedad"])
    th_m = thresholds(raw[raw["fecha_inicio_semana"] < cut], ["municipio_id", "enfermedad"])

    # 1) hiperparámetros: SOLO CV sobre train
    pr, grid_r = tune_region(rtr)
    print("hiperparámetros regional:", pr)

    # 2) evaluación en test (modelo entrenado solo con train)
    model = fit_model(rtr, pr)
    rp, mp = predict(model, rte, mte)
    ev = evaluar(rp, mp, rte, th_r, th_m, sarima=sarima_region(region, cut))

    # 3) SHAP del regresor regional (sobre test)
    muestra = rte[REG_FEATURES].sample(min(300, len(rte)), random_state=SEED)
    sv = np.array(shap.TreeExplainer(model).shap_values(muestra))
    assert sv.shape == (len(muestra), len(REG_FEATURES)), sv.shape
    shap_global = np.abs(sv).mean(axis=0)
    order = np.argsort(shap_global)
    plt.figure(figsize=(8, 7))
    plt.barh(np.array(REG_FEATURES)[order], shap_global[order], color="#c0392b")
    plt.xlabel("mean(|SHAP|) sobre log1p(casos)")
    plt.title("Importancia SHAP - pronóstico semanal regional (test)")
    plt.tight_layout()
    plt.savefig(os.path.join(DOCS, "shap_summary.png"), dpi=150)
    plt.close()

    # 4) modelo congelado con todo el histórico etiquetado
    th_r_all = thresholds(region, ["enfermedad"])
    th_m_all = thresholds(raw, ["municipio_id", "enfermedad"])
    final = fit_model(rall, pr)
    joblib.dump({"reg_region": final, "thresholds_region": th_r_all, "thresholds_municipio": th_m_all,
                 "participacion_municipal": ultima_participacion(raw), "features_region": REG_FEATURES,
                 "labels": LABELS, "hiperparametros": {"region": pr}, "share_weeks": SHARE_WEEKS,
                 "ultima_semana": str(pd.Timestamp(raw["fecha_inicio_semana"].max()).date())},
                os.path.join(ART, "modelo_rf.pkl"))
    with open(os.path.join(ART, "feature_names.json"), "w", encoding="utf-8") as f:
        json.dump({"region": REG_FEATURES}, f, indent=2)
    metricas = {
        "fecha_entrenamiento": datetime.now().isoformat(timespec="seconds"),
        "split": {"corte_test": str(cut.date()), "filas_region_train": len(rtr), "filas_region_test": len(rte),
                  "filas_muni_test": len(mte)},
        "seleccion": {"hiperparametros_region": pr, "grid_region": grid_r},
        "test": ev,
        "shap_importancia_global": dict(sorted(zip(REG_FEATURES, map(float, shap_global)), key=lambda x: -x[1])),
        "importancia_nativa": dict(sorted(zip(REG_FEATURES, map(float, final.feature_importances_)), key=lambda x: -x[1])),
    }
    with open(os.path.join(ART, "metricas.json"), "w", encoding="utf-8") as f:
        json.dump(metricas, f, indent=2, ensure_ascii=False, default=str)

    print("\n== REGIONAL (semana t+1) ==")
    for k, d in ev["regional"].items():
        s = d["sarima"]
        print(f"{k:10s} n={d['n']:4d} medios={d['casos_medios']:7.2f} | MAE RF {d['rf']['mae']:6.2f} persist {d['persistencia']['mae']:6.2f} "
              f"SARIMA {s['mae']:6.2f} | F1 RF {d['rf']['f1_macro']:.2f} persist {d['persistencia']['f1_macro']:.2f} SARIMA {s['f1_macro']:.2f}")
    print("== MUNICIPAL (reparto) ==")
    for k, d in ev["municipal"].items():
        print(f"{k:10s} n={d['n']:5d} medios={d['casos_medios']:5.2f} | MAE reparto {d['reparto']['mae']:.3f} persist {d['persistencia']['mae']:.3f} "
              f"| F1 reparto {d['reparto']['f1_macro']:.2f} persist {d['persistencia']['f1_macro']:.2f}")


if __name__ == "__main__":
    main()
