"""Limpieza batch: CSV limpios por fuente -> CSV unificado sin pérdidas en data/clean/.

Salidas:
  data/clean/casos_municipio_semana.csv  (municipio_id, municipio, enfermedad, fecha_inicio_semana, anio, sem, semana, casos, defunciones, grupos de edad)
  data/clean/clues.csv                   (catálogo CLUES de la Región Centro con horario)
  data/clean/municipios.geojson          (centroides de los 12 municipios, derivados de CLUES)

Uso: python scripts/limpieza.py
"""
import glob
import json
import os

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLEAN = os.path.join(ROOT, "data", "clean")
CONFIRMADO = {"1", "2", "3"}  # 1-3 = confirmado (asociación/dictamen/laboratorio)
# Región Centro de Jalisco: 12 municipios. 002 (Acatic) y 114 (no pertenece) se excluyen.
EXCLUIR = {"14002", "14114"}
GRUPOS = [(0, 14, "edad_0_14"), (15, 44, "edad_15_44"), (45, 64, "edad_45_64"), (65, 200, "edad_65_mas")]


def muni_id(code) -> str:
    codigo = str(int(float(code)))
    if len(codigo) == 5 and codigo.startswith("14"):
        return codigo
    return "14" + codigo.zfill(3)


def read(pattern, **kw):
    files = sorted(glob.glob(os.path.join(CLEAN, pattern)))
    return pd.concat([pd.read_csv(f, dtype=str, encoding="utf-8-sig", **kw) for f in files], ignore_index=True)


def eventos_dengue() -> pd.DataFrame:
    d = read("dengue/*.csv")
    if "ID_REGISTRO" in d.columns:
        con_id = d["ID_REGISTRO"].notna() & (d["ID_REGISTRO"].astype(str).str.strip() != "")
        d = pd.concat([d[con_id].drop_duplicates("ID_REGISTRO"), d[~con_id]], ignore_index=True)
    municipio_col = d["MUNICIPIO"] if "MUNICIPIO" in d.columns else pd.Series("", index=d.index)
    edad_col = d["EDAD_ANOS"] if "EDAD_ANOS" in d.columns else pd.Series(pd.NA, index=d.index)
    defuncion_col = d["DEFUNCION"] if "DEFUNCION" in d.columns else pd.Series("0", index=d.index)
    return pd.DataFrame({
        "municipio_id": d["MUNICIPIO_RES"].map(muni_id),
        "municipio": municipio_col.fillna("").astype(str).str.strip().str.upper(),
        "fecha": pd.to_datetime(d["FECHA_SIGN_SINTOMAS"], errors="coerce"),
        "edad": pd.to_numeric(edad_col, errors="coerce"),
        "enfermedad": "dengue",
        "defuncion": (defuncion_col.astype(str).str.strip() == "1").astype(int),
    })


def eventos_covid_flu() -> pd.DataFrame:
    c = read("datos_covid_influenza/*.csv")
    municipio_col = c["MUNICIPIO_NOMBRE"] if "MUNICIPIO_NOMBRE" in c.columns else pd.Series("", index=c.index)
    edad_col = c["EDAD"] if "EDAD" in c.columns else pd.Series(pd.NA, index=c.index)
    base = pd.DataFrame({
        "municipio_id": c["MUNICIPIO_RES"].map(muni_id),
        "municipio": municipio_col.fillna("").astype(str).str.strip().str.upper(),
        "fecha": pd.to_datetime(c["FECHA_SINTOMAS"], errors="coerce"),
        "edad": pd.to_numeric(edad_col, errors="coerce"),
        "defuncion": 0,
    })
    # Formato 2020-2023: CLASIFICACION_FINAL = COVID. Formato 2024+: CLASIFICACION_FINAL_COVID / CLASIFICACION_FINAL_FLU.
    clas_covid = c.get("CLASIFICACION_FINAL_COVID", pd.Series(pd.NA, index=c.index))
    clas_gen = c.get("CLASIFICACION_FINAL", pd.Series(pd.NA, index=c.index))
    clas_flu = c.get("CLASIFICACION_FINAL_FLU", pd.Series(pd.NA, index=c.index))
    covid = clas_covid.fillna(clas_gen).astype(str).str.strip().isin(CONFIRMADO)
    flu = clas_flu.astype(str).str.strip().isin(CONFIRMADO)
    return pd.concat([
        base[covid].assign(enfermedad="covid"),
        base[flu].assign(enfermedad="influenza"),
    ], ignore_index=True)


