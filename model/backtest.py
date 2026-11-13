"""Backtest de origen móvil (expanding window) por enfermedad y municipio.

Evalúa el desempeño fuera de muestra en bloques de 26 semanas (incluido el brote
de dengue 2024 y las temporadas 2024-2026) reutilizando las funciones y los
hiperparámetros congelados de train.py / modelo_rf.pkl.

Uso: python model/backtest.py
Salida: model/artifacts/backtest.json
"""
import json
import os
import sys

import joblib
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import train as T  # noqa: E402

BLOCK_WEEKS = 26
FIRST_TEST = pd.Timestamp("2023-07-01")
MIN_TRAIN_WEEKS = 26


def main():
    raw = T.load_raw(T.DATA)
    art = joblib.load(os.path.join(T.ART, "modelo_rf.pkl"))
    mun_cod_map = art["mun_cod_map"]
    best_params = art["hiperparametros"]

    featured = T.build_features(raw, mun_cod_map, with_target=True)
    labeled = featured.dropna(subset=T.FEATURES + ["log_next"]).reset_index(drop=True)

    folds_by_disease = {e: [] for e in T.ENFERMEDADES}
    all_eval_parts = []

    for enf in T.ENFERMEDADES:
        d_raw = raw[raw["enfermedad"] == enf]
        d_enf = labeled[labeled["enfermedad"] == enf].copy()
        weeks = np.sort(d_enf["fecha_inicio_semana"].unique())
        starts = [pd.Timestamp(w) for w in weeks[::BLOCK_WEEKS] if pd.Timestamp(w) >= FIRST_TEST]

        for s in starts:
            e = s + BLOCK_WEEKS * T.WEEK
            tr = d_enf[d_enf["fecha_inicio_semana"] < s - T.WEEK].copy()
            te = d_enf[(d_enf["fecha_inicio_semana"] >= s) & (d_enf["fecha_inicio_semana"] < e)].copy()
            if tr["fecha_inicio_semana"].nunique() < MIN_TRAIN_WEEKS or len(te) == 0:
                continue

            th = T.thresholds(d_raw[d_raw["fecha_inicio_semana"] < s])
            model = T.fit_disease(tr, best_params[enf])
            te["pred_rf"] = np.clip(np.expm1(model.predict(te[T.FEATURES])), 0.0, None)
            sar = T.sarima_municipal(d_raw, s)
            te = te.merge(sar, on=["municipio_id", "fecha_inicio_semana"], how="left")

            ev = T.evaluate_predictions(te, th)["municipal"][enf]
            folds_by_disease[enf].append(
                {"inicio": str(s.date()), "fin": str((e - T.WEEK).date()), "evaluacion": ev}
            )
            te["fold_inicio"] = str(s.date())
            te["clase_true"] = T.to_class(te["casos_next"], T.mkey(te), th)
            te["clase_rf"] = T.to_class(np.round(te["pred_rf"]), T.mkey(te), th)
            te["clase_pers"] = T.to_class(te["lag0"], T.mkey(te), th)
            te["clase_sar"] = T.to_class(np.round(te["pred_sarima"]), T.mkey(te), th)
            all_eval_parts.append(te)
            print(f"[{enf:9s}] fold {s.date()} .. {(e - T.WEEK).date()} | n={len(te)} MAE RF {ev['rf']['mae']:.3f} vs persist {ev['persistencia']['mae']:.3f}")

    print("\n== AGREGADO BACKTEST MUNICIPAL (promedio ponderado por n) ==")
    agregado = {}
    for enf in T.ENFERMEDADES:
        rows = [f["evaluacion"] for f in folds_by_disease[enf]]
        if not rows:
            continue
        n = np.array([r["n"] for r in rows], dtype=float)
        w = n / n.sum()
        res = {
            "n_total": int(n.sum()),
            "folds": len(rows),
        }
        for m in ("rf", "persistencia", "sarima"):
            if all(m in r for r in rows):
                res[m] = {
                    "mae": float(np.dot(w, [r[m]["mae"] for r in rows])),
                    "rmse": float(np.dot(w, [r[m]["rmse"] for r in rows])),
                    "exactitud": float(np.dot(w, [r[m]["exactitud"] for r in rows])),
                    "f1_macro": float(np.dot(w, [r[m]["f1_macro"] for r in rows])),
                }
        agregado[enf] = res
        print(
            f"{enf:10s} n={res['n_total']:4d} | "
            f"MAE RF {res['rf']['mae']:.3f} persist {res['persistencia']['mae']:.3f} SARIMA {res['sarima']['mae']:.3f} | "
            f"Acc RF {res['rf']['exactitud']*100:5.1f}% | F1 RF {res['rf']['f1_macro']:.3f} persist {res['persistencia']['f1_macro']:.3f}"
        )

    if all_eval_parts:
        pooled = pd.concat(all_eval_parts, ignore_index=True)
        n_glob = len(pooled)
        agregado["global"] = {
            "n_total": int(n_glob),
            "rf": {
                "mae": T.mae(pooled["casos_next"], pooled["pred_rf"]),
                "rmse": T.rmse(pooled["casos_next"], pooled["pred_rf"]),
                "exactitud": float((pooled["clase_true"] == pooled["clase_rf"]).mean()),
                "f1_macro": float(T.f1_score(pooled["clase_true"], pooled["clase_rf"], average="macro", labels=range(4), zero_division=0)),
            },
            "persistencia": {
                "mae": T.mae(pooled["casos_next"], pooled["lag0"]),
                "rmse": T.rmse(pooled["casos_next"], pooled["lag0"]),
                "exactitud": float((pooled["clase_true"] == pooled["clase_pers"]).mean()),
                "f1_macro": float(T.f1_score(pooled["clase_true"], pooled["clase_pers"], average="macro", labels=range(4), zero_division=0)),
            },
            "sarima": {
                "mae": T.mae(pooled["casos_next"], pooled["pred_sarima"]),
                "rmse": T.rmse(pooled["casos_next"], pooled["pred_sarima"]),
                "exactitud": float((pooled["clase_true"] == pooled["clase_sar"]).mean()),
                "f1_macro": float(T.f1_score(pooled["clase_true"], pooled["clase_sar"], average="macro", labels=range(4), zero_division=0)),
            },
        }
        g = agregado["global"]
        print(
            f"{'global':10s} n={g['n_total']:4d} | "
            f"MAE RF {g['rf']['mae']:.3f} persist {g['persistencia']['mae']:.3f} SARIMA {g['sarima']['mae']:.3f} | "
            f"Acc RF {g['rf']['exactitud']*100:5.1f}% | F1 RF {g['rf']['f1_macro']:.3f} persist {g['persistencia']['f1_macro']:.3f}"
        )

    with open(os.path.join(T.ART, "backtest.json"), "w", encoding="utf-8") as fh:
        json.dump(
            {"bloque_semanas": BLOCK_WEEKS, "agregado": agregado, "folds_por_enfermedad": folds_by_disease},
            fh,
            indent=2,
            ensure_ascii=False,
            default=str,
        )


if __name__ == "__main__":
    main()
