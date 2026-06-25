import pandas as pd
import pytest

import app.services.scanner_service as scanner_service
from app.models.alert import Alert
from app.schemas.alert import AlertStatus, OpportunitySource
from app.schemas.tradingview import TradingViewSignal
from app.services.scanner_service import ScannerTickerResult, ScannerWatchlistResult, scan_ticker, scan_watchlist


def _no_opportunity_dataframe() -> pd.DataFrame:
    close = pd.Series([300 - i for i in range(80)], dtype=float)
    return pd.DataFrame({"Close": close})


def _signal(ticker: str = "AAPL") -> TradingViewSignal:
    return TradingViewSignal(
        ticker=ticker,
        source=OpportunitySource.MIXED,
        reason="scanner",
        close=100,
        target=120,
        stop_loss=90,
    )


@pytest.fixture(autouse=True)
def scanner_market_is_open(monkeypatch):
    monkeypatch.setattr("app.main.is_market_open", lambda current_datetime: True)
    monkeypatch.setattr("app.main.get_market_session_status", lambda current_datetime: "open")


def test_scan_ticker_returns_no_data_when_yfinance_has_no_data(monkeypatch):
    monkeypatch.setattr(scanner_service.yf, "download", lambda *args, **kwargs: pd.DataFrame())

    result = scan_ticker("AAPL")

    assert result.status == "no_data"
    assert result.signal is None
    assert result.reason == "yfinance no trajo datos suficientes"


def test_scan_ticker_returns_no_opportunity_when_conditions_do_not_match(monkeypatch):
    monkeypatch.setattr(scanner_service.yf, "download", lambda *args, **kwargs: _no_opportunity_dataframe())

    result = scan_ticker("AAPL")

    assert result.status == "no_opportunity"
    assert result.signal is None
    assert result.reason == "No cumple condiciones de oportunidad"


@pytest.mark.asyncio
async def test_scan_watchlist_reports_duplicate_active_alert(db_session, monkeypatch):
    existing = Alert(
        ticker="AAPL",
        market="USA",
        timeframe="1D",
        source="mixed",
        reason="existing",
        close=100,
        preliminary_score=70,
        preliminary_risk="MEDIO 🟡",
        status=AlertStatus.EN_OBSERVACION.value,
    )
    db_session.add(existing)
    db_session.commit()

    calls = 0

    def fake_scan_ticker(ticker, force_alert=False):
        nonlocal calls
        calls += 1
        return ScannerTickerResult(ticker=ticker, signal=_signal(ticker), status="alert_created", reason="scanner")

    monkeypatch.setattr(scanner_service, "scan_ticker", fake_scan_ticker)

    result = await scan_watchlist(db_session, ["AAPL"])

    assert result.created_alerts == []
    assert result.skipped[0].status == "duplicate_active_alert"
    assert result.skipped[0].reason == "Ya existe una alerta activa"
    assert calls == 0


@pytest.mark.asyncio
async def test_scan_watchlist_created_alert_appears_in_created_tickers(db_session, monkeypatch):
    monkeypatch.setattr(
        scanner_service,
        "scan_ticker",
        lambda ticker, force_alert=False: ScannerTickerResult(ticker=ticker, signal=_signal(ticker), status="alert_created", reason="scanner"),
    )

    result = await scan_watchlist(db_session, ["NVDA"])

    assert len(result.created_alerts) == 1
    assert result.created_tickers == ["NVDA"]
    assert result.skipped == []


