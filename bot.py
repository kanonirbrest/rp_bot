import asyncio
import io
import logging
import os

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
    WebAppInfo,
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

MENU_EXHIBITION = "🎨 Выставка"
MENU_ANNOUNCEMENTS = "📅 Ближайшие анонсы"
MENU_DISCOUNTS = "🏷 Скидки"
MENU_GIVEAWAY = "🎁 Розыгрыш"

MENU_BUTTONS = [MENU_EXHIBITION, MENU_ANNOUNCEMENTS, MENU_DISCOUNTS, MENU_GIVEAWAY]


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [MENU_EXHIBITION, MENU_ANNOUNCEMENTS],
            [MENU_DISCOUNTS, MENU_GIVEAWAY],
        ],
        resize_keyboard=True,
    )


async def send_main_menu(update: Update, text: str) -> None:
    await update.message.reply_text(text, reply_markup=main_menu_keyboard())


def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if await db.user_exists(user.id):
        await send_main_menu(update, f"👋 С возвращением, {user.first_name}! Выбери раздел 👇")
        return

    await db.add_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
    )
    logger.info("Новый пользователь: %s (%s)", user.full_name, user.id)

    keyboard = ReplyKeyboardMarkup(
        [
            [KeyboardButton("📱 Поделиться номером", request_contact=True)],
            [KeyboardButton("Пропустить →")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await update.message.reply_text(
        f"👋 Привет, *{user.first_name}*\\!\n\n"
        "Добро пожаловать в Пространство «Небо Река»\\.\n\n"
        "📲 *Оставь номер телефона и получи:*\n\n"
        "✅ Скидки для участников\n"
        "✅ Анонсы мероприятий первым\n"
        "✅ Участие в розыгрышах\n\n"
        "👇 Нажми кнопку ниже",
        parse_mode="MarkdownV2",
        reply_markup=keyboard,
    )


async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    contact = update.message.contact

    if contact.user_id != user.id:
        return

    await db.save_phone(user.id, contact.phone_number)
    logger.info("Телефон сохранён для %s: %s", user.id, contact.phone_number)

    await send_main_menu(update, "✅ Номер сохранён, спасибо! Выбери раздел 👇")


async def handle_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_main_menu(update, "Хорошо, пропустим. Выбери раздел 👇")


async def handle_exhibition(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎨 *Выставка «Небо Река»*\n\n"
        "📍 11 марта",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "🗺 Открыть карту выставки",
                web_app=WebAppInfo(url="https://kanonirbrest.github.io/rp_bot/")
            )]
        ]),
    )
    await update.message.reply_text("👇", reply_markup=main_menu_keyboard())


async def handle_announcements(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📅 *Ближайшие анонсы*\n\n"
        "🎨 *11 марта — Выставка «Небо река»*\n\n"
        "Открытие выставки, которую нельзя пропустить.\n"
        "Приходи, зови друзей!"
    )
    photo = await db.get_setting("announcement_photo")
    if photo:
        await update.message.reply_photo(
            photo=photo,
            caption=text,
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(),
        )
    else:
        await update.message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(),
        )


async def handle_discounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🏷 *Скидки*\n\n"
        "Актуальные скидки и специальные предложения появятся здесь.",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(),
    )


