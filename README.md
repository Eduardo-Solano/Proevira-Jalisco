# Sistema de Vigilancia Epidemiológica y Orientación Ciudadana (Dengue, Influenza y COVID-19)

Plataforma integral de vigilancia epidemiológica, predicción municipal explicable, alertas en tiempo real y orientación ciudadana multiplataforma con soporte offline. Diseñada para ejecutarse con un equipo de **3 desarrolladores en un sprint de 7 días** utilizando tecnologías gratuitas y de código abierto.

---

## 1. Decisiones Arquitectónicas Clave

1. **App Móvil Multiplataforma Offline-First (`Flutter`):**
   - Una sola base de código para Android e iOS con generación directa de `APK` sin costos de licenciamiento ni tiempos de revisión en tiendas.
   - Persistencia local mediante **`sqflite`** (SQLite) para almacenar en caché el catálogo **CLUES**, alertas activas y seguimiento de síntomas del usuario, sincronizando automáticamente cuando se recupera conectividad.
   - Geolocalización gratuita mediante **`geolocator` + `flutter_map`** (OpenStreetMap).
2. **Backend como Única Fuente de Verdad (`FastAPI`):**
   - Expone una API REST (`/api/v1/*`) con documentación Swagger automática y un canal **WebSocket** (`/ws/alerts`) para notificaciones push en vivo cuando el modelo o un funcionario detecta riesgo alto en un municipio.
   - Sirve las predicciones del modelo **Random Forest** y calcula explicabilidad local (**SHAP**) y distancias geoespaciales (**Haversine**).
3. **Modelo Predictivo Explicable (`scikit-learn` + `SHAP` + `Prophet`/`SARIMA`):**
   - Clasificador `RandomForestClassifier` validado con `TimeSeriesSplit`.
   - Comparado cuantitativamente contra un modelo baseline (`Prophet` o `SARIMA` de `statsmodels`) mediante métricas `MAE`, `RMSE` y `F1` por clase de riesgo (`bajo`, `medio`, `alto`, `crítico`).
4. **Dashboard Web Epidemiológico (`Streamlit`):**
   - Visualización rápida de mapas de calor municipales con **`folium`**, series de tendencia y gráficas **SHAP** con **`plotly express`**, y consola de emisión/recepción de alertas en tiempo real.
5. **Autenticación y Roles (`Firebase Authentication` + JWT):**
   - Roles diferenciados: `paciente`, `medico` y `funcionario`. Los médicos se registran con `verificado: false` hasta aprobación manual de un funcionario. Contempla respaldo de login local en FastAPI mediante `passlib`.

---

## 2. Arquitectura del Sistema (5 Capas)

```text
[1. FUENTES DE DATOS (CSV Oficiales)]
    SINAVE / DGE  |  Datos Abiertos Salud  |  CLUES (DGIS)  |  Anuario Morbilidad
                                      │ (limpieza batch)
                                      ▼
[2. CAPA DE DATOS Y MODELO (Python)]
    pandas  +  scikit-learn (Random Forest)  +  SHAP  +  Prophet/SARIMA (baseline)
    Salidas: dataset_limpio.parquet | modelo_rf.pkl | feature_names.json | metricas.json
                                      │ (carga inicial / reentrenamiento)
                                      ▼
[3. CAPA DE PERSISTENCIA]
    SQLite (prototipo) / PostgreSQL + PostGIS (opcional)
    Tablas: municipios | predicciones | alertas | clues | usuarios | sintomas
                                      │
                                      ▼
[4. CAPA DE APLICACIÓN — BACKEND FASTAPI (ÚNICA FUENTE DE VERDAD)]
    REST /api/v1/*  |  Auth JWT (Firebase)  |  Inferencia RF + SHAP
    WebSocket /ws/alerts  |  RBAC por rol  |  Cálculo geoespacial Haversine
                        ┌─────────────┴─────────────┐
                        │ HTTP/JSON + WebSocket     │ HTTP/JSON + WebSocket
                        ▼                           ▼
[5A. CLIENTE WEB (Streamlit)]              [5B. CLIENTE MÓVIL (Flutter)]
    Dashboards y mapas de calor                SQLite offline (sqflite) + geolocalización
    Roles: funcionario / médico                Roles: paciente / médico
```

---

## 3. Estructura Oficial del Repositorio

El agente de desarrollo debe respetar exactamente la siguiente organización de directorios y archivos:

