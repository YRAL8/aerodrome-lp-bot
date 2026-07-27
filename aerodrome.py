"""
Чтение данных пула Aerodrome Slipstream (Base, форк Uniswap V3) с mainnet.
Фаза 1 — только чтение: реальная цена из реального пула, но позиция — демо
(DRY_RUN), никаких транзакций. Тот же принцип, что и в orca-lp-bot: сначала
доказать, что бот честно видит реальный рынок, прежде чем доверять ему деньги.

Пул USDC-cbBTC найден и проверен напрямую в блокчейне 2026-07-27 (не по
скриншотам сайтов): 0x4e962BB3889Bf030368F56810A9c96B83CB3E778,
tickSpacing=100, token0=USDC (6 знаков), token1=cbBTC (8 знаков).
Комиссия у Aerodrome Slipstream ДИНАМИЧЕСКАЯ (DynamicSwapFeeModule) — в
отличие от Orca, где фикс на весь пул, тут f() меняется в рантайме.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from web3 import Web3

import config
from config import BASE_RPC_URL, POOL_ADDRESS, DRY_RUN, DEMO_POSITION, DEMO_DEPOSIT_USD

POOL_ABI = [
    {"inputs": [], "name": "token0", "outputs": [{"type": "address"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "token1", "outputs": [{"type": "address"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "tickSpacing", "outputs": [{"type": "int24"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "fee", "outputs": [{"type": "uint24"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "liquidity", "outputs": [{"type": "uint128"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "slot0", "outputs": [
        {"name": "sqrtPriceX96", "type": "uint160"},
        {"name": "tick", "type": "int24"},
        {"name": "observationIndex", "type": "uint16"},
        {"name": "observationCardinality", "type": "uint16"},
        {"name": "observationCardinalityNext", "type": "uint16"},
        {"name": "unlocked", "type": "bool"},
    ], "stateMutability": "view", "type": "function"},
]

ERC20_ABI = [
    {"constant": True, "inputs": [], "name": "decimals", "outputs": [{"name": "", "type": "uint8"}], "type": "function"},
    {"constant": True, "inputs": [{"name": "who", "type": "address"}], "name": "balanceOf",
     "outputs": [{"name": "", "type": "uint256"}], "type": "function"},
]


@dataclass
class Position:
    """Текущая LP-позиция на Aerodrome Slipstream."""
    lower_price: float
    upper_price: float
    current_price: float
    liquidity: int
    in_range: bool
    is_demo: bool = False
    amount_token0: float = 0.0  # USDC
    amount_token1: float = 0.0  # cbBTC
    value_token0_usd: float = 0.0
    value_token1_usd: float = 0.0
    total_value_usd: float = 0.0


# Зафиксированный демо-диапазон — тот же паттерн, что в orca-lp-bot: создаётся
# один раз, не гоняется за живой ценой на каждом вызове (иначе позиция никогда
# не сможет "выйти" из диапазона — баг, найденный и исправленный в Orca-версии
# в самом начале того проекта, тут учтён сразу).
_demo_range: dict | None = None
_pool_static_cache: dict[str, dict] = {}


def _get_pool_static_state(w3: Web3, pool) -> dict:
    """Кэш неизменяемых параметров уже развёрнутого пула.

    token0/token1/decimals/tickSpacing не меняются для существующего пула,
    поэтому читаем один раз, чтобы не перегружать RPC.
    """
    pool_addr = getattr(pool, "address", None) or POOL_ADDRESS
    key = Web3.to_checksum_address(pool_addr)
    cached = _pool_static_cache.get(key)
    if cached is not None:
        return cached

    token0_addr = Web3.to_checksum_address(pool.functions.token0().call())
    token1_addr = Web3.to_checksum_address(pool.functions.token1().call())
    token0 = w3.eth.contract(address=token0_addr, abi=ERC20_ABI)
    token1 = w3.eth.contract(address=token1_addr, abi=ERC20_ABI)
    dec0 = token0.functions.decimals().call()
    dec1 = token1.functions.decimals().call()
    tick_spacing = pool.functions.tickSpacing().call()

    cached = {"dec0": dec0, "dec1": dec1, "tick_spacing": tick_spacing}
    _pool_static_cache[key] = cached
    return cached


def _get_web3() -> Web3:
    return Web3(Web3.HTTPProvider(BASE_RPC_URL))


def _get_pool_contract(w3: Web3):
    return w3.eth.contract(address=Web3.to_checksum_address(POOL_ADDRESS), abi=POOL_ABI)


async def _pool_state(w3: Web3, pool) -> dict:
    """Разовое чтение состояния пула: цена, тик, decimals обоих токенов.
    web3.py синхронный, но держим async-обёртку для единообразия с остальным
    ботом (main.py/monitor будет async, как и в orca-lp-bot)."""
    static = _get_pool_static_state(w3, pool)
    dec0 = static["dec0"]
    dec1 = static["dec1"]
    tick_spacing = static["tick_spacing"]
    slot0 = pool.functions.slot0().call()
    sqrt_price_x96, tick = slot0[0], slot0[1]

    # price = token1 за 1 token0 (сырые unit-ы) -> человекочитаемо через decimals.
    # Нам интереснее обратная величина — цена BTC (token1) в USDC (token0), то
    # же соглашение, что и "цена SOL в USDC" в orca-lp-bot.
    raw_price_1_per_0 = (sqrt_price_x96 / (2**96)) ** 2
    price_1_per_0_human = raw_price_1_per_0 * 10 ** (dec0 - dec1)
    price_0_per_1_human = 1 / price_1_per_0_human  # USDC за 1 cbBTC

    return {
        "dec0": dec0,
        "dec1": dec1,
        "tick_spacing": tick_spacing,
        "tick": tick,
        "current_price": price_0_per_1_human,  # USDC за 1 cbBTC (аналог "цена SOL")
    }


def _price_to_tick(price_0_per_1: float, dec0: int, dec1: int) -> int:
    """Обратное преобразование: цена (USDC за 1 cbBTC) -> ближайший tick."""
    import math

    price_1_per_0_human = 1 / price_0_per_1
    raw_price_1_per_0 = price_1_per_0_human / 10 ** (dec0 - dec1)
    return math.floor(math.log(raw_price_1_per_0) / math.log(1.0001))


def _tick_to_price(tick: int, dec0: int, dec1: int) -> float:
    """tick -> цена (USDC за 1 cbBTC)."""
    raw_price_1_per_0 = 1.0001**tick
    price_1_per_0_human = raw_price_1_per_0 * 10 ** (dec0 - dec1)
    return 1 / price_1_per_0_human


def _align_tick(tick: int, tick_spacing: int, rounding: str = "down") -> int:
    """Выравнивает tick к сетке tick_spacing.

    rounding:
      - "down": floor к ближайшему кратному (в сторону -inf)
      - "up": ceil к ближайшему кратному (в сторону +inf)
    """
    import math

    if tick_spacing <= 0:
        raise ValueError("tick_spacing must be positive")

    if rounding == "down":
        return (tick // tick_spacing) * tick_spacing
    if rounding == "up":
        return math.ceil(tick / tick_spacing) * tick_spacing
    raise ValueError("rounding must be 'down' or 'up'")


def _demo_amounts_from_deposit(
    current_price: float, lower_price: float, upper_price: float, deposit_usd: float
) -> tuple[float, float, float, float, float]:
    """Грубая демо-раскладка депозита на USDC/cbBTC — для показа примерного
    состава позиции в статусе, не для реальных транзакций (тот же принцип
    демо-расчёта, что в orca-lp-bot: не точная формула концентрированной
    ликвидности, а прикидка 50/50 с учётом того, в диапазоне цена или нет)."""
    if current_price <= lower_price:
        # Цена cbBTC ниже диапазона — позиция целиком в token1 (cbBTC)
        usdc = 0.0
        btc_usd = deposit_usd
    elif current_price >= upper_price:
        # Цена cbBTC выше диапазона — позиция целиком в token0 (USDC)
        usdc = deposit_usd
        btc_usd = 0.0
    else:
        usdc = deposit_usd / 2
        btc_usd = deposit_usd / 2

    btc_amount = btc_usd / current_price
    return usdc, btc_amount, usdc, btc_usd, usdc + btc_usd


async def get_current_price() -> float:
    """Текущая цена cbBTC в USDC — реальный вызов к реальному пулу на Base."""
    w3 = _get_web3()
    pool = _get_pool_contract(w3)
    state = await _pool_state(w3, pool)
    return state["current_price"]


async def get_position() -> Optional[Position]:
    """Читает реальную цену с реального пула. Позиция — демо (DRY_RUN),
    реальных позиций/транзакций в Фазе 1 ещё нет."""
    if config.is_placeholder(config.POOL_ADDRESS):
        return None

    w3 = _get_web3()
    pool = _get_pool_contract(w3)
    state = await _pool_state(w3, pool)
    current_price = state["current_price"]
    dec0, dec1 = state["dec0"], state["dec1"]
    tick_spacing = state["tick_spacing"]

    if DRY_RUN and DEMO_POSITION:
        global _demo_range
        if _demo_range is None:
            raw_lower = current_price * (1 - config.RANGE_WIDTH_PCT / 100)
            raw_upper = current_price * (1 + config.RANGE_WIDTH_PCT / 100)
            raw_tick_lower = _price_to_tick(raw_lower, dec0, dec1)
            raw_tick_upper = _price_to_tick(raw_upper, dec0, dec1)

            # В UniswapV3-логике lowerTick должен быть выровнен вниз, upperTick — вверх,
            # чтобы диапазон гарантированно покрывал исходные границы. В нашем случае
            # из-за инверсии цены tick для raw_lower может оказаться численно больше tick
            # для raw_upper — поэтому выбираем направление выравнивания по порядку тиков.
            if raw_tick_lower < raw_tick_upper:
                tick_lower = _align_tick(raw_tick_lower, tick_spacing, rounding="down")
                tick_upper = _align_tick(raw_tick_upper, tick_spacing, rounding="up")
            else:
                tick_lower = _align_tick(raw_tick_lower, tick_spacing, rounding="up")
                tick_upper = _align_tick(raw_tick_upper, tick_spacing, rounding="down")
            # _price_to_tick/_tick_to_price уже сами учитывают инверсию (наша
            # "цена BTC в USDC" — это 1/raw_price token1-за-token0), поэтому
            # tick_lower здесь численно БОЛЬШЕ tick_upper (например -63900 vs
            # -65600) — это ожидаемо и ничего не ломает, если не пытаться
            # переставить их ещё раз при обратном переводе в цену. Первая
            # версия кода как раз добавляла лишнюю (уже встроенную) инверсию
            # второй раз и переворачивала диапазон — поймано сразу на первом
            # живом прогоне (2026-07-27): позиция показывала "ВНЕ диапазона"
            # при цене ровно посередине настроенного диапазона.
            _demo_range = {"tick_lower": tick_lower, "tick_upper": tick_upper}

        lower_price = _tick_to_price(_demo_range["tick_lower"], dec0, dec1)
        upper_price = _tick_to_price(_demo_range["tick_upper"], dec0, dec1)

        in_range = lower_price <= current_price <= upper_price
        usdc, btc, usdc_usd, btc_usd, total = _demo_amounts_from_deposit(
            current_price, lower_price, upper_price, DEMO_DEPOSIT_USD
        )
        return Position(
            lower_price=lower_price,
            upper_price=upper_price,
            current_price=current_price,
            liquidity=0,
            in_range=in_range,
            is_demo=True,
            amount_token0=usdc,
            amount_token1=btc,
            value_token0_usd=usdc_usd,
            value_token1_usd=btc_usd,
            total_value_usd=total,
        )

    # Реальная позиция (Фаза 2, ещё не реализовано) — потребует чтения
    # NonfungiblePositionManager по конкретному tokenId.
    return None


def reset_demo_range() -> None:
    global _demo_range
    _demo_range = None
