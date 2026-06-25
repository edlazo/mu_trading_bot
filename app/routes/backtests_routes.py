from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.backtest import BacktestResult
from app.schemas.backtest import BacktestResultResponse, BacktestRunResponse
from app.services.backtest_service import backtest_summary, list_backtests, run_backtest_for_decision, run_backtests_for_pending_buy_decisions

router = APIRouter(prefix="/backtests", tags=["Backtesting"])


def _backtest_payload(result: BacktestResult) -> BacktestResultResponse:
    return BacktestResultResponse.model_validate(result)


@router.get("", response_model=list[BacktestResultResponse], summary="Get backtests")
def backtests_history(db: Session = Depends(get_db)) -> list[BacktestResultResponse]:
    return [_backtest_payload(result) for result in list_backtests(db)]


@router.get("/summary", summary="Get backtesting summary")
def backtests_summary(
    include_errors: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> dict:
    return backtest_summary(db, include_errors=include_errors)


@router.post("/run", response_model=BacktestRunResponse, summary="Run backtesting")
def run_pending_backtests(
    days: int = Query(default=10, ge=1, le=120),
    force: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> BacktestRunResponse:
    results, skipped = run_backtests_for_pending_buy_decisions(db, days=days, force=force)
    return BacktestRunResponse(
        status="backtest_completed",
        requested=len(results) + skipped,
        created=len(results),
        skipped=skipped,
        results=[_backtest_payload(result) for result in results],
    )


@router.post("/decisions/{decision_id}", response_model=BacktestResultResponse, summary="Run decision backtesting")
def backtest_decision(
    decision_id: int,
    days: int = Query(default=10, ge=1, le=120),
    force: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> BacktestResultResponse:
    return _backtest_payload(run_backtest_for_decision(db, decision_id, days=days, force=force))