```text
proyecto-dengue-influenza-covid/
├── README.md                        # Arranque en 3 comandos + URLs de demo
├── .gitignore                       # data/raw, *.pkl, .env, node_modules
├── .env.example                     # Variables: DB_URL, JWT_SECRET, FIREBASE_*
├── docker-compose.yml               # Opcional: backend + volumen SQLite
├── data/
│   ├── raw/                         # CSVs originales (no versionar)
│   └── clean/
│       ├── casos_municipio_semana.parquet
│       ├── clues.csv
│       └── municipios.geojson
├── scripts/
│   └── limpieza.py                  # pandas: raw → clean
├── model/
│   ├── notebook_entrenamiento.ipynb # EDA + features + RF + SHAP + baseline
│   ├── train.py                     # Script reproducible (mismo pipeline)
│   ├── artifacts/
│   │   ├── modelo_rf.pkl
│   │   ├── feature_names.json
│   │   └── metricas.json            # MAE, RMSE, F1, matriz confusión
│   └── docs/
│       ├── explicacion_modelo.md
│       └── shap_summary.png
├── backend/
│   ├── main.py                      # FastAPI app + include_routers + WS
│   ├── config.py                    # pydantic-settings (.env)
│   ├── requirements.txt
│   ├── db/
│   │   ├── database.py              # SQLAlchemy engine/session
│   │   ├── models.py                # Tablas ORM
│   │   └── seed.py                  # Carga inicial (municipios, CLUES, predicciones)
│   ├── api/
│   │   ├── __init__.py
│   │   ├── auth.py                  # /auth/*
│   │   ├── predictions.py           # /predictions/*
│   │   ├── alerts.py                # /alerts/* + /ws/alerts
│   │   ├── clues.py                 # /clues/*
│   │   ├── symptoms.py              # /symptoms/*
│   │   ├── dashboard.py             # /dashboard/*
│   │   └── system.py                # /health, /version
│   ├── core/
│   │   ├── security.py              # JWT, roles, dependencias
│   │   ├── geo.py                   # Haversine
│   │   └── inference.py             # Carga modelo_rf.pkl, predice, SHAP
│   ├── schemas/
│   │   ├── auth.py
│   │   ├── prediction.py
│   │   ├── alert.py
│   │   ├── clue.py
│   │   └── symptom.py
│   └── ws/
│       └── manager.py               # ConnectionManager broadcast
├── web/
│   ├── app.py                       # Login + navegación
│   ├── pages/
│   │   ├── 1_Mapa_Riesgo.py         # folium heatmap
│   │   ├── 2_Predicciones.py        # plotly tendencia + SHAP
│   │   └── 3_Alertas.py             # websocket-client en vivo
│   ├── api_client.py                # requests + JWT + ws (único que habla con backend)
│   ├── auth_ui.py                   # Formulario login/registro
│   └── requirements.txt
├── mobile/
│   ├── pubspec.yaml
│   └── lib/
│       ├── main.dart
│       ├── config.dart              # baseUrl, wsUrl
│       ├── api/
│       │   ├── api_client.dart      # http + JWT interceptor
│       │   └── ws_client.dart       # web_socket_channel
│       ├── local_db/
│       │   ├── database_helper.dart # sqflite: clues, alerts, symptoms
│       │   └── sync_service.dart    # Cola synced=false → POST
│       ├── auth/
│       │   └── auth_service.dart    # firebase_auth o login local
│       ├── screens/
│       │   ├── login_screen.dart
│       │   ├── home_paciente.dart   # Alertas + síntomas + mapa
│       │   ├── home_medico.dart     # Alertas municipio + pacientes
│       │   ├── mapa_clues.dart      # geolocator + flutter_map
│       │   ├── seguimiento_sintomas.dart
│       │   └── alertas_screen.dart
│       └── models/
│           ├── prediccion.dart
│           ├── alerta.dart
│           └── clue.dart
└── docs/
    ├── arquitectura.png
    ├── contrato_api.md              # Copia legible del Swagger
    ├── normativa_mexico.md          # LFPDPPP, NOM-004, NOM-017
    ├── guion_demo.md                # Pasos demo en vivo
    └── video_demo.mp4               # Respaldo pregrabado
```

---

## 4. Contrato Maestro de Endpoints (Backend FastAPI)

### 4.1 Autenticación (`/auth`)
| Endpoint | Método | Rol | Descripción | Request | Response |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `/auth/login` | `POST` | público | Valida credenciales en Firebase (o local), devuelve JWT propio + rol | `{email, password}` | `{token, role, uid, municipio_id}` |
| `/auth/me` | `GET` | todos | Devuelve perfil del usuario autenticado | Header `Authorization` | `{uid, email, role, municipio_id, verificado}` |
| `/auth/register-medico` | `POST` | público | Registro de médico/funcionario; inicia con `verificado: false` | `{email, password, institucion, cedula}` | `{uid, role, verificado: false}` |
| `/auth/verify-medico/{uid}` | `POST` | `funcionario` | Aprueba manualmente a un médico | Path `uid` | `{uid, verificado: true}` |

