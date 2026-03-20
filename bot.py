import asyncio
import io
import logging
import os
import re

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
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
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

# ── Bottom keyboard ────────────────────────────────────────────────
MENU_MAIN    = "🏠 Главное меню"
MENU_OFFERS  = "💝 Специальные предложения"
MENU_CONTACT = "📞 Связаться с нами"
MENU_REVIEW  = "⭐ Оставить отзыв"

# ── Review conversation states ─────────────────────────────────────
SELECT_PROJECT, RATE_PROJECT, ENTER_EMAIL, ENTER_TEXT = range(4)

# ── Constants ──────────────────────────────────────────────────────
TICKET_URL   = "https://www.ticketpro.by/raznoe/neboreka---planeta-posle-shuma/"
ABOUT_URL    = "https://dei.by/about"
YANDEX_URL   = "https://yandex.ru/navi/org/37468561319?si=g47c3yvm4mfkntjk53aud05zg8"
PHONE        = "+375447383333"
TG_USERNAME  = "DEI_by_RP"
MAP_BASE_URL = "https://razman-production.netlify.app/"

PROJECTS = [
    "Небо.Река 2026",
    "Дом Рождества 3.0",
    "Путь.Напряжение",
    "Небо.Река 2025",
    "Дом Рождества 2.0",
    "Дом Рождества 1.0",
]

ZONE_NAMES = {
    1: "Луч с управлением",
    2: "Письмо вспышка",
    3: "Сколько лаванды ты весишь",
    4: "Хождение по воде",
}

# ── Keyboards ──────────────────────────────────────────────────────
def bottom_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[MENU_MAIN, MENU_OFFERS], [MENU_CONTACT, MENU_REVIEW]],
        is_persistent=True,
        resize_keyboard=True,
    )


def main_menu_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('🎨 Выставка "Небо.Река"',       callback_data="cb_exhibition")],
        [InlineKeyboardButton("🗺 Карта выставки",              web_app=WebAppInfo(url=MAP_BASE_URL))],
        [InlineKeyboardButton("💝 Специальные предложения",     callback_data="cb_offers")],
        [InlineKeyboardButton("📅 Ближайшие анонсы",            callback_data="cb_announcements")],
        [InlineKeyboardButton("🎁 Подарочные сертификаты",      callback_data="cb_certificates")],
        [InlineKeyboardButton("❓ Часто задаваемые вопросы",    callback_data="cb_faq")],
        [InlineKeyboardButton("📞 Связаться с нами",            callback_data="cb_contact")],
        [InlineKeyboardButton("⭐ Оставить отзыв",              callback_data="review_start")],
        [InlineKeyboardButton("ℹ️ О RAZMAN production",         callback_data="cb_about")],
    ])


def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


# ── Helpers ────────────────────────────────────────────────────────
async def _send_main_menu_msg(update: Update):
    text = (
        "Ты в деле! RAZMAN production приветствует тебя в Клубе друзей!\n\n"
        "Нажми на нужное действие 👇🏻"
    )
    try:
        photo = await db.get_setting("main_photo")
    except Exception:
        photo = None
    if photo:
        await update.effective_message.reply_photo(
            photo=photo, caption=text, reply_markup=main_menu_inline()
        )
    else:
        await update.effective_message.reply_text(text, reply_markup=main_menu_inline())


def _map_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🗺 Карта выставки", web_app=WebAppInfo(url=MAP_BASE_URL))],
    ])


