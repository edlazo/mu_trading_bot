from io import StringIO

import httpx
import pandas as pd
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.watchlist import WatchlistTicker

SP500_SOURCE = "sp500"
SP500_DEFAULT_NOTES = "S&P 500"
SP500_WIKIPEDIA_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


def normalize_yfinance_ticker(ticker: str) -> str:
    return ticker.strip().upper().replace(".", "-")


def fetch_sp500_tickers() -> list[str]:
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; MuTradingBot/1.0; +https://github.com/)",
    }

    try:
        response = httpx.get(
            SP500_WIKIPEDIA_URL,
            headers=headers,
            timeout=20,
            follow_redirects=True,
        )
        response.raise_for_status()
        tables = pd.read_html(StringIO(response.text))
    except Exception as exc:
        raise RuntimeError(f"Could not fetch S&P 500 tickers: {exc}") from exc

    for table in tables:
        if "Symbol" not in table.columns:
            continue
        tickers = {
            normalize_yfinance_ticker(str(value))
            for value in table["Symbol"].dropna().tolist()
            if str(value).strip()
        }
        if tickers:
            return sorted(tickers)

    raise RuntimeError("Could not find S&P 500 symbols table")


def _get_watchlist_ticker(db: Session, ticker: str) -> WatchlistTicker | None:
    return (
        db.query(WatchlistTicker)
        .filter(func.upper(WatchlistTicker.ticker) == ticker.upper())
        .filter(func.upper(WatchlistTicker.market) == "USA")
        .first()
    )


def _upsert_sp500_tickers(db: Session, tickers: list[str], enabled: bool, notes: str) -> tuple[int, int, int]:
    created = 0
    updated = 0
    skipped = 0

    for ticker in tickers:
        item = _get_watchlist_ticker(db, ticker)
        if item is None:
            db.add(WatchlistTicker(ticker=ticker, market="USA", enabled=enabled, notes=notes))
            created += 1
            continue

        item.enabled = enabled if enabled else item.enabled
        item.notes = notes
        db.add(item)
        updated += 1

    db.commit()
    return created, updated, skipped


def import_sp500_to_watchlist(db: Session, enabled: bool = True, notes: str = SP500_DEFAULT_NOTES) -> dict:
    tickers = fetch_sp500_tickers()
    created, updated, skipped = _upsert_sp500_tickers(db, tickers, enabled=enabled, notes=notes)
    return {
        "source": SP500_SOURCE,
        "fetched": len(tickers),
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "enabled": enabled,
    }


def _is_sp500_watchlist_item(item: WatchlistTicker) -> bool:
    notes = (item.notes or "").upper()
    return "S&P 500" in notes or "SP500" in notes or "S AND P 500" in notes


def sync_sp500_watchlist(db: Session, enabled: bool = True, disable_removed: bool = False) -> dict:
    tickers = fetch_sp500_tickers()
    created, updated, _skipped = _upsert_sp500_tickers(db, tickers, enabled=enabled, notes=SP500_DEFAULT_NOTES)
    disabled_removed = 0

    if disable_removed:
        current = set(tickers)
        items = db.query(WatchlistTicker).filter(func.upper(WatchlistTicker.market) == "USA").all()
        for item in items:
            if item.ticker.upper() in current:
                continue
            if not item.enabled:
                continue
            if not _is_sp500_watchlist_item(item):
                continue
            item.enabled = False
            db.add(item)
            disabled_removed += 1
        db.commit()

    return {
        "source": SP500_SOURCE,
        "fetched": len(tickers),
        "created": created,
        "updated": updated,
        "disabled_removed": disabled_removed,
        "enabled": enabled,
    }