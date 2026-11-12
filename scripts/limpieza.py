"""Limpieza batch: CSV limpios por fuente -> artefactos consolidados en data/clean/.

Salidas:
  data/clean/casos_municipio_semana.parquet  (municipio_id, municipio, semana, enfermedad, casos, grupos de edad, ...)
  data/clean/clues.csv                       (catálogo CLUES de Jalisco con horario)
  data/clean/municipios.geojson              (centroides de municipios, derivados de CLUES)

Uso: python scripts/limpieza.py
"""
import glob
import json
import os

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLEAN = os.path.join(ROOT, "data", "clean")
CONFIRMADO = {"1", "2", "3"}  # 1-3 = confirmado (asociación/dictamen/laboratorio)
# Región Centro de Jalisco: 12 municipios. 002 (Acatic) y 114 (Zapotlanejo) no pertenecen y se excluyen.
EXCLUIR = {"14002", "14114"}
GRUPOS = [(0, 14, "edad_0_14"), (15, 44, "edad_15_44"), (45, 64, "edad_45_64"), (65, 200, "edad_65_mas")]


def muni_id(code) -> str:
    return "14" + str(int(float(code))).zfill(3)


def read(pattern, **kw):
    files = sorted(glob.glob(os.path.join(CLEAN, pattern)))
    return pd.concat([pd.read_csv(f, dtype=str, encoding="utf-8-sig", **kw) for f in files], ignore_index=True)


def eventos_dengue() -> pd.DataFrame:
    d = read("dengue/*.csv").drop_duplicates("ID_REGISTRO")
    return pd.DataFrame({
        "municipio_id": d["MUNICIPIO_RES"].map(muni_id),
        "municipio": d["MUNICIPIO"].str.strip().str.upper(),
        "fecha": pd.to_datetime(d["FECHA_SIGN_SINTOMAS"], errors="coerce"),
        "edad": pd.to_numeric(d["EDAD_ANOS"], errors="coerce"),
        "enfermedad": "dengue",
        "defuncion": (d["DEFUNCION"] == "1").astype(int),
    })


def eventos_covid_flu() -> pd.DataFrame:
    c = read("datos_covid_influenza/*.csv")
    base = pd.DataFrame({
        "municipio_id": c["MUNICIPIO_RES"].map(muni_id),
        "municipio": c["MUNICIPIO_NOMBRE"].str.strip().str.upper(),
        "fecha": pd.to_datetime(c["FECHA_SINTOMAS"], errors="coerce"),
        "edad": pd.to_numeric(c["EDAD"], errors="coerce"),
        "defuncion": 0,
    })
    # Formato antiguo (2020-2022): CLASIFICACION_FINAL = COVID. Formato nuevo: columnas COVID/FLU.
    covid = c["CLASIFICACION_FINAL_COVID"].fillna(c["CLASIFICACION_FINAL"]).isin(CONFIRMADO)
    flu = c["CLASIFICACION_FINAL_FLU"].isin(CONFIRMADO)
    return pd.concat([
        base[covid].assign(enfermedad="covid"),
        base[flu].assign(enfermedad="influenza"),
    ], ignore_index=True)


def casos_municipio_semana() -> pd.DataFrame:
    ev = pd.concat([eventos_dengue(), eventos_covid_flu()], ignore_index=True)
    ev = ev.dropna(subset=["fecha"])
    ev = ev[~ev["municipio_id"].isin(EXCLUIR)]
    ev = ev[(ev["edad"].isna()) | ((ev["edad"] >= 0) & (ev["edad"] <= 110))]
    iso = ev["fecha"].dt.isocalendar()
    ev["anio"], ev["sem"] = iso["year"].astype(int), iso["week"].astype(int)
    ev["semana"] = ev["anio"].astype(str) + "-W" + ev["sem"].astype(str).str.zfill(2)
    for lo, hi, name in GRUPOS:
        ev[name] = ev["edad"].between(lo, hi).astype(int)

    nombres = ev.groupby("municipio_id")["municipio"].agg(lambda s: s.mode().iat[0])
    agg = ev.groupby(["municipio_id", "enfermedad", "anio", "sem", "semana"], as_index=False).agg(
        casos=("fecha", "size"), defunciones=("defuncion", "sum"),
        **{n: (n, "sum") for _, _, n in GRUPOS})

    # Rejilla completa municipio x enfermedad x semana (ceros explícitos para series de tiempo)
    lunes = pd.date_range(ev["fecha"].min().normalize(), ev["fecha"].max().normalize(), freq="W-MON")
    semanas = pd.DataFrame({"fecha": lunes})
    iso = semanas["fecha"].dt.isocalendar()
    semanas["anio"], semanas["sem"] = iso["year"].astype(int), iso["week"].astype(int)
    semanas["semana"] = semanas["anio"].astype(str) + "-W" + semanas["sem"].astype(str).str.zfill(2)
    semanas = semanas.drop_duplicates("semana")
    grid = (pd.MultiIndex.from_product([nombres.index, ["dengue", "influenza", "covid"]],
                                       names=["municipio_id", "enfermedad"]).to_frame(index=False)
            .merge(semanas, how="cross"))
    out = grid.merge(agg, on=["municipio_id", "enfermedad", "anio", "sem", "semana"], how="left")
    cols = ["casos", "defunciones"] + [n for _, _, n in GRUPOS]
    out[cols] = out[cols].fillna(0).astype(int)
    out["municipio"] = out["municipio_id"].map(nombres)
    return out.rename(columns={"fecha": "fecha_inicio_semana"}).sort_values(
        ["municipio_id", "enfermedad", "fecha_inicio_semana"]).reset_index(drop=True)


