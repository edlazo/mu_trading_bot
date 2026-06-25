from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.sp500 import SP500ImportResponse, SP500SyncResponse, SP500TickerListResponse
from app.schemas.watchlist import WatchlistTickerCreate, WatchlistTickerResponse, WatchlistTickerUpdate
from app.services.sp500_service import fetch_sp500_tickers, import_sp500_to_watchlist, sync_sp500_watchlist
from app.services.watchlist_service import (
    create_watchlist_ticker,
    disable_watchlist_ticker,
    get_watchlist_ticker,
    list_watchlist_tickers,
    seed_default_watchlist,
    update_watchlist_ticker,
)

router = APIRouter(prefix="/watchlist", tags=["Watchlist"])


@router.get("", response_model=list[WatchlistTickerResponse], summary="Get watchlist")
def get_watchlist(db: Session = Depends(get_db)) -> list:
    return list_watchlist_tickers(db)


@router.post("", response_model=WatchlistTickerResponse, status_code=status.HTTP_201_CREATED, summary="Add watchlist ticker")
def add_watchlist_ticker(
    payload: WatchlistTickerCreate,
    db: Session = Depends(get_db),
):
    existing = get_watchlist_ticker(db, payload.ticker, payload.market)
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ticker already exists in watchlist")
    return create_watchlist_ticker(db, payload)


@router.post("/seed-defaults", summary="Seed default watchlist")
def seed_watchlist_defaults(db: Session = Depends(get_db)) -> dict:
    created = seed_default_watchlist(db)
    return {
        "status": "watchlist_seeded",
        "created": len(created),
        "tickers": [item.ticker for item in created],
    }



@router.get("/sp500", response_model=SP500TickerListResponse, summary="Get S&P 500 tickers")
def get_sp500_tickers() -> SP500TickerListResponse:
    tickers = fetch_sp500_tickers()
    return SP500TickerListResponse(source="sp500", count=len(tickers), tickers=tickers)


@router.post("/import-sp500", response_model=SP500ImportResponse, summary="Import S&P 500 to watchlist")
def import_sp500_watchlist(
    enabled: bool = True,
    notes: str = "S&P 500",
    db: Session = Depends(get_db),
) -> SP500ImportResponse:
    return SP500ImportResponse.model_validate(
        import_sp500_to_watchlist(db, enabled=enabled, notes=notes)
    )


@router.post("/sync-sp500", response_model=SP500SyncResponse, summary="Sync S&P 500 watchlist")
def sync_sp500_watchlist_endpoint(
    enabled: bool = True,
    disable_removed: bool = False,
    db: Session = Depends(get_db),
) -> SP500SyncResponse:
    return SP500SyncResponse.model_validate(
        sync_sp500_watchlist(db, enabled=enabled, disable_removed=disable_removed)
    )


@router.patch("/{ticker}", response_model=WatchlistTickerResponse, summary="Update watchlist ticker")
def patch_watchlist_ticker(
    ticker: str,
    payload: WatchlistTickerUpdate,
    db: Session = Depends(get_db),
):
    item = get_watchlist_ticker(db, ticker)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watchlist ticker not found")
    return update_watchlist_ticker(db, item, payload)


@router.delete("/{ticker}", response_model=WatchlistTickerResponse, summary="Disable watchlist ticker")
def delete_watchlist_ticker(
    ticker: str,
    db: Session = Depends(get_db),
):
    item = get_watchlist_ticker(db, ticker)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watchlist ticker not found")
    return disable_watchlist_ticker(db, item)