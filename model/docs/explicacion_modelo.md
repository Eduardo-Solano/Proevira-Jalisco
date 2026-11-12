# Explicación del modelo

**Tarea:** predicción semanal (t+1) de casos y nivel de riesgo (`bajo`, `medio`, `alto`, `crítico`) para dengue, influenza y COVID-19 en 12 municipios de la región Centro de Jalisco.

## Diseño
Las series semanales por municipio son casi todo ceros (72–87% de las semanas), pero la serie regional sí tiene señal. Por eso el diseño tiene dos niveles:
1. **Modelo regional:** `RandomForestRegressor` sobre `log1p(casos de la región)` con rezagos, medias móviles, tendencia, tasas por edad y estacionalidad. Se compara con persistencia y con SARIMA(1,0,1).
2. **Municipio:**
   - **Reparto:** casos esperados = pronóstico regional × participación municipal de las últimas 12 semanas.
   - **RF municipal:** un Random Forest con variables de contexto regional.
   - El método por defecto se elige con una validación interna (últimas semanas de train), sin usar test.
3. **Nivel de riesgo:** se define por cuantiles 50/75/90 de las últimas 104 semanas de train, por serie.

## Validación sin fuga de información
- El último 20% de las semanas es test.
- Las filas de train cuyo objetivo (t+1) cae en test se excluyen.
- Los cortes de riesgo y los hiperparámetros se calculan solo con train.
- La búsqueda de hiperparámetros usa `TimeSeriesSplit`.
- SHAP se calcula sobre el clasificador de riesgo municipal.

Las métricas están en `model/artifacts/metricas.json`.

## Limitaciones
- En test (desde 2025-06) la actividad es baja. La persistencia es un rival muy fuerte con conteos tan pequeños.
- Los municipios chicos solo admiten una predicción aproximada. Se recomienda presentarla como nivel de riesgo.
- COVID tiene casi 0 casos desde 2024. Influenza solo existe desde 2024.
