import asyncio
import os
from typing import Dict, List

from dotenv import load_dotenv
from db import upsert_user, touch_user_active, add_submission, update_user_phone
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# Load environment
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
MANAGER_CHAT_ID = os.getenv("MANAGER_CHAT_ID", "")
# Fine-grained delays
QUESTION_DELAY_SECONDS = float(os.getenv("QUESTION_DELAY_SECONDS", os.getenv("MESSAGE_DELAY_SECONDS", "0.0")))
RESULT_DELAY_SECONDS = float(os.getenv("RESULT_DELAY_SECONDS", os.getenv("MESSAGE_DELAY_SECONDS", "0.2")))

# URLs
URL_CLOUD = "https://filsdesign.ru/sofas/cloud"
URL_GOCCI = "https://filsdesign.ru/sofas/gocci"
URL_FLOUS = "https://filsdesign.ru/sofas/flous"
URL_JUNGLE = "https://filsdesign.ru/sofas/jungle"
URL_ALL = "https://filsdesign.ru/sofas"

# Keys for user_data
UD_ANSWERS = "answers"  # List[int]
UD_RESULT = "result"     # str model key
UD_AWAITING_CONTACT = "awaiting_contact"  # bool
UD_CONTACT_RECEIVED = "contact_received"  # bool

MODELS = {
    "CLOUD": {
        "title": "CLOUD",
        "desc": "Тебе подойдёт диван **CLOUD** — невероятно мягкий, будто облако. Создан для расслабления и уюта.",
        "url": URL_CLOUD,
    },
    "GOCCI": {
        "title": "GOCCI",
        "desc": "Твоя модель — **GOCCI**. Лаконичные линии, модульность и идеальная геометрия для современных интерьеров.",
        "url": URL_GOCCI,
    },
    "FLOUS": {
        "title": "FLOUS",
        "desc": "Рекомендуем **FLOUS** — строгий, уверенный диван с мягкой глубокой посадкой. Для тех, кто ценит стиль и комфорт без компромиссов.",
        "url": URL_FLOUS,
    },
    "JUNGLE": {
        "title": "JUNGLE",
        "desc": "Идеальный вариант — **JUNGLE**. Низкий, широкий и невероятно комфортный диван для отдыха и общения.",
        "url": URL_JUNGLE,
    },
}


async def _ack_and_cleanup(query) -> None:
    """Best-effort: acknowledge tap by editing message text and removing keyboard.
    If editing text fails, try removing just the keyboard. If that fails, try deleting.
    """
    # Try edit text + remove keyboard
    try:
        await query.edit_message_text("Принято ✅")
        return
    except Exception:
        pass
    # Try only remove keyboard
    try:
        await query.edit_message_reply_markup(reply_markup=None)
        return
    except Exception:
        pass
    # Fallback: delete message
    try:
        await query.message.delete()
    except Exception:
        pass

def start_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(text="👉 Начать подбор", callback_data="start_quiz")]]
    )


def q1_payload():
    text = (
        "🧩 Вопрос 1:\n"
        "Где будет стоять диван?"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("1️⃣ Просторная гостиная", callback_data="q1_1")],
        [InlineKeyboardButton("2️⃣ Студия", callback_data="q1_2")],
        [InlineKeyboardButton("3️⃣ Офис / кабинет", callback_data="q1_3")],
        [InlineKeyboardButton("4️⃣ Загородный дом", callback_data="q1_4")],
    ])
    return text, kb


def q2_payload():
    text = (
        "🧩 Вопрос 2:\n"
        "Что для тебя важнее всего?"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("1️⃣ Максимальный комфорт", callback_data="q2_1")],
        [InlineKeyboardButton("2️⃣ Минимализм, чёткие линии", callback_data="q2_2")],
        [InlineKeyboardButton("3️⃣ Вау‑дизайн", callback_data="q2_3")],
        [InlineKeyboardButton("4️⃣ Модульность, простор", callback_data="q2_4")],
    ])
    return text, kb


def q3_payload():
    text = (
        "🧩 Вопрос 3:\n"
        "Какой стиль тебе ближе?"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("1️⃣ Современный минимализм", callback_data="q3_1")],
        [InlineKeyboardButton("2️⃣ Лофт / урбан", callback_data="q3_2")],
        [InlineKeyboardButton("3️⃣ Современная классика", callback_data="q3_3")],
        [InlineKeyboardButton("4️⃣ Дорого и спокойно", callback_data="q3_4")],
    ])
    return text, kb