def test_scanner_run_endpoint_returns_scan_summary(client, monkeypatch):
    result = ScannerWatchlistResult(
        scanned=3,
        created_alerts=[type("AlertLike", (), {"ticker": "NVDA"})()],
        skipped=[
            ScannerTickerResult("AAPL", None, "no_opportunity", "No cumple condiciones de oportunidad"),
            ScannerTickerResult("MSFT", None, "duplicate_active_alert", "Ya existe una alerta activa"),
        ],
    )

    async def fake_scan_watchlist(db, tickers, force_alert=False, **kwargs):
        return result

    monkeypatch.setattr("app.main.scan_watchlist", fake_scan_watchlist)

    response = client.post("/scanner/run", json={"tickers": ["AAPL", "MSFT", "NVDA"]})

    assert response.status_code == 200
    assert response.json() == {
        "status": "scanner_completed",
        "scanned": 3,
        "created_alerts": 1,
        "created_active_alerts": 0,
        "created_watchlist": 0,
        "created_tickers": ["NVDA"],
        "skipped": [
            {
                "ticker": "AAPL",
                "status": "no_opportunity",
                "reason": "No cumple condiciones de oportunidad",
            },
            {
                "ticker": "MSFT",
                "status": "duplicate_active_alert",
                "reason": "Ya existe una alerta activa",
            },
        ],
    }


def test_scanner_run_force_alert_passes_flag(client, monkeypatch):
    captured = {}

    async def fake_scan_watchlist(db, tickers, force_alert=False, **kwargs):
        captured["force_alert"] = force_alert
        return ScannerWatchlistResult(
            scanned=len(tickers),
            created_alerts=[type("AlertLike", (), {"ticker": "AAPL"})()],
            skipped=[],
        )

    monkeypatch.setattr("app.main.scan_watchlist", fake_scan_watchlist)

    response = client.post("/scanner/run?force_alert=true", json={"tickers": ["AAPL"]})

    assert response.status_code == 200
    assert captured["force_alert"] is True
    assert response.json()["created_tickers"] == ["AAPL"]


def test_scan_ticker_force_alert_creates_signal_when_no_opportunity(monkeypatch):
    monkeypatch.setattr(scanner_service.yf, "download", lambda *args, **kwargs: _no_opportunity_dataframe())

    result = scan_ticker("AAPL", force_alert=True)

    assert result.status == "alert_created"
    assert result.signal is not None
    assert result.signal.reason == "Alerta forzada para test del scanner."

def test_scanner_run_force_alert_respects_minimum_risk_reward(client, monkeypatch):
    monkeypatch.setattr(scanner_service.yf, "download", lambda *args, **kwargs: _no_opportunity_dataframe())

    response = client.post("/scanner/run?force_alert=true", json={"tickers": ["AAPL"]})

    assert response.status_code == 200
    payload = response.json()
    assert payload["created_alerts"] == 0
    assert payload["created_tickers"] == []
    assert payload["skipped"][0]["status"] in {"technical_signal_invalid_rr", "invalid_risk_reward"}


def test_scanner_run_force_alert_empty_dataframe_returns_no_data(client, monkeypatch):
    monkeypatch.setattr(scanner_service.yf, "download", lambda *args, **kwargs: pd.DataFrame())

    response = client.post("/scanner/run?force_alert=true", json={"tickers": ["AAPL"]})

    assert response.status_code == 200
    payload = response.json()
    assert payload["created_alerts"] == 0
    assert payload["created_tickers"] == []
    assert payload["skipped"][0]["status"] == "no_data"


def test_scanner_run_returns_error_for_failing_ticker(client, monkeypatch):
    def fake_scan_ticker(ticker, force_alert=False):
        raise RuntimeError("scanner exploded")

    monkeypatch.setattr(scanner_service, "scan_ticker", fake_scan_ticker)

    response = client.post("/scanner/run", json={"tickers": ["AAPL"]})

    assert response.status_code == 200
    payload = response.json()
    assert payload["created_alerts"] == 0
    assert payload["skipped"] == [
        {"ticker": "AAPL", "status": "error", "reason": "scanner exploded"}
    ]


