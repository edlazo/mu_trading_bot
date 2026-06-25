from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.watchlist import WatchlistTicker
from app.schemas.watchlist import WatchlistTickerCreate, WatchlistTickerUpdate

DEFAULT_WATCHLIST_TICKERS = [
    "AAPL",
    "MSFT",
    "NVDA",
    "TSLA",
    "META",
    "AMZN",
    "GOOGL",
    "AMD",
    "NFLX",
    "SPY",
    "QQQ",
    "IWM",
    "MELI",
    "YPF",
    "GGAL",
    "BMA",
    "PAM",
]


def normalize_ticker(value: str) -> str:
    return value.strip().upper()


def normalize_market(value: str = "USA") -> str:
    return value.strip().upper()


def list_watchlist_tickers(db: Session) -> list[WatchlistTicker]:
    return db.query(WatchlistTicker).order_by(WatchlistTicker.ticker.asc()).all()


def list_enabled_watchlist_tickers(db: Session) -> list[WatchlistTicker]:
    return (
        db.query(WatchlistTicker)
        .filter(WatchlistTicker.enabled.is_(True))
        .order_by(WatchlistTicker.ticker.asc())
        .all()
    )


def get_watchlist_ticker(db: Session, ticker: str, market: str = "USA") -> WatchlistTicker | None:
    normalized_ticker = normalize_ticker(ticker)
    normalized_market = normalize_market(market)
    return (
        db.query(WatchlistTicker)
        .filter(func.upper(WatchlistTicker.ticker) == normalized_ticker)
        .filter(func.upper(WatchlistTicker.market) == normalized_market)
        .first()
    )


def create_watchlist_ticker(db: Session, payload: WatchlistTickerCreate) -> WatchlistTicker:
    item = WatchlistTicker(
        ticker=normalize_ticker(payload.ticker),
        market=normalize_market(payload.market),
        notes=payload.notes,
        enabled=True,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def update_watchlist_ticker(db: Session, item: WatchlistTicker, payload: WatchlistTickerUpdate) -> WatchlistTicker:
    update_data = payload.model_dump(exclude_unset=True)
    if "enabled" in update_data:
        item.enabled = update_data["enabled"]
    if "notes" in update_data:
        item.notes = update_data["notes"]
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def disable_watchlist_ticker(db: Session, item: WatchlistTicker) -> WatchlistTicker:
    item.enabled = False
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def seed_default_watchlist(db: Session) -> list[WatchlistTicker]:
    created: list[WatchlistTicker] = []
    for ticker in DEFAULT_WATCHLIST_TICKERS:
        if get_watchlist_ticker(db, ticker) is not None:
            continue
        item = WatchlistTicker(ticker=ticker, market="USA", enabled=True)
        db.add(item)
        created.append(item)
    db.commit()
    for item in created:
        db.refresh(item)
    return created
