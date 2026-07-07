import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.core.market_hours import (
    USA_MARKET_HOURS,
    get_market_session_status,
    is_market_open,
    is_pre_close_window,
    is_weekday_market_day,
)
from app.models.decision import Decision
from app.schemas.alert import AlertStatus
from app.services.confirmation_service import run_pre_close_confirmation
from app.services.scanner_service import ScannerWatchlistResult, scan_watchlist
from app.services.watchlist_service import list_enabled_watchlist_tickers

ConfirmationRunner = Callable[[Session], Awaitable[list[Decision]]]
WatchlistScannerRunner = Callable[[Session], Awaitable[ScannerWatchlistResult]]

last_confirmation_date: Optional[date] = None
last_confirmation_at: Optional[datetime] = None
last_confirmation_result: Optional[dict] = None
is_running: bool = False
is_scan_running: bool = False
scanner_batch_offset: int = 0
last_run_at: Optional[datetime] = None
last_result: Optional[dict] = None


def _batch_metadata(total_enabled: int, batch_size: Optional[int], offset: int) -> dict:
    if batch_size is None:
        return {
            "total_enabled": total_enabled,
            "limit": None,
            "offset": 0,
            "next_offset": None,
            "has_more": False,
        }

    next_offset = offset + batch_size
    has_more = next_offset < total_enabled
    return {
        "total_enabled": total_enabled,
        "limit": batch_size,
        "offset": offset,
        "next_offset": next_offset if has_more else None,
        "has_more": has_more,
    }


def _select_ticker_batch(tickers: list[str], batch_size: Optional[int], offset: int) -> tuple[list[str], dict, int]:
    total_enabled = len(tickers)
    if batch_size is None:
        return tickers, _batch_metadata(total_enabled, None, 0), 0

    if total_enabled == 0:
        return [], _batch_metadata(0, batch_size, 0), 0

    safe_offset = offset if offset < total_enabled else 0
    selected = tickers[safe_offset : safe_offset + batch_size]
    metadata = _batch_metadata(total_enabled, batch_size, safe_offset)
    next_offset = metadata["next_offset"] if metadata["has_more"] else 0
    return selected, metadata, next_offset


def _result_payload(result: ScannerWatchlistResult, batch_metadata: Optional[dict] = None) -> dict:
    payload = {
        "status": "scanner_completed",
        "scanned": result.scanned,
        "created_alerts": len(result.created_alerts),
        "created_tickers": result.created_tickers,
    }
    if batch_metadata:
        payload.update(batch_metadata)
    return payload


def get_scheduler_status(
    enabled: bool,
    interval_seconds: int,
    scanner_batch_size: Optional[int] = None,
    current_datetime: Optional[datetime] = None,
) -> dict:
    now = current_datetime or datetime.now(UTC)
    return {
        "enabled": enabled,
        "interval_seconds": interval_seconds,
        "is_running": is_running,
        "last_run_at": last_run_at.isoformat() if last_run_at else None,
        "last_result": last_result,
        "last_confirmation_at": last_confirmation_at.isoformat() if last_confirmation_at else None,
        "last_confirmation_result": last_confirmation_result,
        "last_confirmation_date": last_confirmation_date.isoformat() if last_confirmation_date else None,
        "last_pre_close_run_at": last_confirmation_at.isoformat() if last_confirmation_at else None,
        "last_pre_close_result": last_confirmation_result,
        "scanner_batch_size": scanner_batch_size,
        "scanner_next_offset": scanner_batch_offset,
        "is_pre_close_window": is_pre_close_window(now),
    }


def _confirmation_result_payload(decisions: list[Decision], already_decided: int = 0) -> dict:
    confirmed = sum(1 for decision in decisions if decision.decision == "COMPRAMOS")
    rejected = sum(1 for decision in decisions if decision.decision == "NO_COMPRAMOS")
    return {
        "status": "pre_close_confirmation_completed",
        "confirmed": confirmed,
        "rejected": rejected,
        "already_decided": already_decided,
        "decisions_created": len(decisions),
        "decisions": [
            {
                "ticker": decision.ticker,
                "decision": decision.decision,
                "score": decision.final_score,
                "risk": decision.final_risk,
                "reason": decision.reason,
            }
            for decision in decisions
        ],
    }


async def run_scheduled_pre_close_confirmation(
    db: Session,
    confirmation_runner: ConfirmationRunner = run_pre_close_confirmation,
) -> list[Decision]:
    return await confirmation_runner(db)


async def run_scheduled_watchlist_scanner(
    db: Session,
    watchlist_scanner_runner: Optional[WatchlistScannerRunner] = None,
    scanner_batch_size: Optional[int] = None,
) -> ScannerWatchlistResult:
    global scanner_batch_offset

    if watchlist_scanner_runner is not None:
        return await watchlist_scanner_runner(db)

    all_tickers = [item.ticker for item in list_enabled_watchlist_tickers(db)]
    selected_tickers, _metadata, next_offset = _select_ticker_batch(all_tickers, scanner_batch_size, scanner_batch_offset)
    scanner_batch_offset = next_offset
    return await scan_watchlist(
        db,
        selected_tickers,
        alert_status=AlertStatus.EN_OBSERVACION,
        watchlist=False,
    )


