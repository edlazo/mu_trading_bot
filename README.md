# Mu Trading Bot

## Descripcion

Mu Trading Bot es una API backend para escanear oportunidades tecnicas de trading, crear alertas, confirmar decisiones pre-cierre y evaluar resultados mediante backtesting basico.

El sistema esta pensado como herramienta educativa, de soporte de decision y portfolio tecnico. No compra ni vende automaticamente, no opera cuentas reales y no debe interpretarse como asesoramiento financiero. La decision final de ejecutar una operacion siempre queda en manos del usuario.

## Features

- Watchlist configurable y persistente.
- Scanner tecnico con filtros operativos.
- Validacion de relacion riesgo/beneficio.
- Alertas `EN_OBSERVACION` durante mercado abierto.
- Alertas `WATCHLIST` fuera de horario cuando se permite `allow_after_hours=true`.
- Confirmaciones pre-cierre con decision `COMPRAMOS` / `NO_COMPRAMOS`.
- Integracion con Discord Webhooks.
- Webhook compatible con TradingView y Postman.
- Scheduler automatico opcional.
- Backtesting basico para decisiones `COMPRAMOS`.
- Dashboard summary centralizado.
- Maintenance tools para datos de prueba.
- Swagger organizado por modulos/tags.
- Tests automatizados con pytest.
- Rutas organizadas con `APIRouter` en `app/routes/`.

## Stack

- Python
- FastAPI
- SQLAlchemy
- SQLite
- Pydantic / Pydantic Settings
- yfinance
- pandas
- numpy
- httpx
- pytest
- Discord Webhooks

## Arquitectura

```text
mu_trading_bot/
  main.py                  Entrypoint raiz: from app.main import app
  app/
    __init__.py
    main.py                Configuracion FastAPI, lifespan, routers y OpenAPI tags
    routes/                Endpoints FastAPI por modulo
    core/                  Indicadores, riesgo, decision y horarios de mercado
    database/              Engine, sesiones y base SQLAlchemy
    integrations/          Discord y validacion TradingView
    models/                Modelos SQLAlchemy
    schemas/               Schemas Pydantic
    services/              Logica de aplicacion
  tests/
    routes/                Tests de endpoints
    services/              Tests de servicios
    core/                  Tests de logica pura
    conftest.py
  docs/                    Documentacion adicional
  examples/                Payloads de ejemplo
```

`main.py` raiz permite correr la API como `main:app`, mientras que `app.main:app` sigue funcionando para compatibilidad.

## Variables de entorno

Copiar `.env.example` a `.env` para desarrollo local:

```bash
cp .env.example .env
```

Variables disponibles:

```env
APP_NAME=Mu Trading Bot
ENVIRONMENT=local
DATABASE_URL=sqlite:///./mu_trading_bot.db
DISCORD_WEBHOOK_URL=
TRADINGVIEW_WEBHOOK_SECRET=change-me
ENABLE_SCHEDULER=false
SCHEDULER_INTERVAL_SECONDS=1200
```

Notas:

- `.env` no se sube al repo.
- `DISCORD_WEBHOOK_URL` es privado.
- `TRADINGVIEW_WEBHOOK_SECRET` protege el webhook de TradingView/Postman.
- `ENABLE_SCHEDULER=true` activa el loop automatico al iniciar FastAPI.
- `SCHEDULER_INTERVAL_SECONDS=1200` equivale a 20 minutos.

## Instalacion local

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## Ejecutar API

Comando recomendado:

```bash
.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

Comando compatible:

```bash
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

URLs:

- API: http://127.0.0.1:8000
- Swagger: http://127.0.0.1:8000/docs

## Ejecutar tests

```bash
task test
```

Alternativa:

```bash
python -m pytest
```

## Flujo principal

1. Cargar o sembrar la watchlist.
2. Ejecutar el scanner manual o automaticamente.
3. Si el mercado esta cerrado y `allow_after_hours=true`, el bot puede crear `WATCHLIST` solo si hay R/R valido.
4. Si el mercado esta abierto, el scanner puede crear alertas `EN_OBSERVACION`.
5. En pre-cierre, el bot confirma alertas activas.
6. La confirmacion crea decisiones `COMPRAMOS` / `NO_COMPRAMOS`.
7. El backtesting evalua decisiones `COMPRAMOS` contra precios posteriores.
8. El dashboard resume el estado general.
9. Maintenance permite revisar y limpiar datos de prueba `TEST_`.

