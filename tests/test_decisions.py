from app.models.alert import Alert
from app.models.decision import Decision
import pytest

from app.schemas.alert import FinalDecision
from tests.test_webhook import EXAMPLE_SIGNAL


def _create_confirmed_decision(client, ticker: str = "AAPL", target: float = 218.0) -> dict:
    payload = {**EXAMPLE_SIGNAL, "ticker": ticker, "target": target}
    response = client.post(
        "/webhooks/tradingview",
        json=payload,
        headers={"X-Webhook-Secret": "test-secret"},
    )
    assert response.status_code == 200

    response = client.post("/confirmations/pre-close")
    assert response.status_code == 200
    assert response.json()["decisions"]
    return response.json()["decisions"][0]


def test_get_decisions_returns_decisions(client):
    _create_confirmed_decision(client, ticker="AAPL")

    response = client.get("/decisions")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["ticker"] == "AAPL"
    assert payload[0]["decision"] == FinalDecision.COMPRAMOS
    assert payload[0]["entry_price"] == 198.5
    assert payload[0]["target"] == 218.0
    assert payload[0]["stop_loss"] == 188.4
    assert payload[0]["risk_reward"] is not None


def test_get_decision_by_id_returns_decision(client):
    _create_confirmed_decision(client, ticker="AAPL")
    decision_id = client.get("/decisions").json()[0]["id"]

    response = client.get(f"/decisions/{decision_id}")

    assert response.status_code == 200
    assert response.json()["id"] == decision_id
    assert response.json()["ticker"] == "AAPL"


def test_get_missing_decision_returns_404(client):
    response = client.get("/decisions/999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Decision not found"


def test_get_decisions_by_ticker_filters_history(client):
    _create_confirmed_decision(client, ticker="AAPL")
    _create_confirmed_decision(client, ticker="MSFT")

    response = client.get("/decisions/by-ticker/aapl")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["ticker"] == "AAPL"


def test_decisions_summary_returns_totals(client, db_session):
    db_session.add_all(
        [
            Decision(alert_id=1, ticker="AAPL", final_score=82, final_risk="BAJO ??", decision="COMPRAMOS", reason="ok"),
            Decision(alert_id=2, ticker="MSFT", final_score=70, final_risk="MEDIO ??", decision="COMPRAMOS", reason="ok"),
            Decision(alert_id=3, ticker="TSLA", final_score=52, final_risk="ALTO ??", decision="NO_COMPRAMOS", reason="risk"),
            Decision(alert_id=4, ticker="NVDA", final_score=30, final_risk="EXTREMO ??", decision="NO_COMPRAMOS", reason="risk"),
        ]
    )
    db_session.commit()

    response = client.get("/decisions/summary")

    assert response.status_code == 200
    assert response.json() == {
        "total": 4,
        "compramos": 2,
        "no_compramos": 2,
        "by_risk": {"BAJO": 1, "MEDIO": 1, "ALTO": 1, "EXTREMO": 1},
    }


def test_pre_close_confirmation_creates_decision(client, db_session):
    _create_confirmed_decision(client, ticker="AAPL")

    decisions = db_session.query(Decision).all()

    assert len(decisions) == 1
    assert decisions[0].ticker == "AAPL"
    assert decisions[0].entry_price == 198.5
    assert decisions[0].target == 218.0
    assert decisions[0].stop_loss == 188.4
    assert decisions[0].risk_reward is not None


def test_double_confirmation_does_not_duplicate_decision(client, db_session):
    response = client.post(
        "/webhooks/tradingview",
        json={**EXAMPLE_SIGNAL, "target": 218.0},
        headers={"X-Webhook-Secret": "test-secret"},
    )
    assert response.status_code == 200

    first_response = client.post("/confirmations/pre-close")
    second_response = client.post("/confirmations/pre-close")

    assert first_response.status_code == 200
    assert first_response.json()["confirmed"] == 1
    assert second_response.status_code == 200
    assert second_response.json()["decisions"] == []
    assert db_session.query(Decision).count() == 1


def test_existing_decision_for_active_alert_is_not_duplicated(client, db_session):
    create_response = client.post(
        "/webhooks/tradingview",
        json={**EXAMPLE_SIGNAL, "target": 218.0},
        headers={"X-Webhook-Secret": "test-secret"},
    )
    assert create_response.status_code == 200
    alert_id = client.get("/alerts/active").json()[0]["id"]
    db_session.add(
        Decision(
            alert_id=alert_id,
            ticker="AAPL",
            final_score=80,
            final_risk="BAJO ??",
            decision="COMPRAMOS",
            reason="existing",
        )
    )
    db_session.commit()

    response = client.post("/confirmations/pre-close")

    assert response.status_code == 200
    assert response.json()["decisions"] == []
    assert db_session.query(Decision).filter(Decision.alert_id == alert_id).count() == 1
    assert db_session.get(Alert, alert_id).status == "COMPRAMOS"



def _operational_payload(**overrides):
    payload = {
        **EXAMPLE_SIGNAL,
        "ticker": "TEST_CONFIRM",
        "close": 100.0,
        "sma30": 99.0,
        "asl21": 98.0,
        "ema150": 90.0,
        "ema200": 85.0,
        "rsi": 60.0,
        "support": 95.0,
        "resistance": 101.0,
        "target": 115.0,
        "stop_loss": 95.0,
        "reason": "Alerta de prueba para validar confirmacion pre-cierre.",
    }
    payload.update(overrides)
    return payload


def _create_operational_decision(client, payload):
    response = client.post(
        "/webhooks/tradingview",
        json=payload,
        headers={"X-Webhook-Secret": "test-secret"},
    )
    assert response.status_code == 200
    response = client.post("/confirmations/pre-close")
    assert response.status_code == 200
    return client.get("/decisions").json()[0]


def test_decision_stores_operational_data_from_webhook_payload(client):
    decision = _create_operational_decision(client, _operational_payload())

    assert decision["ticker"] == "TEST_CONFIRM"
    assert decision["decision"] == FinalDecision.COMPRAMOS
    assert decision["entry_price"] == 101.0
    assert decision["target"] == 115.0
    assert decision["stop_loss"] == 95.0
    assert decision["risk_reward"] == pytest.approx(14 / 6, rel=0.01)


@pytest.mark.parametrize(
    "payload_update",
    [
        {"target": None},
        {"stop_loss": None},
        {"target": 101.0},
        {"target": 100.0},
        {"stop_loss": 101.0},
        {"stop_loss": 102.0},
        {"target": 105.0},
    ],
)
def test_invalid_operational_data_rejects_decision(client, payload_update):
    decision = _create_operational_decision(client, _operational_payload(**payload_update))

    assert decision["decision"] == FinalDecision.NO_COMPRAMOS
    assert "No se confirma compra porque faltan datos operativos o R/R valido." in decision["reason"]
