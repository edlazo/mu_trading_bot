from datetime import UTC, datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.market_hours import get_market_session_status, is_market_open
from app.database.session import get_db
from app.schemas.alert import AlertStatus
from app.schemas.scanner import ScannerRequest, ScannerResponse
from app.services.scanner_service import scan_watchlist
from app.services.watchlist_service import list_enabled_watchlist_tickers

router = APIRouter(prefix="/scanner", tags=["Scanner"])


def _batch_metadata(total_enabled: int, limit: Optional[int], offset: int) -> dict:
    return {
        "total_enabled": total_enabled,
        "limit": limit,
        "offset": offset if limit is not None else 0,
        "next_offset": None,
        "has_more": False,
    }


def _batch_metadata_for_scanned(batch_metadata: dict, scanned: int) -> dict:
    metadata = dict(batch_metadata)
    has_more = metadata["offset"] + scanned < metadata["total_enabled"]
    metadata["has_more"] = has_more
    metadata["next_offset"] = metadata["offset"] + scanned if has_more else None
    return metadata


def _slice_tickers(tickers: list[str], limit: Optional[int], offset: int) -> list[str]:
    if limit is None:
        return tickers
    return tickers[offset : offset + limit]


def _scanner_payload_from_result(
    result,
    debug: bool,
    session_status: Optional[str] = None,
    batch_metadata: Optional[dict] = None,
) -> ScannerResponse:
    skipped = []
    for item in result.skipped:
        payload = {"ticker": item.ticker, "status": item.status, "reason": item.reason}
        if debug and item.debug is not None:
            payload["debug"] = item.debug
        skipped.append(payload)

    created = None
    if debug:
        created = [
            {
                "ticker": item.ticker,
                "status": item.status,
                "reason": item.reason,
                "debug": item.debug,
            }
            for item in result.created_debug
        ]

    created_active_alerts = sum(1 for alert in result.created_alerts if getattr(alert, "status", None) == AlertStatus.EN_OBSERVACION.value)
    created_watchlist = sum(1 for alert in result.created_alerts if getattr(alert, "status", None) == AlertStatus.WATCHLIST.value)
    payload = ScannerResponse(
        status="scanner_completed",
        session_status=session_status,
        scanned=result.scanned,
        created_alerts=len(result.created_alerts),
        created_active_alerts=created_active_alerts,
        created_watchlist=created_watchlist,
        created_tickers=result.created_tickers,
        skipped=skipped,
        created=created,
    )
    if batch_metadata:
        for key, value in _batch_metadata_for_scanned(batch_metadata, result.scanned).items():
            setattr(payload, key, value)
    return payload


async def _run_scanner_for_tickers(
    tickers: list[str],
    allow_after_hours: bool,
    debug: bool,
    force_alert: bool,
    db: Session,
    batch_metadata: Optional[dict] = None,
) -> ScannerResponse:
    current_datetime = datetime.now(UTC)
    session_status = get_market_session_status(current_datetime)
    market_open = is_market_open(current_datetime)

    if not market_open and not allow_after_hours:
        return ScannerResponse(
            status="market_closed",
            session_status=session_status,
            scanned=len(tickers),
            created_alerts=0,
            created_active_alerts=0,
            created_watchlist=0,
            created_tickers=[],
            skipped=[],
            message="Mercado cerrado. Ejecutar scanner en horario de mercado o usar allow_after_hours=true para watchlist.",
            **(_batch_metadata_for_scanned(batch_metadata, len(tickers)) if batch_metadata else {}),
        )

    alert_status = AlertStatus.EN_OBSERVACION if market_open else AlertStatus.WATCHLIST
    watchlist = not market_open and allow_after_hours
    result = await scan_watchlist(
        db,
        tickers,
        force_alert=force_alert,
        alert_status=alert_status,
        watchlist=watchlist,
    )
    return _scanner_payload_from_result(
        result,
        debug=debug,
        session_status=None if market_open else session_status,
        batch_metadata=batch_metadata,
    )


@router.post("/run", response_model=ScannerResponse, response_model_exclude_none=True, summary="Run scanner")
async def run_scanner(
    request: ScannerRequest,
    allow_after_hours: bool = Query(default=False),
    debug: bool = Query(default=False),
    force_alert: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> ScannerResponse:
    return await _run_scanner_for_tickers(
        request.tickers,
        allow_after_hours=allow_after_hours,
        debug=debug,
        force_alert=force_alert,
        db=db,
    )


@router.post("/run-watchlist", response_model=ScannerResponse, response_model_exclude_none=False, summary="Run watchlist scanner")
async def run_watchlist_scanner(
    allow_after_hours: bool = Query(default=False),
    debug: bool = Query(default=False),
    force_alert: bool = Query(default=False),
    limit: Optional[int] = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> ScannerResponse:
    all_tickers = [item.ticker for item in list_enabled_watchlist_tickers(db)]
    selected_tickers = _slice_tickers(all_tickers, limit=limit, offset=offset)
    metadata = _batch_metadata(total_enabled=len(all_tickers), limit=limit, offset=offset if limit is not None else 0)
    return await _run_scanner_for_tickers(
        selected_tickers,
        allow_after_hours=allow_after_hours,
        debug=debug,
        force_alert=force_alert,
        db=db,
        batch_metadata=metadata,
    )