### 4.2 Predicciones (`/predictions`)
*Regla de negocio:* `inference.py` carga `modelo_rf.pkl` al arrancar. `/predictions` calcula bajo demanda y guarda en caché en la tabla `predicciones`. `/bulk` lee de caché o calcula en lote.

| Endpoint | Método | Rol | Descripción | Request | Response |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `/predictions` | `GET` | todos | Predicción de casos + nivel de riesgo por municipio/semana | `?municipio=14039&semana=2026-W20&enfermedad=dengue` | `{municipio, semana, enfermedad, casos_esperados, nivel_riesgo, shap_top3: [{feature, valor}]}` |
| `/predictions/bulk` | `GET` | `funcionario`/`medico` | Predicciones de todos los municipios de una semana (mapa de calor) | `?semana=2026-W20` | `[{municipio, lat, lon, nivel_riesgo, casos_esperados}, ...]` |
| `/predictions/history` | `GET` | `funcionario`/`medico` | Serie histórica + predicción para graficar tendencia | `?municipio=14039&enfermedad=dengue&semanas=12` | `{historico: [{semana, casos}], prediccion: [{semana, casos, nivel}]}` |
| `/predictions/explain` | `GET` | `funcionario`/`medico` | Explicabilidad SHAP detallada de una predicción | `?municipio=14039&semana=2026-W20` | `{feature_importance: [{feature, shap}], base_value}` |

### 4.3 Alertas (`/alerts` y WebSocket)
*Regla de negocio:* `ws/manager.py` mantiene `ConnectionManager` con la lista de conexiones activas. Al crear una alerta se persiste en BD y se invoca `manager.broadcast(json)`.

| Endpoint | Método | Rol | Descripción | Request | Response / Mensaje |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `/alerts` | `GET` | todos | Alertas activas (filtrable por municipio) | `?municipio=14039&activa=true` | `[{id, municipio, nivel, mensaje, ts}]` |
| `/alerts` | `POST` | `funcionario` | Crea alerta manual y la emite por WebSocket | `{municipio_id, nivel, mensaje}` | `{id, emitida: true}` |
| `/alerts/{id}` | `PATCH` | `funcionario` | Activa o desactiva una alerta existente | `{activa: false}` | `{id, activa}` |
| `/ws/alerts` | `WS` | todos (JWT en query) | Stream en vivo de alertas nuevas | Query `?token=...` | `{tipo: "alerta", id, municipio, nivel, mensaje, ts}` |

### 4.4 CLUES / Geolocalización (`/clues`)
*Regla de negocio:* `core/geo.py` implementa distancia **Haversine** en Python sobre SQLite (si se migra a PostGIS, sustituir por `ST_Distance`).

| Endpoint | Método | Rol | Descripción | Request | Response |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `/clues/nearest` | `GET` | `paciente`/`medico` | Unidades médicas más cercanas a `lat`/`lon` | `?lat=20.67&lon=-103.35&limit=5` | `[{clues, nombre, direccion, nivel_atencion, distancia_km, lat, lon}]` |
| `/clues/{clues}` | `GET` | todos | Detalle de una unidad médica | Path `clues` | `{clues, nombre, direccion, telefono, horario, lat, lon}` |
| `/clues` | `GET` | `funcionario` | Catálogo completo para seed/administración | `?municipio_id=...` | `[{...}, ...]` |

### 4.5 Síntomas / Seguimiento (`/symptoms`)
*Regla de negocio offline:* La app móvil guarda en SQLite con `synced=false` y ejecuta `POST /symptoms` al recuperar red. El campo `id_local` (UUID generado en el dispositivo) asegura idempotencia y evita duplicados.

| Endpoint | Método | Rol | Descripción | Request | Response |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `/symptoms` | `POST` | `paciente` | Registra seguimiento de síntomas (idempotente por `id_local`) | `{id_local, fiebre, cefalea, ...}` | `{id, synced: true, ts_registro}` |
| `/symptoms/mine` | `GET` | `paciente` | Historial del usuario autenticado | Header `Authorization` | `[{...}]` |
| `/symptoms/{id}` | `GET` | `paciente`/`medico` | Detalle (médico consulta los de su municipio) | Path `id` | `{...}` |

