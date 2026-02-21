import io
import logging
import os

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import config
import database as db

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if db.user_exists(user.id):
        await update.message.reply_text(
            f"👋 С возвращением, {user.first_name}!\n"
            "Ты уже зарегистрирован. Используй кнопку ниже, чтобы войти в группу.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Войти в группу", url=config.GROUP_INVITE_LINK)]
            ]),
        )
        return

    db.add_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
    )
    logger.info("Новый пользователь: %s (%s)", user.full_name, user.id)

    keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton("📱 Поделиться номером телефона", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await update.message.reply_text(
        f"👋 Привет, {user.first_name}!\n\n"
        "Рады видеть тебя. Мы сохранили твой контакт.\n\n"
        "Поделись номером телефона, чтобы мы могли связаться с тобой напрямую "
        "(или пропусти этот шаг).",
        reply_markup=keyboard,
    )


async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    contact = update.message.contact

    if contact.user_id != user.id:
        return

    db.save_phone(user.id, contact.phone_number)
    logger.info("Телефон сохранён для %s: %s", user.id, contact.phone_number)

    await update.message.reply_text(
        "✅ Номер сохранён, спасибо!\n\nВступай в нашу группу:",
        reply_markup=ReplyKeyboardRemove(),
    )
    await update.message.reply_text(
        "👇",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Войти в группу", url=config.GROUP_INVITE_LINK)]
        ]),
    )


async def handle_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Хорошо, пропустим. Вступай в группу:",
        reply_markup=ReplyKeyboardRemove(),
    )
    await update.message.reply_text(
        "👇",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Войти в группу", url=config.GROUP_INVITE_LINK)]
        ]),
    )


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    stats = db.get_stats()
    lines = [f"📊 Всего пользователей: *{stats['total']}*\n\nПоследние 5:"]
    for first_name, username, joined_at in stats["recent"]:
        uname = f"@{username}" if username else "—"
        lines.append(f"• {first_name} ({uname}) — {joined_at}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    csv_data = db.export_csv()
    file = io.BytesIO(csv_data.encode("utf-8"))
    file.name = "contacts.csv"
    await update.message.reply_document(document=file, filename="contacts.csv")


async def cmd_qr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    try:
        import qrcode

        bot_username = (await context.bot.get_me()).username
        url = f"https://t.me/{bot_username}?start=qr"

        img = qrcode.make(url)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)

        await update.message.reply_photo(
            photo=buf,
            caption=f"QR-код ведёт на: `{url}`",
            parse_mode="Markdown",
        )
    except ImportError:
        await update.message.reply_text(
            "Установи пакет: pip install qrcode[pil]"
        )


def main():
    if not config.BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не задан в .env файле")
    if not config.GROUP_INVITE_LINK:
        raise RuntimeError("GROUP_INVITE_LINK не задан в .env файле")

    db.init_db()

    app = Application.builder().token(config.BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("export", cmd_export))
    app.add_handler(CommandHandler("qr", cmd_qr))
    app.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    app.add_handler(MessageHandler(filters.Regex(r"(?i)пропустить|skip"), handle_skip))

    webhook_url = config.WEBHOOK_URL
    port = int(os.environ.get("PORT", 8443))

    if webhook_url:
        logger.info("Запуск в режиме webhook: %s", webhook_url)
        app.run_webhook(
            listen="0.0.0.0",
            port=port,
            webhook_url=f"{webhook_url}/webhook",
            url_path="/webhook",
        )
    else:
        logger.info("Запуск в режиме polling")
        app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
