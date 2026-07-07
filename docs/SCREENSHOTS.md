# Screenshots Checklist

This file lists suggested screenshots for a public portfolio presentation. Do not include secrets, private webhook URLs, `.env` contents, personal messages, or private data.

Suggested folder:

```text
docs/assets/screenshots/
```

Suggested screenshots:

- `01-swagger-modules.png` - Swagger home with API modules expanded.
- `02-dashboard-summary.png` - `GET /dashboard/summary` response.
- `03-sp500-import.png` - `POST /watchlist/import-sp500` response.
- `04-scanner-batch.png` - Scanner batch response with `limit`, `offset`, `next_offset`, and `has_more`.
- `05-discord-alert-demo.png` - Discord alert example using fake/demo data only.
- `06-decisions.png` - `GET /decisions` response.
- `07-backtesting-summary.png` - `GET /backtests/summary` response.
- `08-scheduler-status.png` - `GET /scheduler/status` response.

Manual checklist:

- [ ] Hide browser bookmarks or private tabs.
- [ ] Hide terminal paths if they reveal personal information.
- [ ] Hide `.env` and all webhook URLs.
- [ ] Use demo tickers and non-sensitive data.
- [ ] Avoid financial performance claims in captions.