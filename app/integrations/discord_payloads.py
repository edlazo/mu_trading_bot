from app.schemas.alert import RiskLevel


def build_discord_embed_payload(embed: dict, content: str | None = None) -> dict:
    payload: dict = {"embeds": [embed], "allowed_mentions": {"parse": []}}
    if content is not None:
        payload["content"] = content
    return payload


def risk_color(risk: RiskLevel) -> int:
    colors = {
        RiskLevel.BAJO: 0x2ECC71,
        RiskLevel.MEDIO: 0xF1C40F,
        RiskLevel.ALTO: 0xE67E22,
        RiskLevel.EXTREMO: 0xE74C3C,
    }
    return colors[risk]