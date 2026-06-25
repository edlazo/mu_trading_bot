# API Examples - Mu Trading Bot

Base URL local:

```text
http://127.0.0.1:8000
```

## Seed watchlist

```bash
curl -X POST http://127.0.0.1:8000/watchlist/seed-defaults
```

## Run scanner manual

```bash
curl -X POST http://127.0.0.1:8000/scanner/run \
  -H "Content-Type: application/json" \
  -d '{"tickers":["AAPL","MSFT","NVDA"]}'
```

## Run scanner watchlist after hours

```bash
curl -X POST "http://127.0.0.1:8000/scanner/run-watchlist?allow_after_hours=true&debug=true"
```

## Get dashboard summary

```bash
curl http://127.0.0.1:8000/dashboard/summary
```

## Run pre-close confirmation

```bash
curl -X POST http://127.0.0.1:8000/confirmations/pre-close
```

## Run backtesting

```bash
curl -X POST "http://127.0.0.1:8000/backtests/run?days=10"
```

## Maintenance dry run

```bash
curl -X POST "http://127.0.0.1:8000/maintenance/cleanup-test-data?dry_run=true"
```

## TradingView webhook using query secret

```bash
curl -X POST "http://127.0.0.1:8000/webhooks/tradingview?secret=change-me" \
  -H "Content-Type: application/json" \
  --data @examples/tradingview_webhook_payload.json
```

## TradingView webhook using header secret

```bash
curl -X POST http://127.0.0.1:8000/webhooks/tradingview \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Secret: change-me" \
  --data @examples/tradingview_webhook_payload.json
```