async def run_scheduled_pre_close_if_due(
    db_session_factory,
    current_datetime: Optional[datetime] = None,
    confirmation_runner: ConfirmationRunner = run_pre_close_confirmation,
    force: bool = False,
) -> dict:
    global last_confirmation_date, last_confirmation_at, last_confirmation_result, last_run_at, last_result

    now = current_datetime or datetime.now(UTC)
    market_datetime = now.astimezone(USA_MARKET_HOURS.timezone)
    market_date = market_datetime.date()

    if not force and not is_pre_close_window(market_datetime):
        print("Scheduler pre-close skipped: outside window")
        return {"status": "pre_close_skipped", "reason": "outside_window"}

    print("Scheduler force pre-close requested" if force else "Scheduler detected pre-close window")
    if last_confirmation_date == market_date:
        print("Scheduler pre-close skipped: already executed for this market date")
        return {
            "status": "pre_close_already_ran",
            "market_date": market_date.isoformat(),
            "last_pre_close_result": last_confirmation_result,
        }

    db = db_session_factory()
    try:
        print("Scheduler running pre-close confirmations")
        decisions = await run_scheduled_pre_close_confirmation(db, confirmation_runner)
        last_confirmation_at = now
        last_confirmation_date = market_date
        last_confirmation_result = _confirmation_result_payload(decisions)
        last_run_at = now
        last_result = last_confirmation_result
        print(
            "Scheduler pre-close completed: "
            f"decisions_created={last_confirmation_result['decisions_created']}"
        )
        return last_confirmation_result
    except Exception as exc:
        last_confirmation_at = now
        last_confirmation_result = {"status": "error", "error": str(exc)}
        last_run_at = now
        last_result = last_confirmation_result
        print(f"Scheduler confirmation error: {exc}")
        return last_confirmation_result
    finally:
        db.close()


async def run_scheduled_watchlist_scan(
    db_session_factory,
    current_datetime: Optional[datetime] = None,
    watchlist_scanner_runner: Optional[WatchlistScannerRunner] = None,
    scanner_batch_size: Optional[int] = None,
) -> dict:
    global is_scan_running, last_run_at, last_result, scanner_batch_offset

    if is_scan_running:
        last_result = {"status": "skipped", "reason": "scan_already_running"}
        print("Scheduler scan skipped: scan already running")
        return last_result

    now = current_datetime or datetime.now(UTC)
    session_status = get_market_session_status(now)
    print(f"Market session status: {session_status}")

    if not is_market_open(now):
        last_run_at = now
        last_result = {
            "status": "market_closed",
            "session_status": session_status,
            "scanned": 0,
            "created_alerts": 0,
            "created_tickers": [],
        }
        print("Scheduler scan skipped: market closed")
        return last_result

    is_scan_running = True
    db = db_session_factory()
    try:
        batch_metadata = None
        if watchlist_scanner_runner is not None:
            result = await watchlist_scanner_runner(db)
        else:
            all_tickers = [item.ticker for item in list_enabled_watchlist_tickers(db)]
            selected_tickers, batch_metadata, next_offset = _select_ticker_batch(
                all_tickers,
                scanner_batch_size,
                scanner_batch_offset,
            )
            print(f"Scheduler running scanner batch offset={batch_metadata['offset'] if batch_metadata else 0}")
            scanner_batch_offset = next_offset
            result = await scan_watchlist(
                db,
                selected_tickers,
                alert_status=AlertStatus.EN_OBSERVACION,
                watchlist=False,
            )
        last_run_at = now
        last_result = _result_payload(result, batch_metadata=batch_metadata)
        print(
            "Scheduler scan completed: "
            f"scanned={last_result['scanned']} "
            f"created_alerts={last_result['created_alerts']} "
            f"created_tickers={last_result['created_tickers']}"
        )
        return last_result
    except Exception as exc:
        last_run_at = now
        last_result = {"status": "error", "error": str(exc)}
        print(f"Scheduler error: {exc}")
        return last_result
    finally:
        db.close()
        is_scan_running = False


async def run_scheduler_once(
    db_session_factory,
    current_datetime: Optional[datetime] = None,
    confirmation_runner: ConfirmationRunner = run_pre_close_confirmation,
    watchlist_scanner_runner: Optional[WatchlistScannerRunner] = None,
    scanner_batch_size: Optional[int] = None,
    force_pre_close: bool = False,
) -> dict:
    now = current_datetime or datetime.now(UTC)
    market_datetime = now.astimezone(USA_MARKET_HOURS.timezone)

    if force_pre_close or (is_weekday_market_day(market_datetime) and is_pre_close_window(market_datetime)):
        return await run_scheduled_pre_close_if_due(
            db_session_factory,
            current_datetime=now,
            confirmation_runner=confirmation_runner,
            force=force_pre_close,
        )

    print("Scheduler pre-close skipped: outside window")
    return await run_scheduled_watchlist_scan(
        db_session_factory,
        current_datetime=now,
        watchlist_scanner_runner=watchlist_scanner_runner,
        scanner_batch_size=scanner_batch_size,
    )


async def run_scheduler_check(
    db_session_factory,
    current_datetime: Optional[datetime] = None,
    confirmation_runner: ConfirmationRunner = run_pre_close_confirmation,
    watchlist_scanner_runner: Optional[WatchlistScannerRunner] = None,
    scanner_batch_size: Optional[int] = None,
) -> bool:
    result = await run_scheduler_once(
        db_session_factory,
        current_datetime=current_datetime,
        confirmation_runner=confirmation_runner,
        watchlist_scanner_runner=watchlist_scanner_runner,
        scanner_batch_size=scanner_batch_size,
    )
    return result.get("status") != "pre_close_skipped"


async def scheduler_loop(db_session_factory, interval_seconds: int = 300, scanner_batch_size: Optional[int] = None) -> None:
    global is_running
    is_running = True
    print("Scheduler started")
    try:
        while True:
            try:
                await run_scheduler_once(
                    db_session_factory,
                    datetime.now(UTC),
                    scanner_batch_size=scanner_batch_size,
                )
            except Exception as exc:
                print(f"Scheduler error: {exc}")
            await asyncio.sleep(interval_seconds)
    finally:
        is_running = False