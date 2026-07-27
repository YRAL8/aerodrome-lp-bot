import logging

from telegram import BotCommand, Update
from telegram.ext import Application, CommandHandler, ContextTypes, filters

import aerodrome
import config
from telegram_notify import format_position_table, format_range_bar

log = logging.getLogger(__name__)

_OWNER_COMMANDS = ("status", "pauza", "stop", "boevoy")


def _owner_chat_id() -> int | None:
    if not config.TELEGRAM_CHAT_ID or config.is_placeholder(config.TELEGRAM_CHAT_ID):
        return None
    try:
        return int(config.TELEGRAM_CHAT_ID)
    except ValueError:
        log.error("TELEGRAM_CHAT_ID=%r не число — команды не зарегистрированы", config.TELEGRAM_CHAT_ID)
        return None


async def unauthorized_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    chat_id = chat.id if chat is not None else None
    text = update.effective_message.text if update.effective_message else None
    command = (text.split()[0] if text else "?")
    log.warning("Ignored Telegram command %s from unauthorized chat_id=%s", command, chat_id)


async def register_menu_commands(app: Application) -> None:
    await app.bot.set_my_commands(
        [
            BotCommand("status", "Статус позиции"),
            BotCommand("pauza", "Пауза автоматики"),
            BotCommand("stop", "Полная заморозка"),
            BotCommand("boevoy", "Вернуть в боевой режим"),
        ]
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        position = await aerodrome.get_position()
        if position is None:
            await update.effective_message.reply_text("⏳ Не удалось загрузить позицию")
            return

        mode = "DEMO" if config.DRY_RUN else "БОЕВОЙ"
        status = "✅ в диапазоне" if position.in_range else "⚠️ ВНЕ диапазона"
        text = (
            f"📊 <b>Статус [{mode}]</b>\n"
            f"{format_position_table(position)}\n"
            f"📈 Цена cbBTC: ${position.current_price:,.2f}\n"
            f"{format_range_bar(position)}\n"
            f"   Статус: {status}"
        )
        await update.effective_message.reply_text(text, parse_mode="HTML")
    except Exception as e:
        log.exception("Ошибка /status: %s", e)
        if update.effective_message is not None:
            await update.effective_message.reply_text(f"❌ Ошибка /status: {e!r}")


async def pauza_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    import main

    main.bot_paused = True
    await update.effective_message.reply_text(
        "⏸ Автоматика приостановлена — мониторинг не отправляет уведомления о событиях.\n"
        "Вернуть всё: /boevoy"
    )


async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    import main

    main.bot_frozen = True
    await update.effective_message.reply_text(
        "🛑 Полная заморозка — мониторинг остановлен.\n"
        "Вернуть всё: /boevoy"
    )


async def boevoy_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    import main

    main.bot_paused = False
    main.bot_frozen = False
    await update.effective_message.reply_text("⚔️ Боевой режим — мониторинг снова работает.")


def build_telegram_app() -> Application:
    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    owner_id = _owner_chat_id()
    if owner_id is None:
        log.error("TELEGRAM_CHAT_ID не задан/плейсхолдер/некорректен — команды не зарегистрированы")
        return app

    owner_chat = filters.Chat(chat_id=owner_id)
    app.add_handler(CommandHandler("status", status_command, filters=owner_chat))
    app.add_handler(CommandHandler("pauza", pauza_command, filters=owner_chat))
    app.add_handler(CommandHandler("stop", stop_command, filters=owner_chat))
    app.add_handler(CommandHandler("boevoy", boevoy_command, filters=owner_chat))

    app.add_handler(
        CommandHandler(
            list(_OWNER_COMMANDS),
            unauthorized_command,
            filters=~owner_chat,
        )
    )
    return app

