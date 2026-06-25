from app.models.alert import Alert
from app.models.decision import Decision
from app.schemas.alert import AlertStatus, FinalDecision
from tests.test_webhook import EXAMPLE_SIGNAL


def _create_alert(client, signal=None) -> int:
    payload = signal or EXAMPLE_SIGNAL
    response = client.post(
        "/webhooks/tradingview",
        json=payload,
        headers={"X-Webhook-Secret": "test-secret"},
    )
    assert response.status_code == 200

    active_response = client.get("/alerts/active")
    assert active_response.status_code == 200
    return active_response.json()[0]["id"]


def test_confirm_existing_alert_with_updated_data_returns_buy(client):
    alert_id = _create_alert(client)
    updated_signal = {**EXAMPLE_SIGNAL, "target": 218.0}

    response = client.post(f"/confirmations/pre-close/{alert_id}", json=updated_signal)

    assert response.status_code == 200
    body = response.json()
    assert body["ticker"] == "AAPL"
    assert body["decision"] == FinalDecision.COMPRAMOS
    assert body["score"] >= 65
    assert body["risk"] in {"BAJO 🟢", "MEDIO 🟡"}
    assert body["reason"] == "oportunidad vigente con riesgo aceptable"


def test_confirm_existing_alert_with_updated_data_returns_no_buy(client):
    alert_id = _create_alert(client)
    updated_signal = {**EXAMPLE_SIGNAL, "target": 198.0}

    response = client.post(f"/confirmations/pre-close/{alert_id}", json=updated_signal)

    assert response.status_code == 200
    body = response.json()
    assert body["ticker"] == "AAPL"
    assert body["decision"] == FinalDecision.NO_COMPRAMOS
    assert "riesgo/beneficio" in body["reason"]


def test_confirm_missing_alert_returns_404(client):
    response = client.post("/confirmations/pre-close/999", json=EXAMPLE_SIGNAL)

    assert response.status_code == 404


def test_confirmed_alert_is_not_confirmed_again(client):
    alert_id = _create_alert(client)
    updated_signal = {**EXAMPLE_SIGNAL, "target": 218.0}

    first_response = client.post(f"/confirmations/pre-close/{alert_id}", json=updated_signal)
    second_response = client.post(f"/confirmations/pre-close/{alert_id}", json=updated_signal)

    assert first_response.status_code == 200
    assert second_response.status_code == 409
    assert "already confirmed" in second_response.json()["detail"]


def test_datetime_columns_are_timezone_aware():
    assert Alert.__table__.c.created_at.type.timezone is True
    assert Alert.__table__.c.updated_at.type.timezone is True
    assert Decision.__table__.c.created_at.type.timezone is True

def test_bulk_pre_close_response_includes_counts(client):
    client.post("/webhooks/tradingview", json={**EXAMPLE_SIGNAL, "target": 218.0}, headers={"X-Webhook-Secret": "test-secret"})

    response = client.post("/confirmations/pre-close")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pre_close_confirmation_completed"
    assert body["confirmed"] == 1
    assert body["rejected"] == 0
    assert len(body["decisions"]) == 1


def test_bulk_confirmation_only_takes_active_alerts(client, db_session):
    active_id = _create_alert(client, {**EXAMPLE_SIGNAL, "ticker": "AAPL", "target": 218.0})
    watchlist = Alert(
        ticker="MSFT",
        market="USA",
        timeframe="1D",
        source="mixed",
        reason="watchlist",
        close=100,
        preliminary_score=70,
        preliminary_risk="MEDIO ??",
        status=AlertStatus.WATCHLIST.value,
    )
    archived = Alert(
        ticker="TSLA",
        market="USA",
        timeframe="1D",
        source="mixed",
        reason="archived",
        close=100,
        preliminary_score=70,
        preliminary_risk="MEDIO ??",
        status=AlertStatus.ARCHIVED.value,
    )
    db_session.add_all([watchlist, archived])
    db_session.commit()

    response = client.post("/confirmations/pre-close")

    assert response.status_code == 200
    body = response.json()
    assert len(body["decisions"]) == 1
    assert body["decisions"][0]["ticker"] == "AAPL"
    assert db_session.get(Alert, active_id).status == AlertStatus.COMPRAMOS.value
    assert db_session.get(Alert, watchlist.id).status == AlertStatus.WATCHLIST.value
    assert db_session.get(Alert, archived.id).status == AlertStatus.ARCHIVED.value


def test_extreme_risk_alert_is_rejected(client):
    alert_id = _create_alert(client, {**EXAMPLE_SIGNAL, "target": 218.0})
    extreme_signal = {**EXAMPLE_SIGNAL, "target": 218.0, "rsi": 82.0}

    response = client.post(f"/confirmations/pre-close/{alert_id}", json=extreme_signal)

    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == FinalDecision.NO_COMPRAMOS
    assert "Riesgo demasiado alto" in body["reason"]


def test_invalid_risk_reward_alert_is_rejected(client):
    alert_id = _create_alert(client)
    invalid_signal = {**EXAMPLE_SIGNAL, "target": 198.5}

    response = client.post(f"/confirmations/pre-close/{alert_id}", json=invalid_signal)

    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == FinalDecision.NO_COMPRAMOS
    assert "riesgo/beneficio" in body["reason"]


def test_bulk_confirmation_does_not_confirm_same_alert_twice(client):
    client.post("/webhooks/tradingview", json={**EXAMPLE_SIGNAL, "target": 218.0}, headers={"X-Webhook-Secret": "test-secret"})

    first_response = client.post("/confirmations/pre-close")
    second_response = client.post("/confirmations/pre-close")

    assert first_response.status_code == 200
    assert first_response.json()["confirmed"] == 1
    assert second_response.status_code == 200
    assert second_response.json()["confirmed"] == 0
    assert second_response.json()["rejected"] == 0
    assert second_response.json()["decisions"] == []