def _phone_request_keyboard(is_retry: bool = False) -> ReplyKeyboardMarkup:
    skip_text = "Нет, не хочу" if is_retry else "Пропустить →"
    return ReplyKeyboardMarkup(
        [[KeyboardButton("📱 Поделиться номером", request_contact=True)],
         [KeyboardButton(skip_text)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


async def _check_phone_gate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Проверяет, есть ли номер телефона. Если нет — показывает запрос и возвращает False."""
    phone = await db.get_phone(update.effective_user.id)
    if phone:
        return True
    context.user_data["phone_stage"] = "offers_1"
    await update.effective_message.reply_text(
        "💝 Специальные предложения доступны только для участников клуба.\n\n"
        "Поделись номером телефона, чтобы продолжить:",
        reply_markup=_phone_request_keyboard(is_retry=False),
    )
    return False


async def _send_offers_text(update: Update):
    await update.effective_message.reply_text(
        "🎁 Действующие акции:\n\n"
        "1. Скидка 20% на билеты студентам и школьникам от 12 лет в будние дни "
        "(при предъявлении подтверждающего документа)\n\n"
        "2. Скидка 10% на билеты многодетным семьям "
        "(при предъявлении удостоверения)\n\n"
        "3. При покупке 5 и более билетов — 1 полёт на качелях включён в стоимость\n\n"
        "4. Скидка 5% на билеты в одном чеке имениннику в день его рождения, "
        "а также 3 дня после (при предъявлении паспорта)\n\n"
        "Акции не суммируются, вы выбираете ту акцию, которая вам наиболее подходит.",
    )


# ── Onboarding ─────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if await db.user_exists(user.id):
        phone = await db.get_phone(user.id)
        if phone:
            await update.message.reply_text(
                f"👋 С возвращением, {user.first_name}!",
                reply_markup=bottom_keyboard(),
            )
            await _send_main_menu_msg(update)
            return

    if not await db.user_exists(user.id):
        await db.add_user(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
        )
        logger.info("Новый пользователь: %s (%s)", user.full_name, user.id)

    keyboard = _phone_request_keyboard(is_retry=False)
    context.user_data["phone_stage"] = "onboarding_1"
    await update.message.reply_text(
        f"👋 Привет, {user.first_name}!\n\n"
        "Добро пожаловать в Клуб друзей RAZMAN production.\n\n"
        "📲 Поделись контактом и получи:\n\n"
        "✅ Скидки для участников\n"
        "✅ Анонсы мероприятий первым\n\n"
        "👇 Нажми кнопку ниже",
        reply_markup=keyboard,
    )


async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    contact = update.message.contact

    if contact.user_id != user.id:
        return

    await db.save_phone(user.id, contact.phone_number)
    logger.info("Телефон сохранён для %s: %s", user.id, contact.phone_number)
    context.user_data.pop("phone_stage", None)

    await update.message.reply_text(
        "Спасибо, запишем тебя в телефонную книгу Razman Production — "
        "теперь мы точно стали друзьями 🙂",
        reply_markup=bottom_keyboard(),
    )
    await _send_offers_text(update)
    await _send_main_menu_msg(update)


async def handle_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stage = context.user_data.get("phone_stage", "")

    if stage == "onboarding_1":
        context.user_data["phone_stage"] = "onboarding_2"
        await update.message.reply_text(
            "Без номера телефона некоторые функции клуба будут недоступны.\n\n"
            "Поделишься контактом?",
            reply_markup=_phone_request_keyboard(is_retry=True),
        )
        return

    if stage == "offers_1":
        context.user_data["phone_stage"] = "offers_2"
        await update.message.reply_text(
            "Без подтверждённого номера раздел специальных предложений будет закрыт.\n\n"
            "Поделишься контактом?",
            reply_markup=_phone_request_keyboard(is_retry=True),
        )
        return

    context.user_data.pop("phone_stage", None)
    await update.message.reply_text(
        "Хорошо, пропустим!", reply_markup=bottom_keyboard()
    )
    await _send_main_menu_msg(update)


async def handle_final_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки «Нет, не хочу» — финальный отказ от номера."""
    stage = context.user_data.pop("phone_stage", "")

    if "offers" in stage:
        await update.message.reply_text(
            "Раздел специальных предложений доступен только для участников клуба "
            "с подтверждённым номером телефона.",
            reply_markup=bottom_keyboard(),
        )
        return

    # onboarding_2 или любой другой контекст — пропускаем в главное меню
    await update.message.reply_text(
        "Хорошо, пропустим!", reply_markup=bottom_keyboard()
    )
    await _send_main_menu_msg(update)


# ── Bottom menu handlers ───────────────────────────────────────────
async def handle_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send_main_menu_msg(update)


async def handle_offers_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _check_phone_gate(update, context):
        return
    await _send_offers_text(update)


async def handle_contact_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"📞 Связаться с нами\n\n{PHONE}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✈️ Написать в ТГ", url=f"https://t.me/{TG_USERNAME}")],
        ]),
    )


