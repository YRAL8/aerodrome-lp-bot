import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

import config
import aerodrome
from aerodrome import get_position
from telegram_notify import send_telegram_message, format_position_table, format_range_bar

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
# python-telegram-bot использует httpx/httpcore: на INFO они логируют полный URL,
# включая bot token. Держим эти логгеры на WARNING, как в orca-lp-bot.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
log = logging.getLogger(__name__)

out_of_range_since: Optional[datetime] = None
bot_paused = False
bot_frozen = False
_state = aerodrome._load_demo_state() or {}
_oors = _state.get("out_of_range_since")
if isinstance(_oors, str) and _oors:
    try:
        _dt = datetime.fromisoformat(_oors)
        out_of_range_since = _dt if _dt.tzinfo is not None else _dt.replace(tzinfo=timezone.utc)
    except ValueError:
        out_of_range_since = None


async def monitor_position() -> None:
    global out_of_range_since, bot_paused, bot_frozen

    if bot_paused or bot_frozen:
        log.info("Бот на паузе/заморожен (/pauza, /stop) — пропускаю тик")
        return

    try:
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

        now = datetime.now(timezone.utc)
        if not position.in_range and out_of_range_since is None:
            out_of_range_since = now
            aerodrome._update_demo_state(
                {"out_of_range_since": out_of_range_since.replace(microsecond=0).isoformat()}
            )
            since_str = (
                out_of_range_since.replace(microsecond=0).isoformat().replace("+00:00", "")
            )
            log.warning(
                "СОБЫТИЕ: цена вышла из диапазона (с %s UTC).",
                since_str,
            )
            send_telegram_message(
                f"⚠️ <b>Цена вышла за границу!</b>\n"
                f"{format_position_table(position)}\n"
                f"📈 Цена cbBTC: ${position.current_price:,.2f}\n"
                f"{format_range_bar(position)}\n"
                f"Статус: ⚠️ ВНЕ диапазона\n"
                f"Продолжаю наблюдать..."
            )
        elif position.in_range and out_of_range_since is not None:
            duration_sec = max(0.0, (now - out_of_range_since).total_seconds())
            since = out_of_range_since.replace(microsecond=0).isoformat().replace("+00:00", "")
            out_of_range_since = None
            aerodrome._update_demo_state({"out_of_range_since": None})
            log.info(
                "СОБЫТИЕ: цена вернулась в диапазон (вне диапазона %.0f сек, с %s UTC).",
                duration_sec,
                since,
            )
            send_telegram_message(
                f"✅ <b>Цена вернулась в диапазон</b>\n"
                f"{format_position_table(position)}\n"
                f"📈 Цена cbBTC: ${position.current_price:,.2f}\n"
                f"{format_range_bar(position)}\n"
                f"Статус: ✅ в диапазоне\n"
                f"Вне диапазона была {duration_sec:.0f} сек.\n"
                f"Продолжаю мониторинг..."
            )

    except Exception:
        log.exception("Ошибка мониторинга (тик пропущен), продолжу на следующем.")


async def main() -> None:
    log.info("=" * 50)
    log.info(f"Aerodrome LP-бот (Base) | DRY RUN: {config.DRY_RUN}")
    log.info(f"Пул: {config.POOL_ADDRESS}")
    log.info("=" * 50)

    async def _monitor_loop() -> None:
        while True:
            await monitor_position()
            await asyncio.sleep(config.POLL_INTERVAL_SEC)

    tg = None
    app = None
    can_start_telegram = False
    if not config.is_placeholder(config.TELEGRAM_BOT_TOKEN):
        try:
            import telegram_commands as tg
        except Exception as e:
            log.exception("Не удалось импортировать telegram_commands, продолжаю без polling: %s", e)
        else:
            app = tg.build_telegram_app()
            try:
                await app.bot.get_me()
            except Exception as e:
                log.exception(
                    "Telegram токен невалиден или API недоступен, продолжаю без входящих команд: %s",
                    e,
                )
            else:
                can_start_telegram = True

    mode = "DEMO" if config.DRY_RUN else "БОЕВОЙ"
    send_telegram_message(
        f"🤖 <b>Aerodrome LP-бот запущен</b>\n"
        f"Режим: {mode}\n"
        f"Пара: USDC/cbBTC · опрос {config.POLL_INTERVAL_SEC} сек\n"
        f"Пул: <code>{config.POOL_ADDRESS}</code>"
    )

    if can_start_telegram and app is not None and tg is not None:
        try:
            async with app:
                await app.start()
                try:
                    await tg.register_menu_commands(app)
                except Exception as e:
                    log.exception("Не удалось зарегистрировать меню команд: %s", e)
                await app.updater.start_polling()
                log.info("Telegram polling запущен, команды активны: /status /pauza /stop /boevoy")

                monitor_task = asyncio.create_task(_monitor_loop())
                try:
                    while True:
                        await asyncio.sleep(1)
                except (KeyboardInterrupt, SystemExit):
                    log.info("Остановка по сигналу (KeyboardInterrupt/SystemExit).")
                finally:
                    monitor_task.cancel()
                    try:
                        await monitor_task
                    except asyncio.CancelledError:
                        pass
                    await app.updater.stop()
                    await app.stop()
            return
        except Exception as e:
            log.exception("Ошибка запуска Telegram, продолжаю без входящих команд: %s", e)

    if config.is_placeholder(config.TELEGRAM_BOT_TOKEN):
        log.warning("Telegram токен не задан, входящие команды отключены")
    else:
        log.warning("Входящие Telegram-команды отключены из-за ошибки токена или API")
    try:
        await _monitor_loop()
    except (KeyboardInterrupt, SystemExit):
        log.info("Остановка по сигналу (KeyboardInterrupt/SystemExit).")


if __name__ == "__main__":
    asyncio.run(main())