def q4_payload():
    text = (
        "🧩 Вопрос 4:\n"
        "Что ты ожидаешь от дивана?"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("1️⃣ Мягкий и уютный ☁️", callback_data="q4_1")],
        [InlineKeyboardButton("2️⃣ Строго и стильно", callback_data="q4_2")],
        [InlineKeyboardButton("3️⃣ Трансформируемый", callback_data="q4_3")],
        [InlineKeyboardButton("4️⃣ Акцент в комнате", callback_data="q4_4")],
    ])
    return text, kb


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    greet = (
        "Привет 👋\n"
        "Это квиз от **FILS Design**.\n"
        "За 1 минуту подберём диван, который идеально впишется в твой интерьер и стиль жизни.\n"
        "Готов начать?"
    )
    await update.effective_chat.send_message(
        greet,
        reply_markup=start_keyboard(),
        parse_mode=ParseMode.MARKDOWN,
    )
    # Store/refresh user in DB (after sending greeting to reduce latency)
    u = update.effective_user
    try:
        upsert_user({
            "telegram_id": u.id,
            "username": u.username,
            "first_name": u.first_name,
            "last_name": u.last_name,
            "language_code": getattr(u, "language_code", None),
            "is_bot": u.is_bot,
        })
        touch_user_active(u.id)
    except Exception:
        pass


async def on_start_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Callback from "Начать подбор"
    query = update.callback_query
    await query.answer(text="Запускаем квиз…")
    context.user_data[UD_ANSWERS] = []
    # Edit greeting message into Q1 to ensure single-tap UX
    text, kb = q1_payload()
    try:
        await query.edit_message_text(text=text, reply_markup=kb)
    except Exception:
        # Fallback to sending new message
        await update.effective_chat.send_message(text, reply_markup=kb)