def horario_texto(h: pd.DataFrame) -> pd.Series:
    dias = ["DOMINGO", "LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES", "SABADO"]
    abre = ["Dom", "Lun", "Mar", "Mié", "Jue", "Vie", "Sáb"]
    textos = []
    for _, r in h.iterrows():
        bloques = []
        for i in range(14):
            sfx = "" if i == 0 else f".{i}"
            ini, fin = r.get(f"HORA INICIO{sfx}"), r.get(f"HORA FIN{sfx}")
            if pd.isna(ini) or pd.isna(fin):
                continue
            ds = [abre[k] for k, d in enumerate(dias) if str(r.get(d + sfx)).strip().upper() == "SI"]
            if ds:
                bloques.append(f"{','.join(ds)} {ini}-{fin}")
        textos.append("; ".join(bloques))
    return pd.Series(textos, index=h.index)


def clues() -> pd.DataFrame:
    u = pd.read_csv(os.path.join(CLEAN, "unidades-medicas/datos_clinicas.csv"), dtype=str, encoding="utf-8-sig")
    h = pd.read_csv(os.path.join(CLEAN, "unidades-medicas/horarios_clinicas.csv"), dtype=str, encoding="utf-8-sig")
    h = pd.DataFrame({"CLUES": h["CLUES"], "horario": horario_texto(h)})
    u = u[u["ESTATUS DE OPERACION"] == "EN OPERACION"].copy()
    u = u[~u["CLAVE DEL MUNICIPIO"].map(muni_id).isin(EXCLUIR)]
    lat, lon = pd.to_numeric(u["LATITUD"], errors="coerce"), pd.to_numeric(u["LONGITUD"], errors="coerce")
    u = u[lat.between(18, 23) & lon.between(-106, -101)]  # descarta 0/0 y fuera de Jalisco
    direccion = (u["TIPO DE VIALIDAD"].fillna("") + " " + u["VIALIDAD"].fillna("") + " " +
                 u["NUMERO EXTERIOR"].fillna("").str.strip() + ", " + u["ASENTAMIENTO"].fillna("") +
                 ", CP " + u["CODIGO POSTAL"].fillna("")).str.replace(r"\s+", " ", regex=True).str.strip()
    out = pd.DataFrame({
        "clues": u["CLUES"],
        "nombre": u["NOMBRE DE LA UNIDAD"].str.strip(),
        "institucion": u["NOMBRE DE LA INSTITUCION"],
        "tipo": u["NOMBRE TIPO ESTABLECIMIENTO"],
        "nivel_atencion": u["NIVEL ATENCION"],
        "municipio_id": u["CLAVE DEL MUNICIPIO"].map(muni_id),
        "municipio": u["MUNICIPIO"],
        "direccion": direccion,
        "telefono": u["TELEFONO 1 DEL ESTABLECIMIENTO"],
        "lat": pd.to_numeric(u["LATITUD"]),
        "lon": pd.to_numeric(u["LONGITUD"]),
    })
    return out.merge(h, left_on="clues", right_on="CLUES", how="left").drop(columns="CLUES").reset_index(drop=True)


def municipios_geojson(cl: pd.DataFrame, casos: pd.DataFrame) -> dict:
    nombres = casos.drop_duplicates("municipio_id").set_index("municipio_id")["municipio"]
    cen = cl.groupby("municipio_id")[["lat", "lon"]].median()
    feats = []
    for mid, nombre in nombres.items():
        if mid not in cen.index:
            continue
        feats.append({"type": "Feature",
                      "properties": {"municipio_id": mid, "nombre": nombre},
                      "geometry": {"type": "Point", "coordinates": [float(cen.loc[mid, "lon"]), float(cen.loc[mid, "lat"])]}})
    return {"type": "FeatureCollection", "features": feats}


def main():
    casos = casos_municipio_semana()
    casos.to_parquet(os.path.join(CLEAN, "casos_municipio_semana.parquet"), index=False)
    cl = clues()
    cl.to_csv(os.path.join(CLEAN, "clues.csv"), index=False)
    with open(os.path.join(CLEAN, "municipios.geojson"), "w", encoding="utf-8") as f:
        json.dump(municipios_geojson(cl, casos), f, ensure_ascii=False)
    print(f"casos_municipio_semana: {len(casos)} filas, {casos['semana'].nunique()} semanas, "
          f"{casos['municipio_id'].nunique()} municipios")
    print(casos.groupby("enfermedad")["casos"].sum().to_string())
    print(f"clues: {len(cl)} unidades en operación con coordenadas válidas")


if __name__ == "__main__":
    main()

