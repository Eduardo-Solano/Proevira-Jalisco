"""Backtest de origen móvil (expanding window) para evaluar el modelo en distintos periodos, incluido el brote
de dengue de 2024. Reutiliza las funciones de train.py y los hiperparámetros congelados en modelo_rf.pkl.

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


def main():
    raw = pd.read_parquet(T.DATA)
    region = T.build_region(raw)
    muni = T.build_muni(raw, region)
    rall = region.dropna(subset=T.REG_FEATURES + ["rlog_next"]).reset_index(drop=True)
    mall = muni.dropna(subset=["share", "casos_next"]).reset_index(drop=True)
    pr = joblib.load(os.path.join(T.ART, "modelo_rf.pkl"))["hiperparametros"]["region"]

    weeks = np.sort(rall["fecha_inicio_semana"].unique())
    starts = [pd.Timestamp(w) for w in weeks[::BLOCK_WEEKS] if pd.Timestamp(w) >= FIRST_TEST]
    folds = []
    for s in starts:
        e = s + BLOCK_WEEKS * T.WEEK
        rtr = rall[rall["fecha_inicio_semana"] < s - T.WEEK]
        rte = rall[(rall["fecha_inicio_semana"] >= s) & (rall["fecha_inicio_semana"] < e)]
        mte = mall[(mall["fecha_inicio_semana"] >= s) & (mall["fecha_inicio_semana"] < e)]
        if len(rte) == 0:
            continue
        th_r = T.thresholds(region[region["fecha_inicio_semana"] < s], ["enfermedad"])
        th_m = T.thresholds(raw[raw["fecha_inicio_semana"] < s], ["municipio_id", "enfermedad"])
        rp, mp = T.predict(T.fit_model(rtr, pr), rte, mte)
        ev = T.evaluar(rp, mp, rte, th_r, th_m, sarima=T.sarima_region(region, s))
        folds.append({"inicio": str(s.date()), "fin": str((e - T.WEEK).date()), "evaluacion": ev})
        print(f"fold {s.date()} .. {(e - T.WEEK).date()} listo")

    # Tabla resumen
    print("\n== REGIONAL por bloque de 26 semanas (MAE: RF / persistencia / SARIMA | F1: RF / persistencia) ==")
    for f in folds:
        print(f"-- {f['inicio']} .. {f['fin']}")
        for k, d in f["evaluacion"]["regional"].items():
            if k == "global":
                continue
            s = d["sarima"]
            print(f"   {k:10s} medios={d['casos_medios']:6.1f} | MAE {d['rf']['mae']:6.2f} / {d['persistencia']['mae']:6.2f} / "
                  f"{s['mae']:6.2f} | F1 {d['rf']['f1_macro']:.2f} / {d['persistencia']['f1_macro']:.2f}")

    print("\n== AGREGADO (promedio ponderado por n sobre todos los bloques) ==")
    agg = {}
    for lvl in ("regional", "municipal"):
        for k in ("global", "dengue", "influenza", "covid"):
            rows = [(f["evaluacion"][lvl][k]) for f in folds]
            n = np.array([r["n"] for r in rows], float)
            w = n / n.sum()
            names = ["rf", "persistencia", "sarima"] if lvl == "regional" else ["reparto", "persistencia"]
            res = {m: {"mae": float(np.dot(w, [r[m]["mae"] for r in rows])),
                       "f1_macro": float(np.dot(w, [r[m]["f1_macro"] for r in rows]))} for m in names}
            agg[f"{lvl}_{k}"] = res
            print(f"{lvl:9s} {k:10s} " + " | ".join(f"{m} MAE {v['mae']:.3f} F1 {v['f1_macro']:.2f}" for m, v in res.items()))

    with open(os.path.join(T.ART, "backtest.json"), "w", encoding="utf-8") as fh:
        json.dump({"bloque_semanas": BLOCK_WEEKS, "agregado": agg, "folds": folds}, fh, indent=2,
                  ensure_ascii=False, default=str)


if __name__ == "__main__":
    main()

