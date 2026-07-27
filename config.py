import os
from dotenv import load_dotenv

load_dotenv()

# Base RPC
BASE_RPC_URL = os.getenv("BASE_RPC_URL", "https://mainnet.base.org").strip()
WALLET_PRIVATE_KEY = os.getenv("WALLET_PRIVATE_KEY", "").strip()

# Aerodrome Slipstream пул
POOL_ADDRESS = os.getenv("POOL_ADDRESS", "").strip()

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# Настройки бота
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"
DEMO_POSITION = os.getenv("DEMO_POSITION", "true").lower() == "true"
DEMO_DEPOSIT_USD = float(os.getenv("DEMO_DEPOSIT_USD", "1000"))
RANGE_WIDTH_PCT = float(os.getenv("RANGE_WIDTH_PCT", "8"))
POLL_INTERVAL_SEC = int(os.getenv("POLL_INTERVAL_SEC", "300"))

_PLACEHOLDER_MARKERS = ("YOUR_", "CHANGE_ME", "TODO", "PLACEHOLDER")


def is_placeholder(value: str) -> bool:
    """True, если значение не заполнено или осталось шаблоном из env_template."""
    if not value:
        return True
    upper = value.upper()
    return any(marker in upper for marker in _PLACEHOLDER_MARKERS)


def wallet_configured() -> bool:
    return not is_placeholder(WALLET_PRIVATE_KEY)