### 4.6 Dashboard (`/dashboard`) y Sistema (`/`)
| Endpoint | Método | Rol | Descripción | Request | Response |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `/dashboard/summary` | `GET` | `funcionario`/`medico` | Totales, tendencia y desglose por municipio | `?semana=2026-W20` | `{totales: {dengue, influenza, covid}, tendencia: [...], por_municipio: [...]}` |
| `/dashboard/kpis` | `GET` | `funcionario` | KPIs rápidos de monitoreo | — | `{casos_semana, municipios_riesgo_alto, alertas_activas, hospitalizaciones_est}` |
| `/dashboard/heatmap` | `GET` | `funcionario`/`medico` | Datos listos para `folium` (GeoJSON + valores) | `?semana=2026-W20` | `{geojson, valores: {municipio_id: nivel}}` |
| `/health` | `GET` | público | Healthcheck para Render/Fly.io | — | `{status: "ok", modelo_cargado: true, db: "ok"}` |
| `/version` | `GET` | público | Versión, rango de datos y siguiente semana proyectada | — | `{api, modelo, fecha_entrenamiento, ultima_semana_datos, semana_prediccion}` |
| `/model/metrics` | `GET` | público | Métricas de prueba exportadas por `model/train.py` | — | `{fecha_entrenamiento, split, test}` |

---

## 5. Plan de Trabajo por Fases (Guía de Ejecución para el Agente)

### Fase 0: Inicialización y Estructura Base (Día 1)
- [ ] Crear el árbol de directorios completo definido en la Sección 3.
- [ ] Configurar `.gitignore`, `.env.example`, `backend/requirements.txt`, `web/requirements.txt` y `mobile/pubspec.yaml`.
- [ ] Verificar que ningún archivo crudo (`data/raw/*`), secreto (`.env`) o binario pesado (`*.pkl`) quede sin reglas de exclusión.

### Fase 1: Pipeline de Datos y Modelado Predictivo Explicable (Días 1–4)
- [ ] Desarrollar `scripts/limpieza.py` con `pandas` para procesar fuentes CSV (SINAVE/DGE, CLUES, Anuario de Morbilidad) hacia `data/clean/casos_municipio_semana.parquet` y `data/clean/clues.csv`.
- [ ] Implementar ingeniería de características en `model/notebook_entrenamiento.ipynb` y `model/train.py`: rezagos temporales, estacionalidad por semana epidemiológica, tasas por grupo de edad y tendencia.
- [ ] Entrenar `RandomForestClassifier` con `TimeSeriesSplit` y compararlo contra baseline (`Prophet` o `SARIMA` en `statsmodels`).
- [ ] Calcular métricas (`MAE`, `RMSE`, `F1` por nivel `bajo`/`medio`/`alto`/`crítico`), matriz de confusión, importancia nativa y valores **SHAP**.
- [ ] Exportar artefactos congelados en `model/artifacts/` (`modelo_rf.pkl`, `feature_names.json`, `metricas.json`) y `model/docs/shap_summary.png`.

### Fase 2: Persistencia SQLite y Núcleo del Backend (Días 1–2)
- [ ] Configurar `backend/config.py` (`pydantic-settings`) y `backend/db/database.py` (SQLAlchemy + SQLite).
- [ ] Crear modelos ORM en `backend/db/models.py` para `municipios`, `predicciones`, `alertas`, `clues`, `usuarios` y `sintomas` (restricción `UNIQUE` en `sintomas.id_local`).
- [ ] Implementar `backend/db/seed.py` para carga inicial de municipios, CLUES y predicciones base.
- [ ] Implementar `backend/core/geo.py` (Haversine), `backend/core/inference.py` (inferencia + `shap_top3`) y `backend/core/security.py` (verificación Firebase/JWT y dependencias RBAC).

### Fase 3: Endpoints REST, Auth y WebSockets en FastAPI (Días 2–4)
- [ ] Implementar esquemas Pydantic en `backend/schemas/`.
- [ ] Desarrollar routers en `backend/api/` (`system.py`, `auth.py`, `predictions.py`, `alerts.py`, `clues.py`, `symptoms.py`, `dashboard.py`) y registrarlos en `backend/main.py`.
- [ ] Implementar `backend/ws/manager.py` (`ConnectionManager`) para broadcast en vivo en `WS /ws/alerts` al ejecutar `POST /alerts`.
- [ ] Validar contrato completo en Swagger (`/docs`).

