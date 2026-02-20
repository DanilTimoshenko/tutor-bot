"""
Общие константы, хелперы и главное меню.
"""
import re
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import database as db

logger = logging.getLogger(__name__)

# Ключи пошаговых диалогов
FLOW_KEYS = (
    "add_lesson", "block_slot", "request_slot", "schedule_range_input",
    "homework_help", "lesson_link_input", "blocked_slot_link_input",
    "add_tutor_input", "booking_username_input",
)
KEYBOARD_BACK_TO_MAIN = [[InlineKeyboardButton("🏠 Вернуться на главную", callback_data="main_menu")]]

# Дни недели
DAY_NAMES = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")
DAY_NAMES_FULL = ("понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье")

MSG_ONLY_TUTOR = "Вы зашли как ученик. Команды репетитора доступны только репетиторам. Используйте /lessons и /my."
SCHEDULE_TEXT_MAX = 4090
SCHEDULE_LESSONS_BUTTONS = 25


def _latex_to_plain(text: str) -> str:
    """Заменяет частые LaTeX-обозначения на текст/Unicode для Telegram."""
    t = text
    t = re.sub(r"\\frac\{([^{}]*)\}\{([^{}]*)\}", r"(\1)/(\2)", t)
    t = re.sub(r"\\\((.+?)\\\)", r"\1", t, flags=re.DOTALL)
    t = re.sub(r"\\\[(.+?)\\\]", r"\n\1\n", t, flags=re.DOTALL)
    t = re.sub(r"\^\{([^{}]*)\}", r"^\1", t)
    t = re.sub(r"_\{([^{}]*)\}", r"_\1", t)
    for cmd, sym in (
        ("\\cdots", "…"), ("\\ldots", "…"), ("\\cdot", "·"), ("\\times", "×"),
        ("\\equiv", "≡"), ("\\rightarrow", "→"), ("\\leftarrow", "←"),
        ("\\vee", "∨"), ("\\wedge", "∧"), ("\\neg", "¬"), ("\\sqrt", "√"),
        ("\\sum", "∑"), ("\\int", "∫"), ("\\infty", "∞"), ("\\leq", "≤"),
        ("\\geq", "≥"), ("\\neq", "≠"), ("\\pm", "±"), ("\\\\", "\n"),
    ):
        t = t.replace(cmd, sym)
    return t