# ── Section senders (reused by inline callbacks and slash commands) ─
async def _send_exhibition(message):
    text = (
        "«НЕБО.РЕКА» Планета после шума — иммерсивная медиа-выставка "
        "и один из самых масштабных арт-проектов страны.\n\n"
        "Команда Razman Production создала на площади 2300 м² в окружении 500 тонн воды "
        "уникальный мир, где природа вдохновляет, технологии удивляют, живая музыка трогает.\n\n"
        "«Небо.Река» выключает городскую «громкость» и возвращает чувствительность — "
        "даёт возможность остановиться, выдохнуть и прожить редкий опыт присутствия «здесь и сейчас».\n\n"
        "📅 21 марта — 23 августа\n"
        "📍 DEI (Дом Экспериментального Искусства)\n"
        "Минск, пр-т. Машерова 15/1\n\n"
        "Подробности и билеты на сайте:"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎟 Купить билет", url=TICKET_URL)],
    ])
    try:
        photo = await db.get_setting("exhibition_photo")
    except Exception:
        photo = None
    if photo:
        await message.reply_photo(photo=photo, caption=text, reply_markup=kb)
    else:
        await message.reply_text(text, reply_markup=kb)


async def _send_announcements(message):
    text = (
        "Ближайшие анонсы 📅\n\n"
        "Следи за обновлениями — скоро здесь появится информация о новых событиях!"
    )
    try:
        photo = await db.get_setting("announcement_photo")
    except Exception as e:
        logger.error("get_setting announcement_photo failed: %s", e)
        photo = None
    try:
        if photo:
            await message.reply_photo(photo=photo, caption=text)
        else:
            await message.reply_text(text)
    except Exception as e:
        logger.error("_send_announcements reply failed: %s", e)


async def _send_certificates(message):
    text = (
        "Подарочные сертификаты 🎁\n\n"
        "Самый лучший подарок — это впечатления! А если точная дата пока неизвестна, "
        "мы сохраним её в секрете до нужного момента.\n\n"
        "Приобретайте в кассе билеты с открытой датой на выставку «Небо.Река», "
        "которые мы упакуем в красивый подарочный конверт, "
        "чтобы момент дарения уже стал особенным ❤️"
    )
    try:
        photo = await db.get_setting("cert_photo")
    except Exception:
        photo = None
    if photo:
        await message.reply_photo(photo=photo, caption=text)
    else:
        await message.reply_text(text)


async def _send_giveaway(message, user):
    try:
        number = await db.get_giveaway_number(user.id)
        gif = await db.get_setting("giveaway_gif")
    except Exception as e:
        logger.error("_send_giveaway db failed: %s", e)
        number = None
        gif = None

    if number:
        caption = (
            f"🎰 Розыгрыш\n\n"
            f"Твой номер участника: № {number}\n\n"
            "Следи за объявлениями — победителя определим в прямом эфире!"
        )
    else:
        caption = "🎰 Розыгрыш\n\nИнформация о текущих розыгрышах и условия участия будут здесь."

    if gif:
        await message.reply_animation(animation=gif, caption=caption)
    else:
        await message.reply_text(caption)


# ── Slash-command shortcuts ────────────────────────────────────────
async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send_main_menu_msg(update)

async def cmd_offers_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _check_phone_gate(update, context):
        return
    await _send_offers_text(update)

async def cmd_contact_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"📞 Связаться с нами\n\n{PHONE}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✈️ Написать в ТГ", url=f"https://t.me/{TG_USERNAME}")],
        ]),
    )

async def cmd_exhibition_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send_exhibition(update.effective_message)

async def cmd_announcements_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send_announcements(update.effective_message)

async def cmd_certificates_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send_certificates(update.effective_message)

async def cmd_faq_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(FAQ_LIST_TEXT, reply_markup=FAQ_KB)

async def cmd_giveaway_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send_giveaway(update.effective_message, update.effective_user)

async def cmd_map_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🗺 Карта выставки",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Открыть карту", web_app=WebAppInfo(url=MAP_BASE_URL))],
        ]),
    )

async def cmd_about_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send_about(update.effective_message)


