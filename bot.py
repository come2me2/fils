import asyncio
import os
from typing import Dict, List

from dotenv import load_dotenv
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
MESSAGE_DELAY_SECONDS = float(os.getenv("MESSAGE_DELAY_SECONDS", "1.7"))

# URLs
URL_CLOUD = "https://filsdesign.ru/sofas/cloud"
URL_GOCCI = "https://filsdesign.ru/sofas/gocci"
URL_FLOUS = "https://filsdesign.ru/sofas/flous"
URL_JUNGLE = "https://filsdesign.ru/sofas/jungle"
URL_ALL = "https://filsdesign.ru/sofas"

# Keys for user_data
UD_ANSWERS = "answers"  # List[int]
UD_RESULT = "result"     # str model key

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


def start_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(text="👉 Начать подбор", callback_data="start_quiz")]]
    )


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


async def on_start_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Callback from "Начать подбор"
    query = update.callback_query
    await query.answer()
    context.user_data[UD_ANSWERS] = []
    # Remove the greeting message with the start button
    try:
        await query.message.delete()
    except Exception:
        pass
    await send_q1(update, context)


async def send_q1(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await asyncio.sleep(MESSAGE_DELAY_SECONDS)
    text = (
        "🧩 Вопрос 1:\n"
        "Где будет стоять диван?"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("1️⃣ Просторная гостиная", callback_data="q1_1")],
        [InlineKeyboardButton("2️⃣ Квартира-студия", callback_data="q1_2")],
        [InlineKeyboardButton("3️⃣ Кабинет / офис", callback_data="q1_3")],
        [InlineKeyboardButton("4️⃣ Дом за городом", callback_data="q1_4")],
    ])
    await update.effective_chat.send_message(text, reply_markup=kb)


async def handle_q1(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    choice = int(query.data.split("_")[1])
    context.user_data.setdefault(UD_ANSWERS, []).append(("Q1", choice))
    # Delete current question message
    try:
        await query.message.delete()
    except Exception:
        pass
    await send_q2(update, context)


async def send_q2(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await asyncio.sleep(MESSAGE_DELAY_SECONDS)
    text = (
        "🧩 Вопрос 2:\n"
        "Что для тебя важнее всего?"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("1️⃣ Максимальный комфорт — хочется “утонуть” в мягкости", callback_data="q2_1")],
        [InlineKeyboardButton("2️⃣ Минимализм и четкие формы", callback_data="q2_2")],
        [InlineKeyboardButton("3️⃣ Современный дизайн и вау-эффект", callback_data="q2_3")],
        [InlineKeyboardButton("4️⃣ Много места и модульность", callback_data="q2_4")],
    ])
    await update.effective_chat.send_message(text, reply_markup=kb)


async def handle_q2(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    choice = int(query.data.split("_")[1])
    context.user_data.setdefault(UD_ANSWERS, []).append(("Q2", choice))
    # Delete current question message
    try:
        await query.message.delete()
    except Exception:
        pass
    await send_q3(update, context)


async def send_q3(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await asyncio.sleep(MESSAGE_DELAY_SECONDS)
    text = (
        "🧩 Вопрос 3:\n"
        "Какой стиль тебе ближе?"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("1️⃣ Современный минимализм", callback_data="q3_1")],
        [InlineKeyboardButton("2️⃣ Лофт / урбан", callback_data="q3_2")],
        [InlineKeyboardButton("3️⃣ Современная классика", callback_data="q3_3")],
        [InlineKeyboardButton("4️⃣ Хочу, чтобы выглядел дорого и спокойно", callback_data="q3_4")],
    ])
    await update.effective_chat.send_message(text, reply_markup=kb)


async def handle_q3(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    choice = int(query.data.split("_")[1])
    context.user_data.setdefault(UD_ANSWERS, []).append(("Q3", choice))
    # Delete current question message
    try:
        await query.message.delete()
    except Exception:
        pass
    await send_q4(update, context)


async def send_q4(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await asyncio.sleep(MESSAGE_DELAY_SECONDS)
    text = (
        "🧩 Вопрос 4:\n"
        "Что ты ожидаешь от дивана?"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("1️⃣ Чтобы был мягким, уютным, как облако ☁️", callback_data="q4_1")],
        [InlineKeyboardButton("2️⃣ Чтобы вписался идеально в интерьер — строго и стильно", callback_data="q4_2")],
        [InlineKeyboardButton("3️⃣ Чтобы можно было трансформировать под разные ситуации", callback_data="q4_3")],
        [InlineKeyboardButton("4️⃣ Чтобы стал акцентом комнаты", callback_data="q4_4")],
    ])
    await update.effective_chat.send_message(text, reply_markup=kb)


async def handle_q4(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    choice = int(query.data.split("_")[1])
    context.user_data.setdefault(UD_ANSWERS, []).append(("Q4", choice))
    # Delete current question message
    try:
        await query.message.delete()
    except Exception:
        pass

    model_key = compute_recommendation(context.user_data.get(UD_ANSWERS, []))
    context.user_data[UD_RESULT] = model_key

    await send_result_and_contact(update, context, model_key)


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


async def send_result_and_contact(update: Update, context: ContextTypes.DEFAULT_TYPE, model_key: str) -> None:
    await asyncio.sleep(MESSAGE_DELAY_SECONDS)

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

    await asyncio.sleep(MESSAGE_DELAY_SECONDS)

    contact_text = (
        "Хочешь, подберём ткань и конфигурацию под твой интерьер?\n"
        "Оставь свой контакт, и дизайнер FILS свяжется с тобой лично."
    )
    contact_kb = ReplyKeyboardMarkup(
        [[KeyboardButton(text="📞 Оставить контакт", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await update.effective_chat.send_message(contact_text, reply_markup=contact_kb)


async def on_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    contact = update.message.contact
    user = update.effective_user

    # Acknowledge to user
    await update.effective_chat.send_message(
        "Спасибо! Дизайнер FILS свяжется с тобой в ближайшее время.",
        reply_markup=ReplyKeyboardRemove(),
    )

    # Forward summary to manager
    try:
        answers = context.user_data.get(UD_ANSWERS, [])
        model_key = context.user_data.get(UD_RESULT, "?")
        lines = [
            "Новая заявка из бота FILS Design — подбор дивана:",
            f"Пользователь: {user.full_name} (@{user.username or '-'}; id={user.id})",
            f"Телефон: {contact.phone_number}",
            f"Имя (из контакта): {contact.first_name} {contact.last_name or ''}",
            "",
            "Ответы квиза:",
        ]
        for q, val in answers:
            lines.append(f" - {q}: {val}")
        model = MODELS.get(model_key, {"title": model_key})
        lines.append("")
        lines.append(f"Рекомендация: {model.get('title', model_key)}")
        lines.append(f"Ссылка: {model.get('url', URL_ALL)}")

        manager_chat_id = int(MANAGER_CHAT_ID) if MANAGER_CHAT_ID else None
        if manager_chat_id:
            await context.bot.send_message(chat_id=manager_chat_id, text="\n".join(lines))
    except Exception:
        # Avoid breaking user flow if manager ID misconfigured
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

    return app


def main() -> None:
    app = build_application()
    print("FILS Design quiz bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
