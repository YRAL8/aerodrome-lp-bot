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
_TRUE_VALUES = {"true", "1", "yes", "y", "on"}


def _env_bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in _TRUE_VALUES


DRY_RUN = _env_bool("DRY_RUN", "true")
DEMO_POSITION = _env_bool("DEMO_POSITION", "true")
DEMO_DEPOSIT_USD = float(os.getenv("DEMO_DEPOSIT_USD", "1000"))
RANGE_WIDTH_PCT = float(os.getenv("RANGE_WIDTH_PCT", "8"))
POLL_INTERVAL_SEC = int(os.getenv("POLL_INTERVAL_SEC", "300"))

if not (0 < RANGE_WIDTH_PCT < 100):
    raise ValueError("RANGE_WIDTH_PCT must be strictly between 0 and 100 (exclusive)")

if POLL_INTERVAL_SEC < 1:
    raise ValueError("POLL_INTERVAL_SEC must be >= 1")

_PLACEHOLDER_MARKERS = ("YOUR_", "CHANGE_ME", "TODO", "PLACEHOLDER")


def is_placeholder(value: str) -> bool:
    """True, если значение не заполнено или осталось шаблоном из env_template."""
    if not value:
        return True
    upper = value.upper()
    return any(marker in upper for marker in _PLACEHOLDER_MARKERS)


def wallet_configured() -> bool:
    return not is_placeholder(WALLET_PRIVATE_KEY)
