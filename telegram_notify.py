import logging

import requests

import config

log = logging.getLogger(__name__)


def format_position_table(position) -> str:
    """Таблица состава позиции — тот же визуальный стиль, что в orca-lp-bot."""
    table = (
        f"{'':6}{'qty':>12}  {'USD':>9}\n"
        f"{'USDC':6}{position.amount_token0:>12.2f}  ${position.value_token0_usd:>8.2f}\n"
        f"{'cbBTC':6}{position.amount_token1:>12.6f}  ${position.value_token1_usd:>8.2f}\n"
        f"{'─' * 29}\n"
        f"{'TOTAL':6}{'':12}  ${position.total_value_usd:>8.2f}"
    )
    return f"💰 <b>Позиция: ${position.total_value_usd:.2f}</b>\n<pre>{table}</pre>"


def format_range_bar(position) -> str:
    """Прогресс-бар диапазона (L/C/U) — тот же визуальный стиль, что в orca-lp-bot."""
    lo, hi, cur = position.lower_price, position.upper_price, position.current_price
    width = 16
    frac = (cur - lo) / (hi - lo) if hi > lo else 0.5
    filled = min(max(round(frac * width), 0), width)
    bar = "█" * filled + "░" * (width - filled)

    extra = ""
    if cur < lo and lo:
        extra = f" ↓ {(lo - cur) / lo * 100:.1f}%"
    elif cur > hi and hi:
        extra = f" ↑ +{(cur - hi) / hi * 100:.1f}%"

    return (
        f"<code>{bar}</code>{extra}\n"
        f"L ${lo:,.2f}  C ${cur:,.2f}  U ${hi:,.2f}"
    )


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
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
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