def test_scanner_run_debug_includes_technical_metrics(client, monkeypatch):
    debug = {
        "close": 195.2,
        "sma30": 192.8,
        "rsi": 48.2,
        "ppo": 0.5,
        "conditions": {"rsi_in_buy_zone": False},
    }
    result = ScannerWatchlistResult(
        scanned=1,
        created_alerts=[],
        skipped=[ScannerTickerResult("AAPL", None, "no_opportunity", "No cumple condiciones de oportunidad", debug)],
    )

    async def fake_scan_watchlist(db, tickers, force_alert=False, **kwargs):
        return result

    monkeypatch.setattr("app.main.scan_watchlist", fake_scan_watchlist)

    response = client.post("/scanner/run?debug=true", json={"tickers": ["AAPL"]})

    assert response.status_code == 200
    skipped_debug = response.json()["skipped"][0]["debug"]
    assert skipped_debug["close"] == 195.2
    assert skipped_debug["sma30"] == 192.8
    assert skipped_debug["rsi"] == 48.2
    assert skipped_debug["ppo"] == 0.5
    assert skipped_debug["conditions"] == {"rsi_in_buy_zone": False}


def test_scanner_run_debug_includes_created_ticker_debug(client, monkeypatch):
    debug = {"close": 100.0, "sma30": 99.0, "rsi": 55.0, "ppo": 1.0, "conditions": {"rsi_in_buy_zone": True}}
    result = ScannerWatchlistResult(
        scanned=1,
        created_alerts=[type("AlertLike", (), {"ticker": "NVDA"})()],
        skipped=[],
        created_debug=[ScannerTickerResult("NVDA", _signal("NVDA"), "alert_created", "scanner", debug)],
    )

    async def fake_scan_watchlist(db, tickers, force_alert=False, **kwargs):
        return result

    monkeypatch.setattr("app.main.scan_watchlist", fake_scan_watchlist)

    response = client.post("/scanner/run?debug=true", json={"tickers": ["NVDA"]})

    assert response.status_code == 200
    payload = response.json()
    assert payload["created_tickers"] == ["NVDA"]
    assert payload["created"][0]["debug"]["conditions"] == {"rsi_in_buy_zone": True}


def test_scanner_run_market_closed_without_after_hours_does_not_create_alerts(client, monkeypatch):
    monkeypatch.setattr("app.main.is_market_open", lambda current_datetime: False)
    monkeypatch.setattr("app.main.get_market_session_status", lambda current_datetime: "post_market")

    response = client.post("/scanner/run", json={"tickers": ["AAPL"]})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "market_closed"
    assert payload["session_status"] == "post_market"
    assert payload["created_alerts"] == 0
    assert payload["message"] == "Mercado cerrado. Ejecutar scanner en horario de mercado o usar allow_after_hours=true para watchlist."


def test_scanner_run_after_hours_creates_watchlist_alert(client, monkeypatch):
    monkeypatch.setattr("app.main.is_market_open", lambda current_datetime: False)
    monkeypatch.setattr("app.main.get_market_session_status", lambda current_datetime: "post_market")
    monkeypatch.setattr(
        scanner_service,
        "scan_ticker",
        lambda ticker, force_alert=False: ScannerTickerResult(ticker=ticker, signal=_signal(ticker), status="alert_created", reason="scanner"),
    )

    response = client.post("/scanner/run?allow_after_hours=true", json={"tickers": ["AAPL"]})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "scanner_completed"
    assert payload["session_status"] == "post_market"
    assert payload["created_alerts"] == 1
    assert payload["created_tickers"] == ["AAPL"]

    active_response = client.get("/alerts/active")
    watchlist_response = client.get("/alerts/watchlist")

    assert active_response.status_code == 200
    assert active_response.json() == []
    assert watchlist_response.status_code == 200
    watchlist = watchlist_response.json()
    assert len(watchlist) == 1
    assert watchlist[0]["ticker"] == "AAPL"
    assert watchlist[0]["status"] == AlertStatus.WATCHLIST.value