async def handle_giveaway(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    number = await db.get_giveaway_number(user.id)
    caption = (
        "🎁 *Розыгрыш*\n\n"
        f"Твой номер участника: *№ {number}*\n\n"
        "Следи за объявлениями — победителя определим в прямом эфире!"
    )

    gif = await db.get_setting("giveaway_gif")
    if gif:
        await update.message.reply_animation(
            animation=gif,
            caption=caption,
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(),
        )
    else:
        await update.message.reply_text(
            caption,
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(),
        )


async def cmd_setphoto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    if not update.message.photo:
        await update.message.reply_text(
            "Отправь фото вместе с командой /setphoto (прикрепи картинку и напиши команду в подписи)."
        )
        return

    file_id = update.message.photo[-1].file_id
    await db.set_setting("announcement_photo", file_id)
    await update.message.reply_text("✅ Фото афиши обновлено!")


async def cmd_setgif(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    if not update.message.animation:
        await update.message.reply_text(
            "Отправь GIF с командой /setgif в подписи."
        )
        return

    file_id = update.message.animation.file_id
    await db.set_setting("giveaway_gif", file_id)
    await update.message.reply_text("✅ GIF для розыгрыша обновлён!")


async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    msg = update.message
    user_ids = await db.get_all_user_ids()

    if not user_ids:
        await msg.reply_text("Нет пользователей для рассылки.")
        return

    # определяем тип контента
    text = " ".join(context.args) if context.args else None
    has_photo = bool(msg.photo)
    has_animation = bool(msg.animation)

    if not text and not has_photo and not has_animation:
        await msg.reply_text(
            "Как использовать рассылку:\n\n"
            "• Текст: `/broadcast Ваш текст`\n"
            "• Фото: прикрепи фото, в подписи напиши `/broadcast текст`\n"
            "• GIF: прикрепи гифку, в подписи напиши `/broadcast текст`",
            parse_mode="Markdown",
        )
        return

    caption = msg.caption.replace("/broadcast", "").strip() if msg.caption else None

    status = await msg.reply_text(f"📤 Начинаю рассылку для {len(user_ids)} пользователей...")

    sent, failed = 0, 0
    for user_id in user_ids:
        try:
            if has_photo:
                await context.bot.send_photo(
                    chat_id=user_id,
                    photo=msg.photo[-1].file_id,
                    caption=caption,
                )
            elif has_animation:
                await context.bot.send_animation(
                    chat_id=user_id,
                    animation=msg.animation.file_id,
                    caption=caption,
                )
            else:
                await context.bot.send_message(chat_id=user_id, text=text)
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)

    await status.edit_text(
        f"✅ Рассылка завершена\n\n"
        f"Отправлено: {sent}\n"
        f"Не доставлено: {failed} (заблокировали бота)"
    )


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    stats = await db.get_stats()
    lines = [f"📊 Всего пользователей: *{stats['total']}*\n\nПоследние 5:"]
    for first_name, username, joined_at in stats["recent"]:
        uname = f"@{username}" if username else "—"
        lines.append(f"• {first_name} ({uname}) — {joined_at}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    csv_data = await db.export_csv()
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
    if not config.SUPABASE_URL or not config.SUPABASE_KEY:
        raise RuntimeError("SUPABASE_URL или SUPABASE_KEY не заданы в .env файле")

    async def post_init(application):
        await db.init_db()

    app = Application.builder().token(config.BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("export", cmd_export))
    app.add_handler(CommandHandler("qr", cmd_qr))
    app.add_handler(CommandHandler("setphoto", cmd_setphoto))
    app.add_handler(MessageHandler(filters.PHOTO & filters.CaptionRegex(r"(?i)/setphoto"), cmd_setphoto))
    app.add_handler(CommandHandler("setgif", cmd_setgif))
    app.add_handler(MessageHandler(filters.ANIMATION & filters.CaptionRegex(r"(?i)/setgif"), cmd_setgif))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast))
    app.add_handler(MessageHandler(
        (filters.PHOTO | filters.ANIMATION) & filters.CaptionRegex(r"(?i)/broadcast"),
        cmd_broadcast,
    ))
    app.add_handler(CommandHandler("exhibition", handle_exhibition))
    app.add_handler(CommandHandler("announcements", handle_announcements))
    app.add_handler(CommandHandler("discounts", handle_discounts))
    app.add_handler(CommandHandler("giveaway", handle_giveaway))
    app.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    app.add_handler(MessageHandler(filters.Regex(r"(?i)пропустить|skip"), handle_skip))
    app.add_handler(MessageHandler(filters.Regex(rf"^{MENU_EXHIBITION}$"), handle_exhibition))
    app.add_handler(MessageHandler(filters.Regex(rf"^{MENU_ANNOUNCEMENTS}$"), handle_announcements))
    app.add_handler(MessageHandler(filters.Regex(rf"^{MENU_DISCOUNTS}$"), handle_discounts))
    app.add_handler(MessageHandler(filters.Regex(rf"^{MENU_GIVEAWAY}$"), handle_giveaway))

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
