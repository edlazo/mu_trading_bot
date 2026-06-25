import json
from pathlib import Path

import pytest

from app.schemas.alert import FinalDecision


EXAMPLE_SIGNAL = {
    "ticker": "AAPL",
    "market": "USA",
    "timeframe": "1D",
    "source": "mixed",
    "reason": "Precio recupera zona tecnica y los indicadores acompanan parcialmente.",
    "close": 195.2,
    "sma30": 192.8,
    "asl21": 191.4,
    "ema150": 181.6,
    "ema200": 178.9,
    "rsi": 61.5,
    "rsi_ma": 55.2,
    "koncorde_azul": 8.2,
    "koncorde_azul_prev": 6.5,
    "koncorde_marron": 14.4,
    "koncorde_marron_prev": 12.8,
    "koncorde_media": 10.1,
    "ppo": 1.25,
    "ppo_signal": 1.1,
    "ppo_hist": 0.15,
    "ppo_hist_prev": 0.07,
    "volume_ok": True,
    "support": 188.4,
    "resistance": 198.5,
    "target": 205.0,
    "stop_loss": 188.4,
    "weekly_context": "alcista",
    "monthly_context": "sano",
    "fundamental_context": "neutral",
    "notes": "Alerta preliminar para seguimiento.",
}


@pytest.fixture
def webhook_headers():
    return {"X-Webhook-Secret": "test-secret"}


def test_webhook_responds_alert_sent(client, webhook_headers):
    response = client.post(
        "/webhooks/tradingview",
        json=EXAMPLE_SIGNAL,
        headers=webhook_headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "alert_sent"
    assert response.json()["ticker"] == "AAPL"


def test_webhook_accepts_query_param_secret(client):
    response = client.post(
        "/webhooks/tradingview?secret=test-secret",
        json=EXAMPLE_SIGNAL,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "alert_sent"


def test_webhook_rejects_invalid_secret(client):
    response = client.post(
        "/webhooks/tradingview?secret=bad-secret",
        json=EXAMPLE_SIGNAL,
        headers={"X-Webhook-Secret": "bad-secret"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid webhook secret"


def test_webhook_rejects_missing_secret(client):
    response = client.post(
        "/webhooks/tradingview",
        json=EXAMPLE_SIGNAL,
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid webhook secret"


def test_test_discord_webhook_responds_200(client):
    response = client.post("/webhooks/test-discord")

    assert response.status_code == 200
    assert response.json() == {"status": "discord_test_sent"}


def test_tradingview_example_payload_file_is_accepted(client, webhook_headers):
    payload = json.loads(Path("examples/tradingview_alert_payload.json").read_text(encoding="utf-8"))

    response = client.post("/webhooks/tradingview", json=payload, headers=webhook_headers)

    assert response.status_code == 200
    assert response.json()["status"] == "alert_sent"
    assert response.json()["ticker"] == "AAPL"


@pytest.mark.parametrize(
    "payload_update",
    [
        {"ticker": ""},
        {"close": 0},
        {"close": -1},
        {"source": "invalid"},
    ],
)
def test_tradingview_payload_validation_errors(client, webhook_headers, payload_update):
    payload = {**EXAMPLE_SIGNAL, **payload_update}

    response = client.post("/webhooks/tradingview", json=payload, headers=webhook_headers)

    assert response.status_code == 422


def test_final_confirmation_returns_buy_when_rules_pass(client, webhook_headers):
    valid_signal = {**EXAMPLE_SIGNAL, "target": 218.0}
    client.post("/webhooks/tradingview", json=valid_signal, headers=webhook_headers)

    response = client.post("/confirmations/pre-close")

    assert response.status_code == 200
    decision = response.json()["decisions"][0]
    assert decision["decision"] == FinalDecision.COMPRAMOS


def test_final_confirmation_returns_no_buy_when_risk_reward_is_bad(client, webhook_headers):
    bad_signal = {**EXAMPLE_SIGNAL, "target": 198.0}
    client.post("/webhooks/tradingview", json=bad_signal, headers=webhook_headers)

    response = client.post("/confirmations/pre-close")

    assert response.status_code == 200
    decision = response.json()["decisions"][0]
    assert decision["decision"] == FinalDecision.NO_COMPRAMOS
    assert "riesgo/beneficio" in decision["reason"]


def test_webhook_persists_operational_alert_data(client, webhook_headers):
    payload = {**EXAMPLE_SIGNAL, "close": 100.0, "resistance": 101.0, "target": 115.0, "stop_loss": 95.0}
    response = client.post("/webhooks/tradingview", json=payload, headers=webhook_headers)

    assert response.status_code == 200
    alert = client.get("/alerts/active").json()[0]
    assert alert["entry_price"] == 101.0
    assert alert["risk_reward"] == pytest.approx(14 / 6, rel=0.01)
