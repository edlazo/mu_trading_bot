from datetime import UTC, datetime

import pandas as pd
import pytest

import app.services.backtest_service as backtest_service
from app.models.backtest import BacktestResult
from app.models.decision import Decision
from app.schemas.backtest import BacktestOutcome


def _decision(db_session, decision="COMPRAMOS", ticker="AAPL", entry=100.0, target=110.0, stop=95.0):
    item = Decision(
        alert_id=1,
        ticker=ticker,
        final_score=90,
        final_risk="BAJO ??",
        decision=decision,
        reason="test",
        entry_price=entry,
        target=target,
        stop_loss=stop,
        risk_reward=(target - entry) / (entry - stop) if target is not None and stop is not None else None,
    )
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)
    return item


def _price_data(highs, lows, closes=None):
    closes = closes or [(high + low) / 2 for high, low in zip(highs, lows)]
    return pd.DataFrame(
        {
            "High": highs,
            "Low": lows,
            "Close": closes,
        },
        index=pd.date_range("2026-01-02", periods=len(highs), freq="D", tz=UTC),
    )


def _mock_download(monkeypatch, data):
    monkeypatch.setattr(backtest_service.yf, "download", lambda *args, **kwargs: data)


def test_backtest_missing_decision_returns_404(client):
    response = client.post("/backtests/decisions/999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Decision not found"


def test_no_buy_decision_is_not_backtested(client, db_session):
    decision = _decision(db_session, decision="NO_COMPRAMOS")

    response = client.post(f"/backtests/decisions/{decision.id}")

    assert response.status_code == 400
    assert response.json()["detail"] == "Only COMPRAMOS decisions can be backtested"


def test_buy_decision_target_hit_creates_backtest(client, db_session, monkeypatch):
    decision = _decision(db_session)
    _mock_download(monkeypatch, _price_data([111.0, 112.0], [99.0, 100.0], [110.5, 111.0]))

    response = client.post(f"/backtests/decisions/{decision.id}?days=10")

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"] == BacktestOutcome.TARGET_HIT
    assert payload["exit_price"] == 110.0
    assert payload["pnl_percent"] == pytest.approx(10.0)
    assert db_session.query(BacktestResult).count() == 1


def test_buy_decision_stop_hit_creates_backtest(client, db_session, monkeypatch):
    decision = _decision(db_session)
    _mock_download(monkeypatch, _price_data([104.0, 106.0], [94.0, 96.0], [96.0, 100.0]))

    response = client.post(f"/backtests/decisions/{decision.id}?days=10")

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"] == BacktestOutcome.STOP_HIT
    assert payload["exit_price"] == 95.0
    assert payload["pnl_percent"] == pytest.approx(-5.0)


def test_buy_decision_without_hit_creates_no_result(client, db_session, monkeypatch):
    decision = _decision(db_session)
    _mock_download(monkeypatch, _price_data([104.0, 105.0], [97.0, 98.0], [102.0, 103.0]))

    response = client.post(f"/backtests/decisions/{decision.id}?days=10")

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"] == BacktestOutcome.NO_RESULT
    assert payload["exit_price"] == 103.0
    assert payload["pnl_percent"] == pytest.approx(3.0)


def test_backtests_history_returns_results(client, db_session, monkeypatch):
    decision = _decision(db_session)
    _mock_download(monkeypatch, _price_data([111.0], [99.0], [110.0]))
    client.post(f"/backtests/decisions/{decision.id}")

    response = client.get("/backtests")

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["ticker"] == "AAPL"


def test_backtests_summary_calculates_metrics(client, db_session):
    db_session.add_all(
        [
            BacktestResult(decision_id=1, alert_id=1, ticker="AAPL", result="TARGET_HIT", days_checked=1, pnl_percent=10.0, reason="target"),
            BacktestResult(decision_id=2, alert_id=2, ticker="MSFT", result="STOP_HIT", days_checked=1, pnl_percent=-5.0, reason="stop"),
            BacktestResult(decision_id=3, alert_id=3, ticker="NVDA", result="NO_RESULT", days_checked=10, pnl_percent=2.5, reason="none"),
        ]
    )
    db_session.commit()

    response = client.get("/backtests/summary")

    assert response.status_code == 200
    assert response.json() == {
        "total": 3,
        "target_hit": 1,
        "stop_hit": 1,
        "no_result": 1,
        "win_rate": pytest.approx(33.33333333333333),
        "average_pnl_percent": pytest.approx(2.5),
    }


def test_backtest_does_not_duplicate_result_for_same_decision(client, db_session, monkeypatch):
    decision = _decision(db_session)
    _mock_download(monkeypatch, _price_data([111.0], [99.0], [110.0]))

    first_response = client.post(f"/backtests/decisions/{decision.id}")
    second_response = client.post(f"/backtests/decisions/{decision.id}")

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_response.json()["id"] == second_response.json()["id"]
    assert db_session.query(BacktestResult).count() == 1


def test_bulk_backtest_runs_only_pending_buy_decisions(client, db_session, monkeypatch):
    first = _decision(db_session, ticker="AAPL")
    _decision(db_session, ticker="MSFT")
    _decision(db_session, ticker="TSLA", decision="NO_COMPRAMOS")
    db_session.add(BacktestResult(decision_id=first.id, alert_id=first.alert_id, ticker="AAPL", result="NO_RESULT", days_checked=10, reason="existing"))
    db_session.commit()
    _mock_download(monkeypatch, _price_data([111.0], [99.0], [110.0]))

    response = client.post("/backtests/run?days=10")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "backtest_completed"
    assert payload["created"] == 1
    assert payload["skipped"] == 1
    assert len(payload["results"]) == 1
    assert db_session.query(BacktestResult).count() == 2