# ── Inline button callbacks ────────────────────────────────────────
async def cb_exhibition(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await _send_exhibition(query.message)


async def cb_offers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not await _check_phone_gate(update, context):
        return
    await _send_offers_text(update)


async def cb_announcements(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await _send_announcements(query.message)


async def cb_certificates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await _send_certificates(query.message)


# ── FAQ ────────────────────────────────────────────────────────────
FAQ_ANSWERS = {
    "faq_buy": (
        "Где и как купить билет 🎟\n\n"
        "Есть три варианта покупки билетов:\n"
        "• на сайте dei.by\n"
        "• в кассе билетного оператора Ticketpro\n"
        "• в кассе перед посещением\n\n"
        "Обращаем внимание, что количество проданных билетов в час ограничено, "
        "поэтому может возникнуть ситуация, что придётся ожидать на входе.\n\n"
        "Рекомендуем приобретать билеты заранее на конкретную дату и время 🤍"
    ),
    "faq_return": (
        "Вернуть / обменять билет 🔄\n\n"
        "Возврат билетов осуществляется в кассе по адресу:\n"
        "Минск, пр. Машерова, 15/1 (вход со двора).\n\n"
        "Возврат возможен не менее чем за 24 часа до начала сеанса.\n\n"
        "Если вы хотите перенести ваш визит, просим связаться с оператором:"
    ),
    "faq_notreceived": (
        "Билеты не пришли на почту 📧\n\n"
        "Билеты после оплаты приходят в течение часа.\n\n"
        "Если прошло больше часа — проверьте папку «Спам» в почтовом ящике.\n\n"
        "Если это не помогло, обратитесь в службу поддержки билетного оператора, "
        "у которого вы приобретали билет."
    ),
    "faq_gift": (
        "Купить билет в подарок 🎁\n\n"
        "У нас в кассе можно приобрести билет с открытой датой, "
        "который мы упакуем в красивый подарочный конверт."
    ),
    "faq_cantbuy": (
        "Не могу купить билет ❌\n\n"
        "— Не работает ссылка?\n"
        "Скорее всего мы уже знаем о проблеме и стараемся оперативно её устранить.\n\n"
        "— Нет билетов в наличии?\n"
        "Скорее всего вы не нажали на цветной прямоугольник необходимой категории билета "
        "(взрослый/детский/льготный).\n\n"
        "Если проблема не решилась — свяжитесь с нами:"
    ),
    "faq_print": (
        "Нужно ли печатать билет? 🖨\n\n"
        "Билет печатать не обязательно.\n"
        "Можно показать в электронном виде на входе."
    ),
}

FAQ_WITH_CONTACT = {"faq_return", "faq_cantbuy"}


FAQ_LIST_TEXT = "❓ Часто задаваемые вопросы\n\nВыбери вопрос:"

FAQ_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("🎟 Где и как купить билет",     callback_data="faq_buy")],
    [InlineKeyboardButton("🔄 Вернуть / обменять билет",  callback_data="faq_return")],
    [InlineKeyboardButton("📧 Билеты не пришли на почту", callback_data="faq_notreceived")],
    [InlineKeyboardButton("🎁 Купить билет в подарок",    callback_data="faq_gift")],
    [InlineKeyboardButton("❌ Не могу купить билет",      callback_data="faq_cantbuy")],
    [InlineKeyboardButton("🖨 Нужно ли печатать билет?",  callback_data="faq_print")],
])


async def cb_faq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        await query.edit_message_text(FAQ_LIST_TEXT, reply_markup=FAQ_KB)
    except Exception:
        await query.message.reply_text(FAQ_LIST_TEXT, reply_markup=FAQ_KB)


async def cb_faq_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    key = query.data
    text = FAQ_ANSWERS.get(key, "Ответ не найден.")
    if key in FAQ_WITH_CONTACT:
        text += f"\n\n{PHONE}"
    buttons = [
        [InlineKeyboardButton("← Назад к вопросам", callback_data="cb_faq")],
    ]
    if key in FAQ_WITH_CONTACT:
        buttons.insert(0, [
            InlineKeyboardButton("✈️ Написать в ТГ", url=f"https://t.me/{TG_USERNAME}"),
        ])
    try:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as e:
        logger.error("cb_faq_item edit failed: %s", e)
        await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def cb_giveaway(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await _send_giveaway(query.message, query.from_user)


async def cb_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        f"📞 Связаться с нами\n\n{PHONE}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✈️ Написать в ТГ", url=f"https://t.me/{TG_USERNAME}")],
        ]),
    )


