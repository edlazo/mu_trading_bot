import httpx

from app.config import get_settings


async def send_discord_message(
    content: str | None = None,
    embeds: list[dict] | None = None,
) -> None:
    if content is None and embeds is None:
        return

    settings = get_settings()
    payload: dict = {"allowed_mentions": {"parse": []}}
    if content is not None:
        payload["content"] = content
    if embeds is not None:
        payload["embeds"] = embeds

    if not settings.discord_webhook_url:
        if content is not None:
            print(content)
        if embeds is not None:
            print(embeds)
        return

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(settings.discord_webhook_url, json=payload)
        response.raise_for_status()