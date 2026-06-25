from types import SimpleNamespace

import pytest

import app.integrations.discord as discord_integration
from app.core.message_builder import (
    _entry_text,
    _stop_loss_text,
    _target_text,
    _technical_reading,
    build_alert_embed,
    build_pre_close_summary_embed,
    build_single_confirmation_embed,
)
from app.integrations.discord import send_discord_message
from app.integrations.discord_payloads import build_discord_embed_payload, risk_color
from app.schemas.alert import FinalDecision, RiskLevel
from app.schemas.tradingview import TradingViewSignal
from tests.test_webhook import EXAMPLE_SIGNAL


def _signal(**overrides) -> TradingViewSignal:
    data = {**EXAMPLE_SIGNAL, **overrides}
    return TradingViewSignal(**data)


def _field_names(embed: dict) -> set[str]:
    return {field["name"] for field in embed["fields"]}


def _field_values(embed: dict) -> dict[str, str]:
    return {field["name"]: field["value"] for field in embed["fields"]}


def test_risk_color_returns_expected_colors():
    assert risk_color(RiskLevel.BAJO) == 0x2ECC71
    assert risk_color(RiskLevel.MEDIO) == 0xF1C40F
    assert risk_color(RiskLevel.ALTO) == 0xE67E22
    assert risk_color(RiskLevel.EXTREMO) == 0xE74C3C


def test_entry_text_uses_resistance_when_available():
    assert _entry_text(_signal(resistance=198.5, sma30=190)) == "Confirmación sobre resistencia 198.50"


def test_entry_text_uses_sma30_when_resistance_missing():
    assert _entry_text(_signal(resistance=None, sma30=190)) == "Arriba de SMA30 190.00"


def test_target_text_uses_target_when_available():
    assert _target_text(_signal(target=205.2, resistance=198.5)) == "205.20"


def test_stop_loss_text_uses_support_when_stop_loss_missing():
    assert _stop_loss_text(_signal(stop_loss=None, support=188.4, sma30=190)) == "Soporte técnico 188.40"


def test_technical_reading_includes_healthy_rsi():
    assert "RSI en zona compradora sana" in _technical_reading(_signal(rsi=61.5))


def test_technical_reading_includes_koncorde_when_confirming():
    reading = _technical_reading(_signal(koncorde_azul=8, koncorde_marron=14, koncorde_media=10))

    assert "KONCORDE acompaña" in reading


def test_technical_reading_includes_ppo_when_confirming():
    reading = _technical_reading(_signal(ppo=1.2, ppo_signal=1.0, ppo_hist=0.2))

    assert "PPO-Min/Max confirma" in reading


def test_build_discord_embed_payload_includes_allowed_mentions():
    payload = build_discord_embed_payload({"title": "Test"}, content="hola")

    assert payload["content"] == "hola"
    assert payload["embeds"] == [{"title": "Test"}]
    assert payload["allowed_mentions"] == {"parse": []}


def test_build_alert_embed_contains_title_with_ticker():
    embed = build_alert_embed(_signal(), score=80, risk=RiskLevel.BAJO)

    assert "$AAPL" in embed["title"]
    assert "Alerta de Compra" in embed["title"]


def test_build_alert_embed_formats_mixed_source():
    embed = build_alert_embed(_signal(source="mixed"), score=80, risk=RiskLevel.ALTO)
    fields = _field_values(embed)

    assert "Gráfico + indicadores" in fields["Motivo"]
    assert fields["Motivo"] != "mixed"



def test_build_alert_embed_risk_reward_uses_estimated_entry_price():
    embed = build_alert_embed(
        _signal(resistance=198.5, target=205, stop_loss=188.4),
        score=80,
        risk=RiskLevel.EXTREMO,
    )
    fields = _field_values(embed)

    assert fields["R/R"] == "0.64:1"