async def _send_about(message):
    text = (
        "О RAZMAN production ℹ️\n\n"
        "Razman Production — команда, которая создаёт масштабные иммерсивные арт-проекты "
        "на стыке технологий, природы и живого искусства.\n\n"
        "Наши проекты — это пространства, где каждый может остановиться, "
        "почувствовать и пережить что-то настоящее."
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌐 Сайт RAZMAN production", url=ABOUT_URL)],
    ])
    try:
        photo = await db.get_setting("about_photo")
    except Exception:
        photo = None
    if photo:
        await message.reply_photo(photo=photo, caption=text, reply_markup=kb)
    else:
        await message.reply_text(text, reply_markup=kb)


async def cb_about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await _send_about(query.message)


# ── Review conversation ────────────────────────────────────────────
async def review_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(p, callback_data=f"proj_{i}")]
        for i, p in enumerate(PROJECTS)
    ])
    await update.effective_message.reply_text(
        "Спасибо, что не прошли мимо! Ваша обратная связь — самый честный способ сделать "
        "будущие проекты лучше и комфортнее. Поделитесь своими мыслями и предложениями — "
        "ваше мнение бесценно! 🙏\n\n"
        "Мы растём благодаря тебе 🌱 Расскажи, как прошел твой день на проекте: "
        "что понравилось, а что стоит доработать? Мы слушаем, и становимся лучше ❤️\n\n"
        "Выбери проект:",
        reply_markup=kb,
    )
    return SELECT_PROJECT


async def review_select_project(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    idx = int(query.data.replace("proj_", ""))
    project = PROJECTS[idx]
    context.user_data["review_project"] = project
    context.user_data["review_proj_idx"] = idx

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐⭐⭐⭐⭐  Отлично — 5", callback_data="rate_5")],
        [InlineKeyboardButton("⭐⭐⭐⭐  Хорошо — 4",   callback_data="rate_4")],
        [InlineKeyboardButton("⭐⭐⭐  Так себе — 3",   callback_data="rate_3")],
        [InlineKeyboardButton("⭐⭐  Плохо — 2",        callback_data="rate_2")],
        [InlineKeyboardButton("⭐  Ужасно — 1",         callback_data="rate_1")],
    ])
    try:
        photo = await db.get_setting(f"proj_photo_{idx}")
    except Exception:
        photo = None
    text = f"Просим оценить {project}:"
    if photo:
        await query.message.reply_photo(photo=photo, caption=text, reply_markup=kb)
    else:
        await query.message.reply_text(text, reply_markup=kb)
    return RATE_PROJECT


async def review_rate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    rating = int(query.data.replace("rate_", ""))
    context.user_data["review_rating"] = rating

    if rating >= 4:
        await query.message.reply_text(
            "От Вашей оценки на душе стало теплее! Поделитесь впечатлениями подробнее: "
            "что тронуло, удивило, порадовало? Мы впитываем все ваши эмоции и открыты к новым идеям!\n\n"
            "➡️ Пожалуйста, оставьте отзыв на Яндекс Картах — это займёт пару минут, но для нас очень важно! 🙏\n"
            "Благодарим, что были с нами! Ждём новых встреч! 🤍",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📍 Отзыв на Яндекс Картах", url=YANDEX_URL)]
            ]),
        )
        await query.message.reply_text("Введите текст отзыва:")
        return ENTER_TEXT

    await query.message.reply_text(
        "Оставьте свой контактный e-mail (по желанию, если нужно связаться для уточнений).\n\n"
        "Введите e-mail или нажмите «Пропустить»:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Пропустить →", callback_data="skip_email")]
        ]),
    )
    return ENTER_EMAIL


async def review_enter_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        context.user_data["review_email"] = None
        msg = update.callback_query.message
    else:
        context.user_data["review_email"] = update.message.text.strip()
        msg = update.message
    await msg.reply_text("Введите текст отзыва:")
    return ENTER_TEXT