def _format_homework_reply_for_telegram(text: str) -> tuple[str, str | None]:
    """Конвертирует ответ с блоками кода в HTML для Telegram."""
    def escape_html(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    blocks: list[str] = []
    zw = "\u200b"
    KNOWN_LANGS = frozenset({"python", "py", "javascript", "js", "formula"})
    pattern_multiline = re.compile(r"```(\w*)\s*\n(.*?)```", re.DOTALL)
    pattern_inline = re.compile(r"```([^`\n]+)```")

    def replace_multiline(m: re.Match) -> str:
        lang = (m.group(1) or "").strip().lower()
        code = (m.group(2) or "").strip()
        if lang and lang not in KNOWN_LANGS:
            code = (lang + " " + code).strip()
            lang = ""
        idx = len(blocks)
        label = f"<b>{escape_html('Формула' if lang == 'formula' else lang.capitalize())}</b>\n" if lang else ""
        blocks.append(label + "<pre><code>" + escape_html(code) + "</code></pre>")
        return f"{zw}{idx}{zw}"

    def replace_inline(m: re.Match) -> str:
        code = (m.group(1) or "").strip()
        idx = len(blocks)
        blocks.append("<pre><code>" + escape_html(code) + "</code></pre>")
        return f"{zw}{idx}{zw}"

    temp = pattern_multiline.sub(replace_multiline, text)
    temp = pattern_inline.sub(replace_inline, temp)
    if not blocks:
        return text, None
    temp = escape_html(temp)
    for i, block in enumerate(blocks):
        temp = temp.replace(f"{zw}{i}{zw}", block, 1)
    return temp, "HTML"


def _clear_other_flows(context: ContextTypes.DEFAULT_TYPE, keep: str) -> None:
    for key in FLOW_KEYS:
        if key != keep:
            context.user_data.pop(key, None)


def _tutor_ids(bot_data) -> set:
    return bot_data.get("tutor_user_ids") or {bot_data.get("tutor_user_id")}


def is_tutor(user_id: int, bot_data) -> bool:
    return user_id in _tutor_ids(bot_data)


def is_admin(user_id: int, bot_data) -> bool:
    return user_id == bot_data.get("admin_user_id")


def _build_main_menu_content(
    user_id: int, first_name: str | None, bot_data: dict, user_data: dict | None = None
) -> tuple[str, list]:
    """Текст и клавиатура главного меню. Учитывает view_as_student (тестовый ученик)."""
    title = bot_data.get("bot_title") or "Репетитор"
    text = (
        f"👋 Привет, {first_name or 'друг'}!\n\n"
        f"Я бот записи на уроки — {title}.\n\n"
        "Выберите действие:"
    )

    # Репетитор в режиме «Тестовый ученик» — показываем меню ученика + кнопка выхода
    if user_data and user_data.get("view_as_student") and is_tutor(user_id, bot_data):
        text += "\n\n━━━━━━━━━━━━━━━━━━━━\n👤 Режим тестового ученика (просмотр от лица ученика)"
        keyboard = [
            [InlineKeyboardButton("📅 Записаться на урок", callback_data="student_lessons")],
            [InlineKeyboardButton("📌 Мои записи и слоты", callback_data="student_my")],
            [InlineKeyboardButton("🕐 Записаться на свободное время", callback_data="student_freetime")],
            [InlineKeyboardButton("👤 Репетитор", callback_data="student_tutor")],
        ]
        if bot_data.get("openai_api_key"):
            keyboard.append([InlineKeyboardButton("AITimoshenko'sAtelie", callback_data="student_homework_help")])
        keyboard.append([InlineKeyboardButton("📚 Раздел ЕГЭ", callback_data="student_ege")])
        keyboard.append([InlineKeyboardButton("◀️ Выйти из теста", callback_data="tutor_exit_test_student")])
        return text, keyboard

    # Админ: выбор режима (админ / репетитор / ученик)
    if user_data is not None and is_admin(user_id, bot_data) and user_data.get("admin_mode") is None:
        text = (
            f"👋 Привет, {first_name or 'друг'}!\n\n"
            f"Я бот записи на уроки — {title}.\n\n"
            "Выберите режим:"
        )
        keyboard = [
            [InlineKeyboardButton("👑 Режим админа", callback_data="choose_mode_admin")],
            [InlineKeyboardButton("👩‍🏫 Режим репетитора", callback_data="choose_mode_tutor")],
            [InlineKeyboardButton("👤 Режим ученика (тест)", callback_data="choose_mode_student")],
        ]
        return text, keyboard

    # Админ в режиме «ученик»
    if user_data and is_admin(user_id, bot_data) and user_data.get("admin_mode") == "student":
        keyboard = [
            [InlineKeyboardButton("📅 Записаться на урок", callback_data="student_lessons")],
            [InlineKeyboardButton("📌 Мои записи и слоты", callback_data="student_my")],
            [InlineKeyboardButton("🕐 Записаться на свободное время", callback_data="student_freetime")],
            [InlineKeyboardButton("👤 Репетитор", callback_data="student_tutor")],
        ]
        if bot_data.get("openai_api_key"):
            keyboard.append([InlineKeyboardButton("AITimoshenko'sAtelie", callback_data="student_homework_help")])
        keyboard.append([InlineKeyboardButton("📚 Раздел ЕГЭ", callback_data="student_ege")])
        return text, keyboard

    # Режим репетитора или админа
    if is_tutor(user_id, bot_data):
        mode = user_data.get("admin_mode") if (user_data and is_admin(user_id, bot_data)) else None
        if mode == "admin":
            text += "\n\n━━━━━━━━━━━━━━━━━━━━\n👑 Режим администратора"
            keyboard = [
                [InlineKeyboardButton("➕ Добавить репетитора", callback_data="admin_add_tutor")],
                [InlineKeyboardButton("📥 Скачать БД", callback_data="admin_download_db")],
            ]
        else:
            text += "\n\n━━━━━━━━━━━━━━━━━━━━\n👩‍🏫 Режим репетитора"
            keyboard = [
                [InlineKeyboardButton("✏️ Создать урок", callback_data="tutor_add_lesson")],
                [InlineKeyboardButton("📅 Расписание", callback_data="tutor_schedule")],
                [InlineKeyboardButton("📊 Сводка на сегодня", callback_data="tutor_summary")],
                [InlineKeyboardButton("📬 Заявки на время", callback_data="tutor_freetime_requests")],
                [InlineKeyboardButton("👤 Тестовый ученик", callback_data="tutor_view_as_student")],
            ]
    else:
        keyboard = [
            [InlineKeyboardButton("📅 Записаться на урок", callback_data="student_lessons")],
            [InlineKeyboardButton("📌 Мои записи и слоты", callback_data="student_my")],
            [InlineKeyboardButton("🕐 Записаться на свободное время", callback_data="student_freetime")],
            [InlineKeyboardButton("👤 Репетитор", callback_data="student_tutor")],
        ]
        if bot_data.get("openai_api_key"):
            keyboard.append([InlineKeyboardButton("AITimoshenko'sAtelie", callback_data="student_homework_help")])
        keyboard.append([InlineKeyboardButton("📚 Раздел ЕГЭ", callback_data="student_ege")])
    return text, keyboard


def format_lesson(lesson: dict, with_id: bool = False) -> str:
    parts = [
        f"▫️ {lesson['title']}",
        f"   📅 {lesson['lesson_date']}  ·  🕐 {lesson['lesson_time']}",
        f"   ⏱ {lesson.get('duration_minutes', 60)} мин",
    ]
    if (lesson.get("description") or "").strip():
        parts.append(f"   📝 {(lesson.get('description') or '').strip()}")
    if with_id:
        parts.append(f"   🆔 {lesson['id']}")
    if lesson.get("booked_count") is not None:
        parts.append(f"   👥 записано: {lesson['booked_count']}/{lesson.get('max_students', 1)}")
    return "\n".join(parts)


def parse_date(s: str) -> str | None:
    s = s.strip()
    if re.match(r"\d{4}-\d{2}-\d{2}", s):
        return s
    m = re.match(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", s)
    if m:
        d, mo, y = m.groups()
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    return None


def parse_time(s: str) -> str | None:
    m = re.match(r"(\d{1,2}):(\d{2})", s.strip())
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        if 0 <= h <= 23 and 0 <= mi <= 59:
            return f"{h:02d}:{mi:02d}"
    return None


def parse_max_students(s: str) -> int | None:
    try:
        n = int(s.strip())
        if 1 <= n <= 100:
            return n
    except ValueError:
        pass
    return None


def parse_day_of_week(s: str) -> int | None:
    t = s.strip().lower()
    for i, short in enumerate(DAY_NAMES):
        if t == short or t == DAY_NAMES_FULL[i]:
            return i
    try:
        n = int(t)
        if 0 <= n <= 6:
            return n
    except ValueError:
        pass
    return None


def normalize_slot_time(t: str) -> str:
    parsed = parse_time(t or "")
    return parsed if parsed else (t or "").strip()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    for key in FLOW_KEYS:
        context.user_data.pop(key, None)
    context.user_data.pop("view_as_student", None)
    user = update.effective_user
    if is_admin(user.id, context.bot_data):
        context.user_data.pop("admin_mode", None)
    logger.info(
        "start: user_id=%s, tutor_ids=%s, is_tutor=%s",
        user.id, _tutor_ids(context.bot_data), is_tutor(user.id, context.bot_data),
    )
    text, keyboard = _build_main_menu_content(user.id, user.first_name, context.bot_data, context.user_data)
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    if user.username:
        try:
            await db.update_blocked_slots_user_id(user.username, user.id)
        except Exception as e:
            logger.warning("update_blocked_slots_user_id failed: %s", e, exc_info=True)


async def materials_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    link = context.bot_data.get("materials_channel_link")
    if link:
        await update.message.reply_text(
            "📚 Материалы к урокам\n\nЗдесь можно смотреть конспекты и доп. материалы:\n\n👉 " + link,
        )
    else:
        await update.message.reply_text("Ссылка на материалы пока не добавлена.")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📖 Как записаться на урок\n\n"
        "1️⃣ Нажми /lessons\n2️⃣ Выбери урок и нажми кнопку под ним\n3️⃣ Готово — ты записан\n\n"
        "❌ Отменить запись: /my → выбери урок → «Отменить запись»\n\n📚 Материалы: /materials",
    )


async def clear_chat_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "💬 Как очистить чат с ботом\n\n"
        "Бот не может удалить сообщения за вас. Сделайте так:\n\n"
        "• iPhone/Android: чат с ботом → название бота вверху → «Очистить историю».\n"
        "• Telegram Desktop: правый клик по чату → «Очистить историю».",
    )