def casos_municipio_semana() -> pd.DataFrame:
    ev = pd.concat([eventos_dengue(), eventos_covid_flu()], ignore_index=True)
    ev = ev.dropna(subset=["fecha"])
    ev = ev[~ev["municipio_id"].isin(EXCLUIR)].copy()

    # Alinear exactamente cada fecha al lunes de su semana ISO (evita perder casos de la semana 1)
    ev["fecha_inicio_semana"] = ev["fecha"].dt.normalize() - pd.to_timedelta(ev["fecha"].dt.day_of_week, unit="D")
    for lo, hi, name in GRUPOS:
        ev[name] = ev["edad"].between(lo, hi).astype(int)

    nombres = ev.groupby("municipio_id")["municipio"].agg(lambda s: s.mode().iat[0])

    # Construir rejilla semanal por cada enfermedad usando SU PROPIO rango real de fechas
    # (evita inyectar años de ceros artificiales en Influenza 2020-2023 o semanas futuras sin corte en Dengue)
    partes = []
    cols = ["casos", "defunciones"] + [n for _, _, n in GRUPOS]
    for enf, sub in ev.groupby("enfermedad"):
        agg = sub.groupby(["municipio_id", "enfermedad", "fecha_inicio_semana"], as_index=False).agg(
            casos=("fecha", "size"),
            defunciones=("defuncion", "sum"),
            **{n: (n, "sum") for _, _, n in GRUPOS},
        )
        lunes = pd.date_range(sub["fecha_inicio_semana"].min(), sub["fecha_inicio_semana"].max(), freq="W-MON")
        semanas = pd.DataFrame({"fecha_inicio_semana": lunes})
        iso = semanas["fecha_inicio_semana"].dt.isocalendar()
        semanas["anio"] = iso["year"].astype(int)
        semanas["sem"] = iso["week"].astype(int)
        semanas["semana"] = semanas["anio"].astype(str) + "-W" + semanas["sem"].astype(str).str.zfill(2)

        grid = (
            pd.MultiIndex.from_product([nombres.index, [enf]], names=["municipio_id", "enfermedad"])
            .to_frame(index=False)
            .merge(semanas, how="cross")
        )
        merged = grid.merge(agg, on=["municipio_id", "enfermedad", "fecha_inicio_semana"], how="left")
        merged[cols] = merged[cols].fillna(0).astype(int)
        merged["municipio"] = merged["municipio_id"].map(nombres)
        partes.append(merged)

    out = pd.concat(partes, ignore_index=True)
    columnas_orden = [
        "municipio_id", "municipio", "enfermedad",
        "fecha_inicio_semana", "anio", "sem", "semana",
        "casos", "defunciones",
    ] + [n for _, _, n in GRUPOS]
    return (
        out[columnas_orden]
        .sort_values(["municipio_id", "enfermedad", "fecha_inicio_semana"])
        .reset_index(drop=True)
    )


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
    csv_out = os.path.join(CLEAN, "casos_municipio_semana.csv")
    casos.to_csv(csv_out, index=False, encoding="utf-8-sig")

    # Eliminar el parquet antiguo para evitar incongruencias entre fuentes
    old_parquet = os.path.join(CLEAN, "casos_municipio_semana.parquet")
    if os.path.exists(old_parquet):
        os.remove(old_parquet)

    cl = clues()
    cl.to_csv(os.path.join(CLEAN, "clues.csv"), index=False)
    with open(os.path.join(CLEAN, "municipios.geojson"), "w", encoding="utf-8") as f:
        json.dump(municipios_geojson(cl, casos), f, ensure_ascii=False)
    print(f"casos_municipio_semana.csv: {len(casos)} filas, {casos['municipio_id'].nunique()} municipios")
    for enf, g in casos.groupby("enfermedad"):
        print(f"  {enf:10s}: {g['casos'].sum():6d} casos | {g['semana'].min()} -> {g['semana'].max()} ({g['semana'].nunique()} sem)")
    print(f"clues: {len(cl)} unidades en operación con coordenadas válidas")


if __name__ == "__main__":
    main()