async def review_enter_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    review_text = update.message.text.strip()
    user = update.effective_user
    project = context.user_data.get("review_project", "—")
    rating  = context.user_data.get("review_rating", 0)
    email   = context.user_data.get("review_email")

    try:
        await db.save_review(user.id, project, rating, email, review_text)
    except Exception as e:
        logger.error("save_review failed: %s", e)

    admin_text = (
        f"📝 Новый отзыв\n\n"
        f"👤 {user.full_name} (@{user.username or '—'})\n"
        f"🎨 Проект: {project}\n"
        f"⭐ Оценка: {rating}/5\n"
        f"📧 Email: {email or '—'}\n\n"
        f"💬 {review_text}"
    )
    for admin_id in config.ADMIN_IDS:
        try:
            await context.bot.send_message(chat_id=admin_id, text=admin_text)
        except Exception:
            pass

    await update.message.reply_text(
        "Благодарим, что были с нами! Ждём новых встреч! 🤍",
        reply_markup=bottom_keyboard(),
    )
    context.user_data.clear()
    return ConversationHandler.END


async def review_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    if update.message:
        await update.message.reply_text("Отзыв отменён.", reply_markup=bottom_keyboard())
    return ConversationHandler.END


# ── Admin commands ─────────────────────────────────────────────────
async def cmd_setphoto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not update.message.photo:
        await update.message.reply_text(
            "Отправь фото с командой /setphoto в подписи (для раздела «Анонсы»)."
        )
        return
    file_id = update.message.photo[-1].file_id
    await db.set_setting("announcement_photo", file_id)
    await update.message.reply_text("✅ Фото анонса обновлено!")


