import logging

import requests

import config

log = logging.getLogger(__name__)


def send_telegram_message(text: str) -> None:
    """
    Best-effort Telegram notification.

    - If Telegram env vars are placeholders/missing -> silently no-op.
    - Any network/API error -> log warning, never raise.
    """
    token = config.TELEGRAM_BOT_TOKEN
    chat_id = config.TELEGRAM_CHAT_ID

    if config.is_placeholder(token) or config.is_placeholder(chat_id):
        return

    if not text:
        return

    # Telegram Bot API limit is 4096 chars for text.
    if len(text) > 4096:
        text = text[:4093] + "..."

    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=10,
        )
    except Exception:
        log.warning("Telegram sendMessage failed (request error).", exc_info=True)
        return

    if resp.status_code != 200:
        body = (resp.text or "").strip()
        if len(body) > 500:
            body = body[:500] + "..."
        log.warning(
            "Telegram sendMessage failed (HTTP %s). Response: %s",
            resp.status_code,
            body,
        )
