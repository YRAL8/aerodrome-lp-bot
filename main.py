import asyncio
import logging

import config
from aerodrome import get_position

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


async def main() -> None:
    log.info("=" * 50)
    log.info(f"Aerodrome LP-бот (Base) | DRY RUN: {config.DRY_RUN}")
    log.info(f"Пул: {config.POOL_ADDRESS}")
    log.info("=" * 50)

    position = await get_position()
    if position is None:
        log.error("Не удалось получить позицию — проверь POOL_ADDRESS в .env")
        return

    demo = " [ДЕМО]" if position.is_demo else ""
    status = "в диапазоне" if position.in_range else "ВНЕ диапазона"
    log.info(
        f"Позиция{demo}: ${position.total_value_usd:.2f} "
        f"(USDC ${position.value_token0_usd:.2f} + cbBTC ${position.value_token1_usd:.2f})"
    )
    log.info(f"Цена cbBTC: ${position.current_price:,.2f}")
    log.info(f"Диапазон: ${position.lower_price:,.2f} — ${position.upper_price:,.2f}")
    log.info(f"Статус: {status}")


if __name__ == "__main__":
    asyncio.run(main())
