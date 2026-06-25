# Architecture - Mu Trading Bot

Mu Trading Bot is organized as a modular FastAPI backend. The project separates route declarations, application services, domain logic, persistence models, schemas and external integrations.

## Entrypoints

```text
main.py
```

Root entrypoint used by the recommended command:

```bash
.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

It only imports the FastAPI app from `app.main`.

```text
app/main.py
```

Creates the FastAPI instance, defines OpenAPI tags, registers routers and owns the lifespan logic for the scheduler. The previous command still works:

```bash
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

## Routes

```text
app/routes/
```

Each module owns one API section using `APIRouter`:

- `system_routes.py`
- `dashboard_routes.py`
- `watchlist_routes.py`
- `scanner_routes.py`
- `alerts_routes.py`
- `confirmations_routes.py`
- `decisions_routes.py`
- `backtests_routes.py`
- `scheduler_routes.py`
- `maintenance_routes.py`
- `webhooks_routes.py`

`app/routes/__init__.py` centralizes router imports for `app.main`.

## Services

```text
app/services/
```

Application workflows live here. Services coordinate database access, scanner execution, confirmations, decisions, dashboard summaries, maintenance cleanup and backtesting.

## Core

```text
app/core/
```

Pure or mostly pure domain logic:

- Indicators.
- Risk scoring.
- Decision rules.
- Message building.
- Market hours.

## Models

```text
app/models/
```

SQLAlchemy models for alerts, decisions, backtest results and watchlist tickers.

## Schemas

```text
app/schemas/
```

Pydantic schemas and enums used by request/response models and internal contracts.

## Integrations

```text
app/integrations/
```

External integrations such as Discord Webhooks and TradingView webhook validation.

## Scanner flow

1. The scanner receives tickers from a request or persistent watchlist.
2. It fetches data with `yfinance`.
3. It computes indicators and technical conditions.
4. It validates operational structure and R/R.
5. It creates `EN_OBSERVACION` during market hours or `WATCHLIST` after hours when explicitly allowed.

## Confirmation flow

1. Active alerts are stored as `EN_OBSERVACION`.
2. Pre-close confirmation reevaluates active alerts.
3. It creates decisions: `COMPRAMOS` or `NO_COMPRAMOS`.
4. The alert leaves the active state so it is not confirmed twice.

## Backtesting flow

1. Backtesting only evaluates `COMPRAMOS` decisions.
2. It downloads later price data with `yfinance`.
3. It checks whether target or stop was reached first.
4. It stores `TARGET_HIT`, `STOP_HIT`, `NO_RESULT`, `AMBIGUOUS` or `ERROR`.

## Scheduler flow

1. `ENABLE_SCHEDULER=true` starts the automatic loop at FastAPI startup.
2. The loop checks market status repeatedly.
3. During market hours, it scans the watchlist.
4. Around pre-close time, it confirms active alerts.
5. Market closed does not stop the loop; it only prevents operational alert creation.

## No automatic trading

The bot never sends broker orders. It only creates alerts, decisions and backtesting records. The final trade execution decision belongs to the user.