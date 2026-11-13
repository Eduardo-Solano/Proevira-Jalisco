# Explicación del modelo municipal (`rf-municipal-v2`)

**Tarea:** predicción semanal directa (`t+1`) de casos esperados y nivel de riesgo (`bajo`, `medio`, `alto`, `crítico`) para **dengue**, **influenza** y **COVID-19** en los 12 municipios de la Región Centro de Jalisco.

## Fuente de datos unificada (sin `.parquet`)
- Todos los procesos de entrenamiento, backtest, inferencia y reportes consumen directamente el archivo unificado [casos_municipio_semana.csv](../../data/clean/casos_municipio_semana.csv) generado por `scripts/limpieza.py`.
- Cada patología conserva exactamente su rango temporal real sin inyectar semanas inexistentes ni filtrar casos por edad:
  - **COVID-19:** `2020-W09` -> `2026-W44` (`220,877` casos en 349 semanas).
  - **Dengue:** `2020-W01` -> `2026-W43` (`10,232` casos en 356 semanas).
  - **Influenza:** `2024-W01` -> `2026-W44` (`703` casos en 148 semanas).

## Arquitectura municipal directa (sin reparto regional)
1. **Un regresor dedicado por enfermedad:** `RandomForestRegressor` entrenado sobre `log1p(casos_municipio)` de la semana `t+1`, con variables construidas exclusivamente dentro de cada serie `(municipio_id, enfermedad)` hasta la semana `t` (`lag0..7`, `log_lag0..7`, medias móviles, volatilidad, tendencia, defunciones recientes, proporciones por grupo de edad, estacionalidad ISO `sem_sin`/`sem_cos` y código municipal `mun_cod`).
2. **Clasificación de riesgo congruente:** el nivel de riesgo se obtiene comparando `int(round(casos_esperados))` contra los cuantiles `50/75/90` de las últimas `104` semanas de entrenamiento del mismo municipio y enfermedad, evitando incongruencias entre casos proyectados y etiqueta de riesgo.
3. **Comparativa:** cada modelo municipal se evalúa frente a **persistencia** (`casos(t)`) y **SARIMA(1,0,1)** municipal.

## Validación sin fuga de información
- División cronológica independiente por enfermedad (último 20% de semanas como `test`).
- Exclusión estricta en `train` de filas cuyo objetivo `t+1` cruza el corte hacia `test` (`fecha < cut - 7 días`).
- Búsqueda de hiperparámetros con `TimeSeriesSplit(5)` y cálculo de umbrales únicamente dentro de `train`.
- Validación adicional en ventana móvil expansiva en `model/backtest.py` (`4,956` evaluaciones municipales entre 2023 y 2026).

Las métricas completas y la importancia SHAP global y por enfermedad se almacenan en `model/artifacts/metricas.json`.