## Endpoints principales

### System

- `GET /`

### Dashboard

- `GET /dashboard/summary`

### Watchlist

- `GET /watchlist`
- `POST /watchlist`
- `PATCH /watchlist/{ticker}`
- `DELETE /watchlist/{ticker}`
- `POST /watchlist/seed-defaults`

### Scanner

- `POST /scanner/run`
- `POST /scanner/run-watchlist`

### Alerts

- `GET /alerts/active`
- `GET /alerts/watchlist`
- `GET /alerts/archived`
- `PATCH /alerts/{alert_id}/archive`
- `POST /alerts/archive-watchlist`
- `POST /alerts/archive-test-alerts`

### Confirmations

- `POST /confirmations/pre-close`
- `POST /confirmations/pre-close/{alert_id}`

### Decisions

- `GET /decisions`
- `GET /decisions/summary`
- `GET /decisions/{decision_id}`
- `GET /decisions/by-ticker/{ticker}`

### Backtesting

- `GET /backtests`
- `GET /backtests/summary`
- `POST /backtests/run`
- `POST /backtests/decisions/{decision_id}`

### Scheduler

- `GET /scheduler/status`
- `POST /scheduler/run-once`

### Maintenance

- `GET /maintenance/test-data/summary`
- `POST /maintenance/cleanup-test-data`

### Webhooks

- `POST /webhooks/tradingview`
- `POST /webhooks/test-discord`

## Ejemplos de uso

### 1. Seed watchlist

```bash
curl -X POST http://127.0.0.1:8000/watchlist/seed-defaults
```

### 2. Run scanner watchlist fuera de horario

```bash
curl -X POST "http://127.0.0.1:8000/scanner/run-watchlist?allow_after_hours=true&debug=true"
```

### 3. Get active alerts

```bash
curl http://127.0.0.1:8000/alerts/active
```

### 4. Pre-close confirmation

```bash
curl -X POST http://127.0.0.1:8000/confirmations/pre-close
```

### 5. Run backtesting

```bash
curl -X POST "http://127.0.0.1:8000/backtests/run?days=10"
```

### 6. Get dashboard summary

```bash
curl http://127.0.0.1:8000/dashboard/summary
```

### 7. Maintenance dry run

```bash
curl -X POST "http://127.0.0.1:8000/maintenance/cleanup-test-data?dry_run=true"
```

Mas ejemplos en [docs/API_EXAMPLES.md](docs/API_EXAMPLES.md).

## Estados y decisiones

Alert status principales:

- `EN_OBSERVACION`: alerta operativa activa pendiente de confirmacion.
- `WATCHLIST`: oportunidad fuera de horario, no operativa.
- `ARCHIVED`: alerta archivada.
- `COMPRAMOS`: alerta confirmada positivamente.
- `NO_COMPRAMOS`: alerta rechazada.

Decision:

- `COMPRAMOS`
- `NO_COMPRAMOS`

Backtesting result:

- `TARGET_HIT`
- `STOP_HIT`
- `NO_RESULT`
- `AMBIGUOUS`
- `ERROR`

## Scheduler

- `ENABLE_SCHEDULER=true` activa el loop automatico.
- `SCHEDULER_INTERVAL_SECONDS=1200` equivale a 20 minutos.
- `is_running=true` significa que el loop automatico esta activo.
- Mercado cerrado no apaga el scheduler; solo hace que esa corrida no cree alertas operativas.
- `POST /scheduler/run-once` ejecuta una corrida manual aunque el scheduler automatico este apagado.

## Seguridad

- No subir `.env`.
- No subir bases SQLite (`*.db`, `*.sqlite`, `*.sqlite3`).
- No compartir `DISCORD_WEBHOOK_URL`.
- No compartir `TRADINGVIEW_WEBHOOK_SECRET`.
- Usar secretos distintos por entorno.

## Roadmap

- v0.1.0 - Scanner + watchlist + decisiones.
- v0.2.0 - Backtesting basico.
- v0.3.0 - Dashboard summary + scheduler corregido.
- v0.4.0 - Maintenance tools.
- v0.5.0 - Documentacion y demo portfolio.

Proximos pasos:

- Deploy demo.
- Dashboard web frontend.
- Metricas avanzadas.
- Backtesting con comisiones/slippage.
- Reportes exportables.
- Mejor soporte para feriados USA y half-days.