async def send_q1(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if QUESTION_DELAY_SECONDS > 0:
        await asyncio.sleep(QUESTION_DELAY_SECONDS)
    text, kb = q1_payload()
    await update.effective_chat.send_message(text, reply_markup=kb)


async def handle_q1(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer(text="Выбрано ✅")
    choice = int(query.data.split("_")[1])
    context.user_data.setdefault(UD_ANSWERS, []).append(("Q1", choice))
    # Edit to next question in-place
    text, kb = q2_payload()
    try:
        await query.edit_message_text(text=text, reply_markup=kb)
    except Exception:
        await update.effective_chat.send_message(text, reply_markup=kb)


async def send_q2(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if QUESTION_DELAY_SECONDS > 0:
        await asyncio.sleep(QUESTION_DELAY_SECONDS)
    text, kb = q2_payload()
    await update.effective_chat.send_message(text, reply_markup=kb)


async def handle_q2(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer(text="Выбрано ✅")
    choice = int(query.data.split("_")[1])
    context.user_data.setdefault(UD_ANSWERS, []).append(("Q2", choice))
    # Edit to next question in-place
    text, kb = q3_payload()
    try:
        await query.edit_message_text(text=text, reply_markup=kb)
    except Exception:
        await update.effective_chat.send_message(text, reply_markup=kb)


async def send_q3(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if QUESTION_DELAY_SECONDS > 0:
        await asyncio.sleep(QUESTION_DELAY_SECONDS)
    text, kb = q3_payload()
    await update.effective_chat.send_message(text, reply_markup=kb)


async def handle_q3(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer(text="Выбрано ✅")
    choice = int(query.data.split("_")[1])
    context.user_data.setdefault(UD_ANSWERS, []).append(("Q3", choice))
    # Edit to next question in-place
    text, kb = q4_payload()
    try:
        await query.edit_message_text(text=text, reply_markup=kb)
    except Exception:
        await update.effective_chat.send_message(text, reply_markup=kb)


async def send_q4(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if QUESTION_DELAY_SECONDS > 0:
        await asyncio.sleep(QUESTION_DELAY_SECONDS)
    text, kb = q4_payload()
    await update.effective_chat.send_message(text, reply_markup=kb)


async def handle_q4(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer(text="Выбрано ✅")
    choice = int(query.data.split("_")[1])
    context.user_data.setdefault(UD_ANSWERS, []).append(("Q4", choice))
    # Acknowledge selection in-place
    try:
        await query.edit_message_text(text="Принято ✅")
    except Exception:
        pass

    model_key = compute_recommendation(context.user_data.get(UD_ANSWERS, []))
    context.user_data[UD_RESULT] = model_key
    
    # Save submission
    try:
        user_id = update.effective_user.id
        add_submission(user_id, model_key, context.user_data.get(UD_ANSWERS, []))
        touch_user_active(user_id)
    except Exception:
        pass

    # Send result first
    await send_result(update, context, model_key)
    
    # Then send promo code and contact separately
    await send_promo_code(update, context)
    await send_contact_request(update, context)


def compute_recommendation(answers: List) -> str:
    # answers: list of tuples [("Q1",choice_int), ...]
    score: Dict[str, int] = {"CLOUD": 0, "GOCCI": 0, "FLOUS": 0, "JUNGLE": 0}
    amap = {key: val for key, val in answers}

    # Q1
    q1 = amap.get("Q1")
    if q1 == 1:
        score["CLOUD"] += 1
        score["JUNGLE"] += 1
    elif q1 == 2:
        score["GOCCI"] += 1
    elif q1 == 3:
        score["FLOUS"] += 2
    elif q1 == 4:
        score["JUNGLE"] += 2

    # Q2
    q2 = amap.get("Q2")
    if q2 == 1:
        score["CLOUD"] += 2
        score["JUNGLE"] += 1
    elif q2 == 2:
        score["GOCCI"] += 2
        score["FLOUS"] += 1
    elif q2 == 3:
        score["FLOUS"] += 2
        score["CLOUD"] += 1
    elif q2 == 4:
        score["GOCCI"] += 1
        score["JUNGLE"] += 1
        score["CLOUD"] += 1

    # Q3
    q3 = amap.get("Q3")
    if q3 == 1:
        score["GOCCI"] += 2
        score["CLOUD"] += 1
    elif q3 == 2:
        score["FLOUS"] += 2
    elif q3 == 3:
        score["CLOUD"] += 2
        score["FLOUS"] += 1
    elif q3 == 4:
        score["JUNGLE"] += 2
        score["CLOUD"] += 1

    # Q4
    q4 = amap.get("Q4")
    if q4 == 1:
        score["CLOUD"] += 3
    elif q4 == 2:
        score["GOCCI"] += 2
        score["FLOUS"] += 1
    elif q4 == 3:
        score["GOCCI"] += 2
        score["CLOUD"] += 1
    elif q4 == 4:
        score["FLOUS"] += 2
        score["CLOUD"] += 1

    # pick max; tie-breaker order
    order = ["CLOUD", "GOCCI", "FLOUS", "JUNGLE"]
    best = max(order, key=lambda m: (score[m], -order.index(m)))
    return best


async def send_result(update: Update, context: ContextTypes.DEFAULT_TYPE, model_key: str) -> None:
    # Send result message first
    if RESULT_DELAY_SECONDS > 0:
        await asyncio.sleep(RESULT_DELAY_SECONDS)

    model = MODELS[model_key]
    text = (
        f"🛋 **{model['title']}**\n"
        f"> {model['desc']}\n\n"
        f"[Посмотреть {model['title']} →]({model['url']})"
    )
    link_kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton(text="🔍 Посмотреть все модели", url=URL_ALL)]]
    )
    await update.effective_chat.send_message(text, parse_mode=ParseMode.MARKDOWN, reply_markup=link_kb)


async def send_promo_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await asyncio.sleep(MESSAGE_DELAY_SECONDS)
    
    promo_text = (
        "🎉 **Поздравляем!**\n\n"
        "За прохождение квиза ты получаешь промокод на **5000₽**!\n\n"
        "**Промокод:** `FILS1978`\n\n"
        "💡 *Промокод действует 1 месяц и может быть использован при покупке любого дивана FILS Design.*"
    )
    await update.effective_chat.send_message(promo_text, parse_mode=ParseMode.MARKDOWN)


async def send_contact_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await asyncio.sleep(MESSAGE_DELAY_SECONDS)
    
    contact_text = (
        "🎯 **Хочешь получить персональную консультацию?**\n\n"
        "Наш дизайнер поможет:\n"
        "• Подобрать идеальную ткань и цвет\n"
        "• Рассчитать точные размеры\n"
        "• Ответить на все вопросы о доставке\n"
        "• Оформить заказ со скидкой\n\n"
        "Оставь свой контакт, и мы свяжемся с тобой в течение часа! ⏰"
    )
    
    context.user_data[UD_AWAITING_CONTACT] = True
    context.user_data[UD_CONTACT_RECEIVED] = False
    contact_kb = ReplyKeyboardMarkup(
        [[KeyboardButton(text="📞 Получить консультацию", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await update.effective_chat.send_message(contact_text, reply_markup=contact_kb)


async def on_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Only process if we're expecting a contact
    if not context.user_data.get(UD_AWAITING_CONTACT, False):
        return

    contact = update.message.contact
    user = update.effective_user

    # Mark received to avoid duplicates
    context.user_data[UD_CONTACT_RECEIVED] = True
    context.user_data[UD_AWAITING_CONTACT] = False

    # Acknowledge to user
    try:
        await update.effective_chat.send_message(
            "✅ **Отлично! Заявка принята.**\n\n"
            "🎯 Наш дизайнер свяжется с вами в течение часа и поможет:\n"
            "• Подобрать идеальную конфигурацию\n"
            "• Рассчитать точную стоимость\n"
            "• Ответить на все вопросы\n\n"
            "📞 Ожидайте звонка!",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception:
        pass

    # Forward summary to manager
    await forward_to_manager(context, user_full_name=user.full_name, username=user.username, user_id=user.id,
                             phone=contact.phone_number, name=f"{contact.first_name} {contact.last_name or ''}")
    # Save phone to DB
    try:
        update_user_phone(user.id, contact.phone_number)
        touch_user_active(user.id)
    except Exception:
        pass


async def on_phone_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Accept plain text phone numbers as a fallback
    if not context.user_data.get(UD_AWAITING_CONTACT, False):
        return

    text = (update.message.text or "").strip()
    digits = [c for c in text if c.isdigit()]
    if len(digits) < 7:
        return  # not a phone-like text

    user = update.effective_user
    context.user_data[UD_CONTACT_RECEIVED] = True
    context.user_data[UD_AWAITING_CONTACT] = False

    # Confirm to user
    try:
        await update.effective_chat.send_message(
            "✅ **Отлично! Заявка принята.**\n\n"
            "🎯 Наш дизайнер свяжется с вами в течение часа и поможет:\n"
            "• Подобрать идеальную конфигурацию\n"
            "• Рассчитать точную стоимость\n"
            "• Ответить на все вопросы\n\n"
            "📞 Ожидайте звонка!",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception:
        pass

    # Forward summary to manager
    await forward_to_manager(context, user_full_name=user.full_name, username=user.username, user_id=user.id,
                             phone=text, name=user.full_name)


async def forward_to_manager(context: ContextTypes.DEFAULT_TYPE, *, user_full_name: str, username: str, user_id: int,
                             phone: str, name: str) -> None:
    try:
        answers = context.user_data.get(UD_ANSWERS, [])
        model_key = context.user_data.get(UD_RESULT, "?")
        
        # Get user's latest promo code
        from db import get_user_promo_codes
        user_promos = get_user_promo_codes(user_id)
        latest_promo = user_promos[0] if user_promos else None
        
        lines = [
            "Новая заявка из бота FILS Design — подбор дивана:",
            f"Пользователь: {user_full_name} (@{username or '-'}; id={user_id})",
            f"Телефон: {phone}",
            f"Имя: {name}",
            "",
            "Ответы квиза:",
        ]
        for q, val in answers:
            lines.append(f" - {q}: {val}")
        model = MODELS.get(model_key, {"title": model_key})
        lines.append("")
        lines.append(f"Рекомендация: {model.get('title', model_key)}")
        lines.append(f"Ссылка: {model.get('url', URL_ALL)}")
        
        if latest_promo:
            lines.append("")
            lines.append(f"🎁 Выдан промокод: {latest_promo['code']} (5000₽)")

        manager_chat_id = int(MANAGER_CHAT_ID) if MANAGER_CHAT_ID else None
        if manager_chat_id:
            await context.bot.send_message(chat_id=manager_chat_id, text="\n".join(lines))
    except Exception:
        # Silent failure to not break user UX
        pass


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_chat.send_message(
        "Это бот-линквиз для подбора дивана FILS Design. Нажми 'Начать подбор' чтобы пройти квиз.",
    )


def build_application() -> Application:
    if not BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set. See .env.example")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))

    # Callbacks for quiz
    app.add_handler(CallbackQueryHandler(on_start_quiz, pattern=r"^start_quiz$"))
    app.add_handler(CallbackQueryHandler(handle_q1, pattern=r"^q1_([1-4])$"))
    app.add_handler(CallbackQueryHandler(handle_q2, pattern=r"^q2_([1-4])$"))
    app.add_handler(CallbackQueryHandler(handle_q3, pattern=r"^q3_([1-4])$"))
    app.add_handler(CallbackQueryHandler(handle_q4, pattern=r"^q4_([1-4])$"))

    # Contact messages
    app.add_handler(MessageHandler(filters.CONTACT, on_contact))
    # Fallback: accept phone numbers typed as text
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), on_phone_text))

    return app


def main() -> None:
    app = build_application()
    print("FILS Design quiz bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
