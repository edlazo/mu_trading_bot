# Mu Trading Bot

Mu Trading Bot is a FastAPI backend that scans technical trading opportunities, manages a configurable watchlist, sends Discord alerts, confirms pre-close decisions, and evaluates results with basic backtesting.

This is an educational and portfolio project. It does not execute trades automatically, it is not financial advice, and it does not guarantee profitability. The project is designed to demonstrate backend engineering, data processing, scheduling, testing, integrations, and API architecture.

## Key Features

- Modular FastAPI API with `APIRouter`.
- Configurable persistent watchlist.
- S&P 500 import and synchronization.
- Scanner batching with `limit` and `offset` for large watchlists.
- Technical indicators: SMA30, ASL21, EMA150, EMA200, RSI, PPO, support, and resistance.
- Risk/reward validation before creating operational alerts.
- Discord alerting through webhooks.
- Pre-close confirmation workflow for `COMPRAMOS` / `NO_COMPRAMOS` decisions.
- Scheduler with batch scanning and pre-close confirmation support.
- Basic backtesting for confirmed buy decisions.
- Dashboard summary endpoint.
- Maintenance tools for test data cleanup.
- Swagger organized by tags.
- Automated tests with pytest.

## Architecture

```text
mu_trading_bot/
  main.py
  app/
    main.py
    routes/
    core/
    services/
    models/
    schemas/
    integrations/
    database/
  tests/
  docs/
  examples/
```

- `main.py`: root ASGI entrypoint that imports `app.main:app`.
- `app/main.py`: FastAPI app creation, OpenAPI tags, router registration, startup lifespan, and scheduler integration.
- `app/routes/`: API layer, grouped by module with `APIRouter`.
- `app/services/`: application workflows such as scanning, confirmations, decisions, backtesting, dashboard summaries, and maintenance.
- `app/core/`: scanner support logic, indicators, risk rules, decision rules, market hours, and message builders.
- `app/integrations/`: external services such as Discord and TradingView webhook validation.
- `app/models/`: SQLAlchemy persistence models.
- `app/schemas/`: Pydantic schemas and enums.
- `app/database/`: SQLAlchemy engine, session, and base metadata.
- `tests/`: route, service, and core tests.
- `docs/`: project documentation.
- `examples/`: demo payloads and local API requests.

## API Modules

- System
- Dashboard
- Watchlist
- Scanner
- Alerts
- Confirmations
- Decisions
- Backtesting
- Scheduler
- Maintenance
- Webhooks

Swagger is available at `http://127.0.0.1:8000/docs` and is organized with these tags.

## Local Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

Local URLs:

- API: http://127.0.0.1:8000
- Swagger: http://127.0.0.1:8000/docs

## Environment Variables

Safe defaults are provided in `.env.example`:

```env
APP_NAME=Mu Trading Bot
ENVIRONMENT=local
DATABASE_URL=sqlite:///./mu_trading_bot.db
DISCORD_WEBHOOK_URL=
TRADINGVIEW_WEBHOOK_SECRET=change-me
ENABLE_SCHEDULER=false
SCHEDULER_INTERVAL_SECONDS=1200
SCANNER_BATCH_SIZE=50
```

Notes:

- `.env` is ignored and must not be committed.
- `DISCORD_WEBHOOK_URL` is private.
- `TRADINGVIEW_WEBHOOK_SECRET` protects the TradingView webhook.
- `ENABLE_SCHEDULER=true` starts the automatic scheduler loop.
- `SCANNER_BATCH_SIZE` controls how many enabled watchlist tickers the scheduler scans per run.

## Demo Flow

A complete local demo flow is documented in [docs/PORTFOLIO_DEMO.md](docs/PORTFOLIO_DEMO.md).

Quick version:

1. Start the API.
2. Open Swagger.
3. Import S&P 500 tickers.
4. Check `GET /dashboard/summary`.
5. Run a scanner batch with `POST /scanner/run-watchlist?allow_after_hours=true&debug=true&limit=10&offset=0`.
6. Check alerts.
7. Run `POST /scheduler/run-once`.
8. Use `POST /scheduler/run-once?force_pre_close=true` for demo/dev pre-close validation.
9. Check decisions.
10. Run basic backtesting.
11. Check backtesting summary.

`force_pre_close=true` is intended for local demo and development validation. It should not be used as a production trading signal shortcut.

## Development Commands

```bash
task test
```

Alternative:

```bash
python -m pytest
```

## Documentation

- [API examples](docs/API_EXAMPLES.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Portfolio demo](docs/PORTFOLIO_DEMO.md)
- [Screenshots checklist](docs/SCREENSHOTS.md)
- [Known limitations](docs/KNOWN_LIMITATIONS.md)
- [Disclaimer](docs/DISCLAIMER.md)
- [Versions](docs/VERSIONS.md)
- [Roadmap](docs/ROADMAP.md)
- [TradingView webhook setup](docs/tradingview-webhook.md)

## Safety Notes

- This project does not execute broker orders.
- This project is not financial advice.
- The user is responsible for their own investment decisions.
- Public market data can be delayed, incomplete, or unavailable.
- Backtesting is basic and does not fully model execution, slippage, fees, or liquidity.
- No result in this repository should be interpreted as a promise of profitability.

## License / Portfolio Use

This repository is prepared as a technical portfolio project. Before publishing, review local files and make sure `.env`, SQLite databases, private Discord webhook URLs, and any personal data are not included.