def test_build_alert_embed_contains_core_fields():
    embed = build_alert_embed(_signal(), score=80, risk=RiskLevel.BAJO)

    names = _field_names(embed)
    assert "Lectura técnica" in names
    assert "Riesgo preliminar" in names
    assert "Score preliminar" in names
    assert "Entrada" in names
    assert "Objetivo" in names
    assert "Stop Loss" in names
    assert "R/R" in names


def test_build_alert_embed_includes_missing_data_only_when_missing():
    complete_embed = build_alert_embed(_signal(), score=80, risk=RiskLevel.BAJO)
    missing_embed = build_alert_embed(
        _signal(target=None, stop_loss=None, volume_ok=None),
        score=40,
        risk=RiskLevel.EXTREMO,
    )

    assert "Datos faltantes" not in _field_names(complete_embed)
    assert "Datos faltantes" in _field_names(missing_embed)


def test_build_alert_embed_field_values_stay_under_reasonable_limits():
    embed = build_alert_embed(_signal(reason="x" * 5000), score=80, risk=RiskLevel.BAJO)

    for value in _field_values(embed).values():
        assert len(value) <= 1000


def test_build_single_confirmation_embed_uses_green_for_buy():
    embed = build_single_confirmation_embed("AAPL", FinalDecision.COMPRAMOS, RiskLevel.MEDIO, "ok", 72)

    assert embed["color"] == 0x2ECC71
    assert "Compramos" in embed["description"]


def test_build_single_confirmation_embed_uses_red_for_no_buy():
    embed = build_single_confirmation_embed("AAPL", FinalDecision.NO_COMPRAMOS, RiskLevel.ALTO, "riesgo", 52)

    assert embed["color"] == 0xE74C3C
    assert "No compramos" in embed["description"]


def test_build_single_confirmation_embed_contains_suggested_action():
    embed = build_single_confirmation_embed("AAPL", FinalDecision.COMPRAMOS, RiskLevel.MEDIO, "ok", 72)

    assert "Acción sugerida" in _field_names(embed)


def test_build_pre_close_summary_embed_counts_decisions():
    embed = build_pre_close_summary_embed(
        [
            ("AAPL", FinalDecision.COMPRAMOS, RiskLevel.MEDIO, "ok"),
            ("TSLA", FinalDecision.NO_COMPRAMOS, RiskLevel.ALTO, "riesgo"),
            ("SPY", FinalDecision.COMPRAMOS, RiskLevel.BAJO, "ok"),
        ]
    )
    fields = _field_values(embed)

    assert fields["Total alertas"] == "3"
    assert fields["Compramos"] == "2"
    assert fields["No compramos"] == "1"


@pytest.mark.asyncio
async def test_send_discord_message_sends_allowed_mentions_payload(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return None

        async def post(self, url, json):
            captured["url"] = url
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr(discord_integration, "get_settings", lambda: SimpleNamespace(discord_webhook_url="https://discord.test/webhook"))
    monkeypatch.setattr(discord_integration.httpx, "AsyncClient", FakeAsyncClient)

    await send_discord_message(content="hola", embeds=[{"title": "Embed"}])

    assert captured["url"] == "https://discord.test/webhook"
    assert captured["json"]["content"] == "hola"
    assert captured["json"]["embeds"] == [{"title": "Embed"}]
    assert captured["json"]["allowed_mentions"] == {"parse": []}


@pytest.mark.asyncio
async def test_send_discord_message_without_webhook_accepts_embeds(monkeypatch):
    monkeypatch.setattr(discord_integration, "get_settings", lambda: SimpleNamespace(discord_webhook_url=None))

    await send_discord_message(embeds=[{"title": "Embed"}])

def test_build_alert_embed_uses_high_risk_title_for_extreme_signal():
    embed = build_alert_embed(
        _signal(resistance=198.5, target=198.5, stop_loss=188.4),
        score=40,
        risk=RiskLevel.EXTREMO,
    )

    assert "Se\u00f1al en observaci\u00f3n de alto riesgo" in embed["title"]
    assert "Alerta de Compra" not in embed["title"]