### Fase 4: Dashboard Web Epidemiológico en Streamlit (Días 2–5)
- [ ] Implementar `web/api_client.py` (único módulo autorizado a comunicarse con FastAPI vía HTTP/JWT y WebSocket) y `web/auth_ui.py`.
- [ ] Construir `web/app.py` y las páginas:
  - `web/pages/1_Mapa_Riesgo.py`: mapa de calor municipal con `folium`.
  - `web/pages/2_Predicciones.py`: curvas históricas y proyectadas + explicabilidad SHAP con `plotly express`.
  - `web/pages/3_Alertas.py`: emisión de alertas y recepción en vivo vía `websocket-client`.

### Fase 5: App Móvil Multiplataforma Offline-First en Flutter (Días 2–5)
- [ ] Implementar modelos (`prediccion.dart`, `alerta.dart`, `clue.dart`), `config.dart`, `api/api_client.dart` y `api/ws_client.dart`.
- [ ] Construir persistencia local SQLite en `local_db/database_helper.dart` y sincronización automática en `local_db/sync_service.dart` (`synced=false` -> `POST /symptoms`).
- [ ] Desarrollar flujo de autenticación en `auth/auth_service.dart` y `screens/login_screen.dart` diferenciando `home_paciente.dart` y `home_medico.dart`.
- [ ] Implementar `screens/mapa_clues.dart` (`geolocator` + `flutter_map`), `screens/seguimiento_sintomas.dart` (con disclaimer médico visible) y `screens/alertas_screen.dart`.

### Fase 6: Integración End-to-End, Despliegue y Documentación Final (Días 5–7)
- [ ] Desplegar backend en Render/Fly.io y dashboard en Streamlit Community Cloud; actualizar URLs en `mobile/lib/config.dart` y compilar `APK` final.
- [ ] Ejecutar pruebas end-to-end (alerta web -> push móvil -> búsqueda CLUES -> registro offline de síntomas -> sincronización).
- [ ] Completar `docs/arquitectura.png`, `docs/contrato_api.md`, `docs/normativa_mexico.md`, `docs/guion_demo.md` y `docs/video_demo.mp4`.

---

## 6. Matriz de Ejecución Paralela (7 Días — 3 Roles)

| Día | Data / Modelo ML | Backend FastAPI | Web Streamlit + Móvil Flutter |
| :--- | :--- | :--- | :--- |
| **Día 1** | Limpieza CSVs, EDA, definición de features | Esqueleto FastAPI + SQLite | Setup Flutter + Streamlit; diseño UI |
| **Día 2** | Entrenamiento RF + baseline + SHAP | Endpoints `/predict`, `/clues`, `/alerts` | Dashboard Streamlit con mapas; pantallas app |
| **Día 3** | Validación, métricas, matriz de confusión | WebSockets alertas + auth Firebase | Integración API en app; offline con SQLite |
| **Día 4** | Ajuste de hiperparámetros, congelar modelo | Endpoints auth roles | Auth en app (`paciente` vs `medico`); geolocalización |
| **Día 5** | Documentación del modelo (slides) | Deploy Render / Fly.io | Deploy Streamlit Cloud; APK de prueba |
| **Día 6** | Ensayo de demo, correcciones | Pruebas end-to-end | Pruebas offline, pulido UI |
| **Día 7** | Slides finales (5–8) + video demo | Último deploy | APK final + ensayo general |

---

## 7. Marco Normativo Mexicano (Referencia para App y Documentación)

- **LFPDPPP:** El prototipo opera con datos agregados y anonimizados; no almacena CURP ni nombres. Para producción se contempla aviso de privacidad, consentimiento expreso, principio de minimización y medidas de seguridad.
- **NOM-004-SSA3-2012 (Expediente Clínico):** La aplicación móvil se declara como **asistente orientador** y no como expediente clínico. Debe mostrar en interfaz el aviso: *"Esta aplicación no sustituye diagnóstico médico"*.
- **NOM-017-SSA2-2012 y Ley General de Salud:** Alineación metodológica con el Sistema Nacional de Vigilancia Epidemiológica (SINAVE) y coordinación institucional con la Secretaría de Salud Jalisco.

---

## 8. Arranque Rápido (3 Comandos)

```bash
# 1. Preparar datos y entrenar modelo reproducible
python scripts/limpieza.py && python model/train.py

# 2. Poblar base de datos inicial y levantar Backend FastAPI
python backend/db/seed.py && uvicorn backend.main:app --reload --port 8000

# 3. Levantar Dashboard Web Streamlit (en una segunda terminal)
streamlit run web/app.py
```

El dashboard se conecta al backend por defecto (`http://127.0.0.1:8000/api/v1`) y requiere iniciar sesión con un usuario creado en el backend. Puedes configurar otra URL mediante `API_BASE_URL`. Para abrir únicamente la demostración sintética, inicia Streamlit con `PROEVIRA_DEMO_MODE=true`.
