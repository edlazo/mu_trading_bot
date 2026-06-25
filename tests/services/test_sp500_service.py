import pytest

import pandas as pd

from app.models.watchlist import WatchlistTicker
import app.services.sp500_service as sp500_service
from app.services.sp500_service import (
    fetch_sp500_tickers,
    import_sp500_to_watchlist,
    normalize_yfinance_ticker,
    sync_sp500_watchlist,
)


def test_normalize_yfinance_ticker_converts_dot_to_dash():
    assert normalize_yfinance_ticker("brk.b") == "BRK-B"


class FakeResponse:
    def __init__(self, text: str = "", error: Exception | None = None):
        self.text = text
        self.error = error

    def raise_for_status(self) -> None:
        if self.error is not None:
            raise self.error


def test_fetch_sp500_tickers_uses_mocked_html_and_normalizes_symbols(monkeypatch):
    html = """
    <table>
      <tr><th>Symbol</th><th>Security</th></tr>
      <tr><td>AAPL</td><td>Apple</td></tr>
      <tr><td>BRK.B</td><td>Berkshire Hathaway</td></tr>
      <tr><td>BF.B</td><td>Brown-Forman</td></tr>
      <tr><td>MSFT</td><td>Microsoft</td></tr>
      <tr><td>AAPL</td><td>Apple duplicate</td></tr>
    </table>
    """
    captured = {}

    def fake_get(url, headers=None, timeout=None, follow_redirects=None):
        captured["headers"] = headers
        captured["timeout"] = timeout
        captured["follow_redirects"] = follow_redirects
        return FakeResponse(html)

    monkeypatch.setattr(sp500_service.httpx, "get", fake_get)

    assert fetch_sp500_tickers() == ["AAPL", "BF-B", "BRK-B", "MSFT"]
    assert "MuTradingBot" in captured["headers"]["User-Agent"]
    assert captured["timeout"] == 20
    assert captured["follow_redirects"] is True


def test_fetch_sp500_tickers_raises_clear_error_when_symbol_table_missing(monkeypatch):
    html = """
    <table>
      <tr><th>Ticker</th></tr>
      <tr><td>AAPL</td></tr>
    </table>
    """
    monkeypatch.setattr(sp500_service.httpx, "get", lambda *args, **kwargs: FakeResponse(html))

    with pytest.raises(RuntimeError, match="Could not find S&P 500 symbols table"):
        fetch_sp500_tickers()


def test_fetch_sp500_tickers_raises_clear_error_on_http_error(monkeypatch):
    monkeypatch.setattr(
        sp500_service.httpx,
        "get",
        lambda *args, **kwargs: FakeResponse(error=RuntimeError("HTTP Error 403: Forbidden")),
    )

    with pytest.raises(RuntimeError, match="Could not fetch S&P 500 tickers: HTTP Error 403: Forbidden"):
        fetch_sp500_tickers()


def test_import_sp500_to_watchlist_creates_new_tickers(db_session, monkeypatch):
    monkeypatch.setattr(sp500_service, "fetch_sp500_tickers", lambda: ["AAPL", "MSFT"])

    result = import_sp500_to_watchlist(db_session)

    assert result["fetched"] == 2
    assert result["created"] == 2
    assert result["updated"] == 0
    assert [item.ticker for item in db_session.query(WatchlistTicker).order_by(WatchlistTicker.ticker).all()] == ["AAPL", "MSFT"]


def test_import_sp500_to_watchlist_does_not_duplicate_existing_tickers(db_session, monkeypatch):
    db_session.add(WatchlistTicker(ticker="AAPL", market="USA", enabled=True, notes="old"))
    db_session.commit()
    monkeypatch.setattr(sp500_service, "fetch_sp500_tickers", lambda: ["AAPL", "MSFT"])

    result = import_sp500_to_watchlist(db_session, notes="S&P 500")

    assert result["created"] == 1
    assert result["updated"] == 1
    assert db_session.query(WatchlistTicker).count() == 2
    assert db_session.query(WatchlistTicker).filter(WatchlistTicker.ticker == "AAPL").one().notes == "S&P 500"


def test_import_sp500_to_watchlist_reactivates_disabled_ticker(db_session, monkeypatch):
    db_session.add(WatchlistTicker(ticker="AAPL", market="USA", enabled=False, notes="old"))
    db_session.commit()
    monkeypatch.setattr(sp500_service, "fetch_sp500_tickers", lambda: ["AAPL"])

    result = import_sp500_to_watchlist(db_session, enabled=True)

    assert result["updated"] == 1
    assert db_session.query(WatchlistTicker).filter(WatchlistTicker.ticker == "AAPL").one().enabled is True


def test_sync_sp500_without_disable_removed_keeps_removed_tickers_enabled(db_session, monkeypatch):
    db_session.add(WatchlistTicker(ticker="REMOVED", market="USA", enabled=True, notes="S&P 500"))
    db_session.commit()
    monkeypatch.setattr(sp500_service, "fetch_sp500_tickers", lambda: ["AAPL"])

    result = sync_sp500_watchlist(db_session, disable_removed=False)

    assert result["disabled_removed"] == 0
    assert db_session.query(WatchlistTicker).filter(WatchlistTicker.ticker == "REMOVED").one().enabled is True


def test_sync_sp500_with_disable_removed_disables_only_sp500_removed_tickers(db_session, monkeypatch):
    db_session.add(WatchlistTicker(ticker="REMOVED", market="USA", enabled=True, notes="S&P 500"))
    db_session.add(WatchlistTicker(ticker="CUSTOM", market="USA", enabled=True, notes="manual"))
    db_session.commit()
    monkeypatch.setattr(sp500_service, "fetch_sp500_tickers", lambda: ["AAPL"])

    result = sync_sp500_watchlist(db_session, disable_removed=True)

    assert result["disabled_removed"] == 1
    assert db_session.query(WatchlistTicker).filter(WatchlistTicker.ticker == "REMOVED").one().enabled is False
    assert db_session.query(WatchlistTicker).filter(WatchlistTicker.ticker == "CUSTOM").one().enabled is True