async def cmd_setgif(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not update.message.animation:
        await update.message.reply_text("Отправь GIF с командой /setgif в подписи.")
        return
    file_id = update.message.animation.file_id
    await db.set_setting("giveaway_gif", file_id)
    await update.message.reply_text("✅ GIF для розыгрыша обновлён!")


async def cmd_setmainphoto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not update.message.photo:
        await update.message.reply_text("Отправь фото с командой /setmainphoto в подписи.")
        return
    file_id = update.message.photo[-1].file_id
    await db.set_setting("main_photo", file_id)
    await update.message.reply_text("✅ Фото главного меню обновлено!")


async def cmd_setexhibitionphoto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not update.message.photo:
        await update.message.reply_text("Отправь фото с командой /setexhibitionphoto в подписи.")
        return
    file_id = update.message.photo[-1].file_id
    await db.set_setting("exhibition_photo", file_id)
    await update.message.reply_text("✅ Фото выставки обновлено!")


async def cmd_setcertphoto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not update.message.photo:
        await update.message.reply_text("Отправь фото с командой /setcertphoto в подписи.")
        return
    file_id = update.message.photo[-1].file_id
    await db.set_setting("cert_photo", file_id)
    await update.message.reply_text("✅ Фото сертификатов обновлено!")


async def cmd_setaboutphoto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not update.message.photo:
        await update.message.reply_text("Отправь фото с командой /setaboutphoto в подписи.")
        return
    file_id = update.message.photo[-1].file_id
    await db.set_setting("about_photo", file_id)
    await update.message.reply_text("✅ Фото раздела «О RAZMAN production» обновлено!")


async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    msg = update.message
    user_ids = await db.get_all_user_ids()

    if not user_ids:
        await msg.reply_text("Нет пользователей для рассылки.")
        return

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
                    chat_id=user_id, photo=msg.photo[-1].file_id, caption=caption
                )
            elif has_animation:
                await context.bot.send_animation(
                    chat_id=user_id, animation=msg.animation.file_id, caption=caption
                )
            else:
                await context.bot.send_message(chat_id=user_id, text=text)
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)

    await status.edit_text(
        f"✅ Рассылка завершена\n\nОтправлено: {sent}\nНе доставлено: {failed}"
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


async def cmd_reviews(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    reviews = await db.get_reviews(limit=10)
    if not reviews:
        await update.message.reply_text("Отзывов пока нет.")
        return
    stars = {5: "⭐⭐⭐⭐⭐", 4: "⭐⭐⭐⭐", 3: "⭐⭐⭐", 2: "⭐⭐", 1: "⭐"}
    lines = [f"📝 Последние {len(reviews)} отзывов:\n"]
    for r in reviews:
        rating_str = stars.get(r["rating"], str(r["rating"]))
        email_str = f"\n📧 {r['email']}" if r.get("email") else ""
        lines.append(
            f"{rating_str} {r['project']}\n"
            f"{r['text']}"
            f"{email_str}\n"
            f"🕐 {r['created_at']}\n"
            f"{'—'*20}"
        )
    await update.message.reply_text("\n".join(lines))


async def cmd_export_reviews(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    csv_data = await db.export_reviews_csv()
    file = io.BytesIO(csv_data.encode("utf-8"))
    await update.message.reply_document(document=file, filename="reviews.csv")


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
            photo=buf, caption=f"QR-код ведёт на: `{url}`", parse_mode="Markdown"
        )
    except ImportError:
        await update.message.reply_text("Установи пакет: pip install qrcode[pil]")


async def cmd_qrzone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    try:
        import qrcode
        if not context.args or not context.args[0].isdigit():
            zones = "\n".join(f"{k} — {v}" for k, v in ZONE_NAMES.items())
            await update.message.reply_text(f"Использование: /qrzone <номер>\n\nЛокации:\n{zones}")
            return
        zone_id = int(context.args[0])
        if zone_id not in ZONE_NAMES:
            await update.message.reply_text("Номер локации: 1, 2, 3 или 4")
            return
        bot_username = (await context.bot.get_me()).username
        url = f"https://t.me/{bot_username}/map?startapp={zone_id}"
        img = qrcode.make(url)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        await update.message.reply_photo(
            photo=buf, caption=f"📍 Локация {zone_id}: {ZONE_NAMES[zone_id]}\n\n{url}"
        )
    except ImportError:
        await update.message.reply_text("Установи пакет: pip install qrcode[pil]")


# ── Main ───────────────────────────────────────────────────────────
def main():
    if not config.BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не задан в .env файле")
    if not config.TURSO_URL or not config.TURSO_TOKEN:
        raise RuntimeError("TURSO_URL или TURSO_TOKEN не заданы в .env файле")

    async def post_init(application):
        await db.init_db()
        await application.bot.set_my_commands([
            # — нижняя панель —
            ("menu",          "Главное меню 🏠"),
            ("offers",        "Специальные предложения 💝"),
            ("contact",       "Связаться с нами 📞"),
            ("review",        "Оставить отзыв ⭐️"),
            # — разделы основного меню —
            ("exhibition",    "Выставка «Небо.Река» 🖼"),
            ("announcements", "Ближайшие анонсы 📅"),
            ("certificates",  "Подарочные сертификаты 🎀"),
            ("faq",           "Часто задаваемые вопросы ❓"),
            ("map",           "Карта выставки 🗺"),
            ("about",         "О RAZMAN production ℹ️"),
        ])

    async def error_handler(update, context):
        logger.error("Ошибка: %s", context.error, exc_info=context.error)

    app = Application.builder().token(config.BOT_TOKEN).post_init(post_init).build()
    app.add_error_handler(error_handler)

    # Review ConversationHandler — первым, чтобы перехватывал раньше других
    review_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(review_start, pattern="^review_start$"),
            MessageHandler(filters.Regex(rf"^{re.escape(MENU_REVIEW)}$"), review_start),
        ],
        states={
            SELECT_PROJECT: [
                CallbackQueryHandler(review_select_project, pattern=r"^proj_\d+$"),
            ],
            RATE_PROJECT: [
                CallbackQueryHandler(review_rate, pattern=r"^rate_[1-5]$"),
            ],
            ENTER_EMAIL: [
                CallbackQueryHandler(review_enter_email, pattern="^skip_email$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, review_enter_email),
            ],
            ENTER_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, review_enter_text),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", review_cancel),
            MessageHandler(filters.Regex(r"^Нет, не хочу$"),               handle_final_skip),
            MessageHandler(filters.Regex(rf"^{re.escape(MENU_MAIN)}$"),    handle_main_menu),
            MessageHandler(filters.Regex(rf"^{re.escape(MENU_OFFERS)}$"),  handle_offers_menu),
            MessageHandler(filters.Regex(rf"^{re.escape(MENU_CONTACT)}$"), handle_contact_menu),
            MessageHandler(filters.Regex(rf"^{re.escape(MENU_REVIEW)}$"),  review_cancel),
        ],
    )
    app.add_handler(review_conv)

    # Commands
    app.add_handler(CommandHandler("start",         cmd_start))
    app.add_handler(CommandHandler("menu",          cmd_menu))
    app.add_handler(CommandHandler("exhibition",    cmd_exhibition_cmd))
    app.add_handler(CommandHandler("offers",        cmd_offers_cmd))
    app.add_handler(CommandHandler("announcements", cmd_announcements_cmd))
    app.add_handler(CommandHandler("certificates",  cmd_certificates_cmd))
    app.add_handler(CommandHandler("faq",           cmd_faq_cmd))
    app.add_handler(CommandHandler("giveaway",      cmd_giveaway_cmd))
    app.add_handler(CommandHandler("review",        review_start))
    app.add_handler(CommandHandler("contact",       cmd_contact_cmd))
    app.add_handler(CommandHandler("map",           cmd_map_cmd))
    app.add_handler(CommandHandler("about",         cmd_about_cmd))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("export", cmd_export))
    app.add_handler(CommandHandler("qr", cmd_qr))
    app.add_handler(CommandHandler("qrzone", cmd_qrzone))
    app.add_handler(CommandHandler("setphoto", cmd_setphoto))
    app.add_handler(CommandHandler("setgif", cmd_setgif))
    app.add_handler(CommandHandler("setmainphoto", cmd_setmainphoto))
    app.add_handler(CommandHandler("setexhibitionphoto", cmd_setexhibitionphoto))
    app.add_handler(CommandHandler("setcertphoto", cmd_setcertphoto))
    app.add_handler(CommandHandler("setaboutphoto", cmd_setaboutphoto))
    app.add_handler(MessageHandler(filters.PHOTO & filters.CaptionRegex(r"(?i)/setaboutphoto"), cmd_setaboutphoto))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast))
    app.add_handler(CommandHandler("reviews", cmd_reviews))
    app.add_handler(CommandHandler("exportreviews", cmd_export_reviews))
    app.add_handler(MessageHandler(filters.PHOTO & filters.CaptionRegex(r"(?i)/setphoto"), cmd_setphoto))
    app.add_handler(MessageHandler(filters.PHOTO & filters.CaptionRegex(r"(?i)/setmainphoto"), cmd_setmainphoto))
    app.add_handler(MessageHandler(filters.PHOTO & filters.CaptionRegex(r"(?i)/setexhibitionphoto"), cmd_setexhibitionphoto))
    app.add_handler(MessageHandler(filters.PHOTO & filters.CaptionRegex(r"(?i)/setcertphoto"), cmd_setcertphoto))
    app.add_handler(MessageHandler(filters.ANIMATION & filters.CaptionRegex(r"(?i)/setgif"), cmd_setgif))
    app.add_handler(MessageHandler(
        (filters.PHOTO | filters.ANIMATION) & filters.CaptionRegex(r"(?i)/broadcast"),
        cmd_broadcast,
    ))

    # Inline callbacks
    app.add_handler(CallbackQueryHandler(cb_exhibition,  pattern="^cb_exhibition$"))
    app.add_handler(CallbackQueryHandler(cb_offers,      pattern="^cb_offers$"))
    app.add_handler(CallbackQueryHandler(cb_announcements, pattern="^cb_announcements$"))
    app.add_handler(CallbackQueryHandler(cb_certificates, pattern="^cb_certificates$"))
    app.add_handler(CallbackQueryHandler(cb_faq,         pattern="^cb_faq$"))
    app.add_handler(CallbackQueryHandler(cb_faq_item,    pattern="^faq_"))
    app.add_handler(CallbackQueryHandler(cb_giveaway,    pattern="^cb_giveaway$"))
    app.add_handler(CallbackQueryHandler(cb_contact,     pattern="^cb_contact$"))
    app.add_handler(CallbackQueryHandler(cb_about,       pattern="^cb_about$"))

    # Message handlers
    app.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    app.add_handler(MessageHandler(filters.Regex(r"^Нет, не хочу$"), handle_final_skip))
    app.add_handler(MessageHandler(filters.Regex(r"(?i)пропустить|skip"), handle_skip))
    app.add_handler(MessageHandler(filters.Regex(rf"^{re.escape(MENU_MAIN)}$"),    handle_main_menu))
    app.add_handler(MessageHandler(filters.Regex(rf"^{re.escape(MENU_OFFERS)}$"),  handle_offers_menu))
    app.add_handler(MessageHandler(filters.Regex(rf"^{re.escape(MENU_CONTACT)}$"), handle_contact_menu))

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