def _scanner_dataframe_with_high_low_volume() -> pd.DataFrame:
    rows = 80
    close = pd.Series([100.0] * (rows - 1) + [104.0], dtype=float)
    high = pd.Series([105.0] * (rows - 1) + [999.0], dtype=float)
    low = pd.Series([90.0] * rows, dtype=float)
    volume = pd.Series([1000.0] * rows, dtype=float)
    return pd.DataFrame({"Close": close, "High": high, "Low": low, "Volume": volume})


@pytest.mark.asyncio
async def test_scan_watchlist_skips_when_target_equals_entry_price(db_session, monkeypatch):
    signal = TradingViewSignal(ticker="MELI", source=OpportunitySource.MIXED, reason="scanner", close=100, resistance=110, target=110, stop_loss=90)
    monkeypatch.setattr(scanner_service, "scan_ticker", lambda ticker, force_alert=False: ScannerTickerResult(ticker, signal, "alert_created", "scanner"))

    result = await scan_watchlist(db_session, ["MELI"])

    assert result.created_alerts == []
    assert result.skipped[0].status == "invalid_risk_reward"


@pytest.mark.asyncio
async def test_scan_watchlist_skips_when_target_is_below_entry_price(db_session, monkeypatch):
    signal = TradingViewSignal(ticker="MELI", source=OpportunitySource.MIXED, reason="scanner", close=100, resistance=110, target=105, stop_loss=90)
    monkeypatch.setattr(scanner_service, "scan_ticker", lambda ticker, force_alert=False: ScannerTickerResult(ticker, signal, "alert_created", "scanner"))

    result = await scan_watchlist(db_session, ["MELI"])

    assert result.created_alerts == []
    assert result.skipped[0].status == "invalid_risk_reward"


@pytest.mark.asyncio
async def test_scan_watchlist_skips_when_stop_loss_is_above_entry_price(db_session, monkeypatch):
    signal = TradingViewSignal(ticker="MELI", source=OpportunitySource.MIXED, reason="scanner", close=100, target=120, stop_loss=100)
    monkeypatch.setattr(scanner_service, "scan_ticker", lambda ticker, force_alert=False: ScannerTickerResult(ticker, signal, "alert_created", "scanner"))

    result = await scan_watchlist(db_session, ["MELI"])

    assert result.created_alerts == []
    assert result.skipped[0].status == "invalid_risk_reward"


@pytest.mark.asyncio
async def test_scan_watchlist_skips_when_risk_reward_is_below_one(db_session, monkeypatch):
    signal = TradingViewSignal(ticker="MELI", source=OpportunitySource.MIXED, reason="scanner", close=100, target=105, stop_loss=90)
    monkeypatch.setattr(scanner_service, "scan_ticker", lambda ticker, force_alert=False: ScannerTickerResult(ticker, signal, "alert_created", "scanner"))

    result = await scan_watchlist(db_session, ["MELI"])

    assert result.created_alerts == []
    assert result.skipped[0].status == "technical_signal_invalid_rr"
    assert result.skipped[0].reason == "Hay se?al t?cnica, pero el R/R no alcanza el m?nimo operativo"


def test_scan_ticker_resistance_excludes_current_high(monkeypatch):
    monkeypatch.setattr(scanner_service.yf, "download", lambda *args, **kwargs: _scanner_dataframe_with_high_low_volume())

    result = scan_ticker("MELI")

    assert result.signal is not None
    assert result.signal.resistance == 105.0
    assert result.signal.target == 108.15
    assert result.debug["resistance"] == 105.0


def test_scan_ticker_sets_volume_ok_when_yfinance_has_volume(monkeypatch):
    monkeypatch.setattr(scanner_service.yf, "download", lambda *args, **kwargs: _scanner_dataframe_with_high_low_volume())

    result = scan_ticker("MELI")

    assert result.signal is not None
    assert result.signal.volume_ok is True


