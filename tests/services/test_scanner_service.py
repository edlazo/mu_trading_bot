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



def test_scan_ticker_force_alert_creates_signal_when_no_opportunity(monkeypatch):
    monkeypatch.setattr(scanner_service.yf, "download", lambda *args, **kwargs: _no_opportunity_dataframe())

    result = scan_ticker("AAPL", force_alert=True)

    assert result.status == "alert_created"
    assert result.signal is not None
    assert result.signal.reason == "Alerta forzada para test del scanner."


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
    assert result.skipped[0].reason == "Hay senal tecnica, pero el R/R no alcanza el minimo operativo"



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
    assert result.skipped[0].reason == "Hay senal tecnica, pero el R/R no alcanza el minimo operativo"
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