@pytest.mark.asyncio
async def test_scan_watchlist_skips_technical_signal_when_risk_reward_below_one_for_watchlist(db_session, monkeypatch):
    signal = TradingViewSignal(ticker="ABBV", source=OpportunitySource.MIXED, reason="scanner", close=100, target=105, stop_loss=90)
    debug = {"conditions": {"rsi_in_buy_zone": True}, "close": 100, "entry_price": 100, "target": 105, "stop_loss": 90, "risk_reward": 0.5}
    monkeypatch.setattr(scanner_service, "scan_ticker", lambda ticker, force_alert=False: ScannerTickerResult(ticker, signal, "alert_created", "scanner", debug))

    result = await scan_watchlist(db_session, ["ABBV"], alert_status=AlertStatus.WATCHLIST, watchlist=True)

    assert result.created_alerts == []
    assert result.skipped[0].status == "technical_signal_invalid_rr"
    assert result.skipped[0].reason == "Hay se?al t?cnica, pero el R/R no alcanza el m?nimo operativo"
    assert result.skipped[0].debug["risk_reward"] == 0.5
    assert result.skipped[0].debug["conditions"] == {"rsi_in_buy_zone": True}


@pytest.mark.asyncio
async def test_scan_watchlist_creates_watchlist_when_risk_reward_reaches_minimum(db_session, monkeypatch):
    signal = TradingViewSignal(ticker="ABNB", source=OpportunitySource.MIXED, reason="scanner", close=100, target=112, stop_loss=94)
    monkeypatch.setattr(scanner_service, "scan_ticker", lambda ticker, force_alert=False: ScannerTickerResult(ticker, signal, "alert_created", "scanner", {"conditions": {"rsi_in_buy_zone": True}}))

    result = await scan_watchlist(db_session, ["ABNB"], alert_status=AlertStatus.WATCHLIST, watchlist=True)

    assert len(result.created_alerts) == 1
    assert result.created_alerts[0].status == AlertStatus.WATCHLIST.value
    assert result.skipped == []


@pytest.mark.asyncio
async def test_open_market_skips_technical_signal_when_risk_reward_below_one(db_session, monkeypatch):
    signal = TradingViewSignal(ticker="ABBV", source=OpportunitySource.MIXED, reason="scanner", close=100, target=105, stop_loss=90)
    monkeypatch.setattr(scanner_service, "scan_ticker", lambda ticker, force_alert=False: ScannerTickerResult(ticker, signal, "alert_created", "scanner", {"conditions": {"ppo_bullish": True}}))

    result = await scan_watchlist(db_session, ["ABBV"], alert_status=AlertStatus.EN_OBSERVACION)

    assert result.created_alerts == []
    assert result.skipped[0].status == "technical_signal_invalid_rr"


@pytest.mark.asyncio
async def test_watchlist_invalid_target_returns_invalid_risk_reward(db_session, monkeypatch):
    signal = TradingViewSignal(ticker="MELI", source=OpportunitySource.MIXED, reason="scanner", close=100, resistance=110, target=110, stop_loss=90)
    monkeypatch.setattr(scanner_service, "scan_ticker", lambda ticker, force_alert=False: ScannerTickerResult(ticker, signal, "alert_created", "scanner", {"conditions": {"near_resistance": True}}))

    result = await scan_watchlist(db_session, ["MELI"], alert_status=AlertStatus.WATCHLIST, watchlist=True)

    assert result.created_alerts == []
    assert result.skipped[0].status == "invalid_risk_reward"


@pytest.mark.asyncio
async def test_watchlist_invalid_stop_returns_invalid_risk_reward(db_session, monkeypatch):
    signal = TradingViewSignal(ticker="MELI", source=OpportunitySource.MIXED, reason="scanner", close=100, target=120, stop_loss=100)
    monkeypatch.setattr(scanner_service, "scan_ticker", lambda ticker, force_alert=False: ScannerTickerResult(ticker, signal, "alert_created", "scanner", {"conditions": {"near_resistance": True}}))

    result = await scan_watchlist(db_session, ["MELI"], alert_status=AlertStatus.WATCHLIST, watchlist=True)

    assert result.created_alerts == []
    assert result.skipped[0].status == "invalid_risk_reward"
