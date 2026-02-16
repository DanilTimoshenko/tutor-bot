"""
Обработчики команд и кнопок бота.
"""
import io
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import ContextTypes

import database as db
import homework_llm

logger = logging.getLogger(__name__)

# Ключи пошаговых диалогов — при старте одного сбрасываем остальные, чтобы не «подхватывать» сообщения
FLOW_KEYS = ("add_lesson", "block_slot", "request_slot", "schedule_range_input", "homework_help")

# Кнопка «Вернуться на главную» — чтобы после любого действия можно было не писать /start
KEYBOARD_BACK_TO_MAIN = [[InlineKeyboardButton("🏠 Вернуться на главную", callback_data="main_menu")]]


def _latex_to_plain(text: str) -> str:
    """Заменяет частые LaTeX-обозначения на текст/Unicode, чтобы формулы читались в Telegram."""
    t = text
    # Дроби \frac{a}{b} → (a)/(b); простой случай без вложенных {}
    t = re.sub(r"\\frac\{([^{}]*)\}\{([^{}]*)\}", r"(\1)/(\2)", t)
    # Инлайн и дисплей: убираем обёртки, оставляем содержимое
    t = re.sub(r"\\\((.+?)\\\)", r"\1", t, flags=re.DOTALL)
    t = re.sub(r"\\\[(.+?)\\\]", r"\n\1\n", t, flags=re.DOTALL)
    # Степени в фигурных скобках: ^{x} → ^x (один символ) или оставляем
    t = re.sub(r"\^\{([^{}]*)\}", r"^\1", t)
    t = re.sub(r"_\{([^{}]*)\}", r"_\1", t)
    # Частые команды → символы
    t = t.replace("\\cdots", "…")
    t = t.replace("\\ldots", "…")
    t = t.replace("\\cdot", "·")
    t = t.replace("\\times", "×")
    t = t.replace("\\equiv", "≡")
    t = t.replace("\\rightarrow", "→")
    t = t.replace("\\leftarrow", "←")
    t = t.replace("\\vee", "∨")
    t = t.replace("\\wedge", "∧")
    t = t.replace("\\neg", "¬")
    t = t.replace("\\sqrt", "√")
    t = t.replace("\\sum", "∑")
    t = t.replace("\\int", "∫")
    t = t.replace("\\infty", "∞")
    t = t.replace("\\leq", "≤")
    t = t.replace("\\geq", "≥")
    t = t.replace("\\neq", "≠")
    t = t.replace("\\pm", "±")
    # Двойные бэкслеши от модели
    t = t.replace("\\\\", "\n")
    return t


def _format_homework_reply_for_telegram(text: str) -> tuple[str, str | None]:
    """
    Конвертирует ответ с блоками кода (```python ... ``` и т.п.) в HTML для Telegram:
    моноширинный блок + подпись языка (как «Python») сверху. Подсветку синтаксиса Telegram не поддерживает.
    """
    def escape_html(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    blocks: list[str] = []
    zw = "\u200b"

    # Группа 1 — язык (python, javascript, ...), группа 2 — код
    pattern = re.compile(r"```(\w*)\s*\n(.*?)```", re.DOTALL)

    def replace_block(m: re.Match) -> str:
        lang = (m.group(1) or "").strip().lower()
        code = m.group(2)
        idx = len(blocks)
        label = ""
        if lang:
            name = "Формула" if lang == "formula" else lang.capitalize()
            label = f"<b>{escape_html(name)}</b>\n"
        blocks.append(label + "<pre><code>" + escape_html(code) + "</code></pre>")
        return f"{zw}{idx}{zw}"
    if not pattern.search(text):
        return text, None
    temp = pattern.sub(replace_block, text)
    temp = escape_html(temp)
    for i, block in enumerate(blocks):
        temp = temp.replace(f"{zw}{i}{zw}", block, 1)
    return temp, "HTML"


def _clear_other_flows(context: ContextTypes.DEFAULT_TYPE, keep: str) -> None:
    """Сбрасывает все пошаговые диалоги, кроме keep. Тогда после «нет»/«спасибо» бот не уйдёт в старый сценарий."""
    for key in FLOW_KEYS:
        if key != keep:
            context.user_data.pop(key, None)


def _tutor_ids(bot_data) -> set:
    return bot_data.get("tutor_user_ids") or {bot_data.get("tutor_user_id")}


def is_tutor(user_id: int, bot_data) -> bool:
    """Репетитор: админ или в списке TUTOR_USER_IDS."""
    return user_id in _tutor_ids(bot_data)


def is_admin(user_id: int, bot_data) -> bool:
    """Только администратор (ADMIN_USER_ID)."""
    return user_id == bot_data.get("admin_user_id")


def _build_main_menu_content(user_id: int, first_name: str | None, bot_data: dict) -> tuple[str, list]:
    """Текст и клавиатура главного меню (для /start и для кнопки «Вернуться на главную»)."""
    title = bot_data.get("bot_title") or "Репетитор"
    text = (
        f"👋 Привет, {first_name or 'друг'}!\n\n"
        f"Я бот записи на уроки — {title}.\n\n"
        "Выберите действие:"
    )
    if is_tutor(user_id, bot_data):
        if is_admin(user_id, bot_data):
            text += "\n\n━━━━━━━━━━━━━━━━━━━━\n👑 Режим администратора"
        else:
            text += "\n\n━━━━━━━━━━━━━━━━━━━━\n👩‍🏫 Режим репетитора"
        keyboard = [
            [InlineKeyboardButton("✏️ Создать урок", callback_data="tutor_add_lesson")],
            [InlineKeyboardButton("📅 Расписание", callback_data="tutor_schedule")],
            [InlineKeyboardButton("📊 Сводка на завтра", callback_data="tutor_summary")],
            [InlineKeyboardButton("👀 Как видят ученики", callback_data="tutor_preview_student")],
            [InlineKeyboardButton("💬 Как очистить чат", callback_data="tutor_clear_chat_help")],
            [InlineKeyboardButton("📥 Скачать БД", callback_data="admin_download_db")],
        ]
        if is_admin(user_id, bot_data):
            keyboard.append([InlineKeyboardButton("➕ Добавить репетитора", callback_data="admin_add_tutor")])
    else:
        keyboard = [
            [InlineKeyboardButton("📅 Записаться на урок", callback_data="student_lessons")],
            [InlineKeyboardButton("📌 Мои записи и слоты", callback_data="student_my")],
            [InlineKeyboardButton("🕐 Записаться на свободное время", callback_data="student_freetime")],
            [InlineKeyboardButton("👤 Репетитор", callback_data="student_tutor")],
        ]
        if bot_data.get("openai_api_key"):
            keyboard.append([InlineKeyboardButton("📝 Помощь с домашкой", callback_data="student_homework_help")])
        keyboard.append([InlineKeyboardButton("📚 Раздел ЕГЭ", callback_data="student_ege")])
    return text, keyboard


MSG_ONLY_TUTOR = "Вы зашли как ученик. Команды репетитора доступны только репетиторам. Используйте /lessons и /my."


def format_lesson(lesson: dict, with_id: bool = False) -> str:
    parts = [
        f"▫️ {lesson['title']}",
        f"   📅 {lesson['lesson_date']}  ·  🕐 {lesson['lesson_time']}",
        f"   ⏱ {lesson.get('duration_minutes', 60)} мин",
    ]
    desc = lesson.get("description") or ""
    if desc.strip():
        parts.append(f"   📝 {desc.strip()}")
    if with_id:
        parts.append(f"   🆔 {lesson['id']}")
    booked = lesson.get("booked_count")
    if booked is not None:
        parts.append(f"   👥 записано: {booked}/{lesson.get('max_students', 1)}")
    return "\n".join(parts)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    for key in FLOW_KEYS:
        context.user_data.pop(key, None)
    user = update.effective_user
    logger.info(
        "start: user_id=%s, tutor_ids=%s, is_tutor=%s",
        user.id,
        _tutor_ids(context.bot_data),
        is_tutor(user.id, context.bot_data),
    )
    text, keyboard = _build_main_menu_content(user.id, user.first_name, context.bot_data)
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def materials_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ссылка на канал с материалами (если настроен репетитором)."""
    link = context.bot_data.get("materials_channel_link")
    if link:
        await update.message.reply_text(
            "📚 Материалы к урокам\n\n"
            "Здесь можно смотреть конспекты и доп. материалы:\n\n"
            f"👉 {link}",
        )
    else:
        await update.message.reply_text("Ссылка на материалы пока не добавлена.")


async def homework_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Обработка вопроса для «Помощь с домашкой». Возвращает True если обработано."""
    if not context.user_data.get("homework_help"):
        return False
    text = (update.message.text or "").strip()
    if len(text) < 2:
        await update.message.reply_text("Напиши вопрос или задание текстом (хотя бы пару слов).")
        return True
    api_key = context.bot_data.get("yandex_api_key") or ""
    folder_id = context.bot_data.get("yandex_folder_id") or ""
    try:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        reply = await homework_llm.ask_homework(text, api_key, folder_id)
    except Exception as e:
        logger.exception("homework_receive: %s", e)
        await update.message.reply_text(
            "Произошла ошибка при запросе. Попробуй ещё раз или нажми /start.",
        )
        await update.message.reply_text(
            "💬 Задай следующий вопрос или нажми /start — вернуться в меню.",
        )
        return True
    if reply:
        reply = _latex_to_plain(reply)
        if len(reply) > 4000:
            reply = reply[:3990] + "\n\n… (ответ обрезан)"
        body, parse_mode = _format_homework_reply_for_telegram(reply)
        await update.message.reply_text(body, parse_mode=parse_mode)
    else:
        if api_key and folder_id:
            await update.message.reply_text(
                "Не удалось получить ответ от Yandex GPT. Возможно, ошибка ключа, квоты или доступа к модели в каталоге. Попробуй позже — репетитор может посмотреть логи в Railway."
            )
        else:
            await update.message.reply_text(
                "Не удалось получить ответ. Проверь, что у репетитора заданы YANDEX_API_KEY и YANDEX_FOLDER_ID в Railway Variables, или попробуй позже.",
            )
    await update.message.reply_text(
        "💬 Задай следующий вопрос или нажми /start — вернуться в меню.",
    )
    return True


async def request_slot_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка ввода даты/времени для «Свободное время»."""
    data = context.user_data.get("request_slot")
    if not data:
        return False
    text = update.message.text.strip()
    step = data.get("step")
    user = update.effective_user
    tutor_id = context.bot_data["tutor_user_id"]

    if step == "date":
        date = parse_date(text)
        if not date:
            await update.message.reply_text("❌ Неверный формат. Пример: 20.02.2025 или 2025-02-20")
            return True
        data["date"] = date
        data["step"] = "time"
        await update.message.reply_text("Напиши удобное время (например 14:00):")
        return True

    if step == "time":
        time = parse_time(text)
        if not time:
            await update.message.reply_text("❌ Неверный формат. Пример: 14:00")
            return True
        data["time"] = time
        context.user_data.pop("request_slot", None)
        student_name = user.first_name or user.username or f"ID{user.id}"
        req = (
            "🕐 Запрос на свободное время\n\n"
            f"👤 {student_name}"
        )
        if user.username:
            req += f" @{user.username}"
        req += f"\n\nЖелаемые дата и время: {data['date']} в {data['time']}\n\nСоздайте урок в /add_lesson — тогда он появится у ученика в «Записаться на урок»."
        try:
            await context.bot.send_message(chat_id=tutor_id, text=req)
        except Exception:
            pass
        await update.message.reply_text(
            "✅ Запрос отправлен репетитору.\n\n"
            "Когда урок будет создан, он появится в разделе «Записаться на урок» — зайди туда и запишись.",
        )
        return True
    return False


async def clear_chat_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Подсказка, как очистить чат с ботом (бот не может удалить сообщения сам)."""
    await update.message.reply_text(
        "💬 Как очистить чат с ботом\n\n"
        "Бот не может удалить сообщения за вас. Сделайте так:\n\n"
        "• **iPhone/Android:** откройте чат с ботом → нажмите на название бота вверху → «Очистить историю» или «Удалить чат».\n\n"
        "• **Telegram Desktop:** правый клик по чату → «Очистить историю».",
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📖 Как записаться на урок\n\n"
        "1️⃣ Нажми /lessons\n"
        "2️⃣ Выбери урок и нажми кнопку под ним\n"
        "3️⃣ Готово — ты записан\n\n"
        "❌ Отменить запись: /my → выбери урок → «Отменить запись»\n\n"
        "📚 Материалы к урокам: /materials",
    )


async def lessons_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lessons = await db.get_upcoming_lessons()
    if not lessons:
        await update.message.reply_text(
            "📭 Пока нет доступных уроков.\n\n"
            "Следи за обновлениями — новые слоты появятся здесь.",
        )
        return
    text = "📋 Доступные уроки\n\nВыбери урок и нажми кнопку записи:\n\n" + "\n\n".join(format_lesson(l) for l in lessons)
    keyboard = []
    for l in lessons:
        booked = l.get("booked_count", 0)
        max_s = l.get("max_students", 1)
        if booked < max_s:
            keyboard.append([
                InlineKeyboardButton(
                    f"✏️ Записаться · {l['title']} ({l['lesson_date']} {l['lesson_time']})",
                    callback_data=f"book_{l['id']}",
                )
            ])
    if not keyboard:
        await update.message.reply_text(text)
        return
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(text, reply_markup=reply_markup)


async def _build_my_bookings_message(user_id: int, username: str):
    """Возвращает (text, keyboard) для «Мои записи» ученика."""
    bookings = await db.get_my_bookings(user_id)
    assigned_slots = await db.get_blocked_slots_for_student(username) if username else []
    if not bookings and not assigned_slots:
        return None, None
    text = "📌 Ваши записи\n\n"
    keyboard = []
    if bookings:
        text += "Уроки:\n\n" + "\n\n".join(format_lesson(l) for l in bookings) + "\n\n"
        for l in bookings:
            keyboard.append([
                InlineKeyboardButton(f"❌ Отменить урок · {l['title']} ({l['lesson_date']})", callback_data=f"cancel_{l['id']}"),
            ])
    if assigned_slots:
        text += "🔒 Закреплённые за вами слоты (репетитор назначил вам это время):\n\n"
        for s in assigned_slots:
            day = DAY_NAMES[s["day_of_week"]]
            text += f"   • {day} {s['lesson_time']} — {s['student_name']}\n"
        text += "\n"
        for s in assigned_slots:
            day = DAY_NAMES[s["day_of_week"]]
            keyboard.append([
                InlineKeyboardButton(f"🔓 Отменить слот · {day} {s['lesson_time']}", callback_data=f"student_unblock_{s['id']}"),
            ])
    keyboard.extend(KEYBOARD_BACK_TO_MAIN)
    return text.strip(), InlineKeyboardMarkup(keyboard)


async def my_bookings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    username = (update.effective_user.username or "").strip()
    text, reply_markup = await _build_my_bookings_message(user_id, username)
    if text is None:
        await update.message.reply_text(
            "📌 У вас пока нет записей.\n\n"
            "Нажми /lessons или кнопку «Записаться на урок», чтобы записаться.",
        )
        return
    await update.message.reply_text(text, reply_markup=reply_markup)


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    data = query.data or ""
    user_id = query.from_user.id
    tutor_id = context.bot_data["tutor_user_id"]

    try:
        await query.answer()
    except Exception as e:
        logger.warning("query.answer failed: %s", e)

    try:
        if data == "main_menu":
            for key in FLOW_KEYS:
                context.user_data.pop(key, None)
            user = query.from_user
            text, keyboard = _build_main_menu_content(user.id, user.first_name, context.bot_data)
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            return

        if data == "student_lessons":
            lessons = await db.get_upcoming_lessons()
            if not lessons:
                await query.edit_message_text(
                    "📭 Пока нет доступных уроков.\n\nСледи за обновлениями — новые слоты появятся здесь.",
                    reply_markup=InlineKeyboardMarkup(KEYBOARD_BACK_TO_MAIN),
                )
                return
            text = "📋 Доступные уроки\n\nВыбери урок и нажми кнопку записи:\n\n" + "\n\n".join(format_lesson(l) for l in lessons)
            keyboard = []
            for l in lessons:
                booked = l.get("booked_count", 0)
                max_s = l.get("max_students", 1)
                if booked < max_s:
                    keyboard.append([
                        InlineKeyboardButton(
                            f"✏️ Записаться · {l['title']} ({l['lesson_date']} {l['lesson_time']})",
                            callback_data=f"book_{l['id']}",
                        )
                    ])
            keyboard.extend(KEYBOARD_BACK_TO_MAIN)
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

        elif data == "student_my":
            user_id = query.from_user.id
            username = (query.from_user.username or "").strip()
            text, reply_markup = await _build_my_bookings_message(user_id, username)
            if text is None:
                await query.edit_message_text(
                    "📌 У вас пока нет записей.\n\n"
                    "Нажми «Записаться на урок», чтобы выбрать урок и записаться.",
                    reply_markup=InlineKeyboardMarkup(KEYBOARD_BACK_TO_MAIN),
                )
                return
            await query.edit_message_text(text, reply_markup=reply_markup)

        elif data == "student_tutor":
            title = context.bot_data.get("bot_title") or "Репетитор"
            msg = f"👤 Репетитор\n\nЗанятия ведёт: {title}."
            if context.bot_data.get("materials_channel_link"):
                msg += f"\n\n📚 Материалы: /materials"
            await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(KEYBOARD_BACK_TO_MAIN))

        elif data == "student_freetime":
            _clear_other_flows(context, "request_slot")
            context.user_data["request_slot"] = {"step": "date"}
            await query.edit_message_text(
                "🕐 Запись на свободное время\n\n"
                "Напиши желаемую дату урока в формате 20.02.2025 или 2025-02-20:",
            )

        elif data == "student_homework_help":
            _clear_other_flows(context, "homework_help")
            context.user_data["homework_help"] = True
            await query.edit_message_text(
                "📝 Помощь с домашкой\n\n"
                "Напиши вопрос или задание — постараюсь объяснить и подсказать ход решения.\n\n"
                "Для выхода нажми кнопку ниже или /start.",
                reply_markup=InlineKeyboardMarkup(KEYBOARD_BACK_TO_MAIN),
            )

        elif data == "student_ege":
            text = (
                "📚 Раздел ЕГЭ по информатике\n\n"
                "Выбери номер задания (1–27). Откроется пример решения и краткое объяснение.\n\n"
                "Источник материалов: code-enjoy.ru"
            )
            keyboard = []
            for row_start in range(1, 28, 3):
                row = [
                    InlineKeyboardButton(f"{row_start}", callback_data=f"ege_task_{row_start}"),
                    InlineKeyboardButton(f"{row_start + 1}", callback_data=f"ege_task_{row_start + 1}"),
                    InlineKeyboardButton(f"{row_start + 2}", callback_data=f"ege_task_{row_start + 2}"),
                ]
                keyboard.append(row)
            keyboard.extend(KEYBOARD_BACK_TO_MAIN)
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

        elif data.startswith("ege_task_"):
            parts = data.split("_")
            try:
                num = int(parts[2])
                subtask = int(parts[3]) if len(parts) >= 4 else None  # 8_1 или 8_2
            except (IndexError, ValueError):
                num = 0
                subtask = None
            if not (1 <= num <= 27):
                await query.edit_message_text("Некорректный номер задания.", reply_markup=InlineKeyboardMarkup(KEYBOARD_BACK_TO_MAIN))
                return
            # По кнопке 8 или 11 без подтипа — спрашиваем тип
            if num == 8 and subtask is None:
                keyboard = [
                    [InlineKeyboardButton("Задача 8.1", callback_data="ege_task_8_1"), InlineKeyboardButton("Задача 8.2", callback_data="ege_task_8_2")],
                    [InlineKeyboardButton("📚 К списку заданий", callback_data="student_ege")],
                ]
                keyboard.extend(KEYBOARD_BACK_TO_MAIN)
                await query.edit_message_text(
                    "📚 Задание 8. Выберите тип:",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )
                return
            if num == 11 and subtask is None:
                keyboard = [
                    [InlineKeyboardButton("Задача 11.1", callback_data="ege_task_11_1"), InlineKeyboardButton("Задача 11.2", callback_data="ege_task_11_2")],
                    [InlineKeyboardButton("📚 К списку заданий", callback_data="student_ege")],
                ]
                keyboard.extend(KEYBOARD_BACK_TO_MAIN)
                await query.edit_message_text(
                    "📚 Задание 11. Выберите тип:",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )
                return
            if num == 14 and subtask is None:
                keyboard = [
                    [InlineKeyboardButton("Задача 14.1", callback_data="ege_task_14_1"), InlineKeyboardButton("Задача 14.2", callback_data="ege_task_14_2")],
                    [InlineKeyboardButton("📚 К списку заданий", callback_data="student_ege")],
                ]
                keyboard.extend(KEYBOARD_BACK_TO_MAIN)
                await query.edit_message_text(
                    "📚 Задание 14. Выберите тип:",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )
                return
            if num == 17 and subtask is None:
                keyboard = [
                    [InlineKeyboardButton("Задача 17.1", callback_data="ege_task_17_1"), InlineKeyboardButton("Задача 17.2", callback_data="ege_task_17_2")],
                    [InlineKeyboardButton("📚 К списку заданий", callback_data="student_ege")],
                ]
                keyboard.extend(KEYBOARD_BACK_TO_MAIN)
                await query.edit_message_text(
                    "📚 Задание 17. Выберите тип:",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )
                return
            if num == 19 and subtask is None:
                keyboard = [
                    [InlineKeyboardButton("Задача 19.1", callback_data="ege_task_19_1"), InlineKeyboardButton("Задача 19.2", callback_data="ege_task_19_2")],
                    [InlineKeyboardButton("📚 К списку заданий", callback_data="student_ege")],
                ]
                keyboard.extend(KEYBOARD_BACK_TO_MAIN)
                await query.edit_message_text(
                    "📚 Задание 19. Выберите тип:",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )
                return
            if num == 20 and subtask is None:
                keyboard = [
                    [InlineKeyboardButton("Задача 20.1", callback_data="ege_task_20_1"), InlineKeyboardButton("Задача 20.2", callback_data="ege_task_20_2")],
                    [InlineKeyboardButton("📚 К списку заданий", callback_data="student_ege")],
                ]
                keyboard.extend(KEYBOARD_BACK_TO_MAIN)
                await query.edit_message_text(
                    "📚 Задание 20. Выберите тип:",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )
                return
            if num == 21 and subtask is None:
                keyboard = [
                    [InlineKeyboardButton("Задача 21.1", callback_data="ege_task_21_1"), InlineKeyboardButton("Задача 21.2", callback_data="ege_task_21_2")],
                    [InlineKeyboardButton("📚 К списку заданий", callback_data="student_ege")],
                ]
                keyboard.extend(KEYBOARD_BACK_TO_MAIN)
                await query.edit_message_text(
                    "📚 Задание 21. Выберите тип:",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )
                return
            if num == 22 and subtask is None:
                keyboard = [
                    [InlineKeyboardButton("Задача 22.1", callback_data="ege_task_22_1"), InlineKeyboardButton("Задача 22.2", callback_data="ege_task_22_2")],
                    [InlineKeyboardButton("📚 К списку заданий", callback_data="student_ege")],
                ]
                keyboard.extend(KEYBOARD_BACK_TO_MAIN)
                await query.edit_message_text(
                    "📚 Задание 22. Выберите тип:",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )
                return
            if num == 24 and subtask is None:
                keyboard = [
                    [InlineKeyboardButton("Задача 24.1", callback_data="ege_task_24_1"), InlineKeyboardButton("Задача 24.2", callback_data="ege_task_24_2")],
                    [InlineKeyboardButton("📚 К списку заданий", callback_data="student_ege")],
                ]
                keyboard.extend(KEYBOARD_BACK_TO_MAIN)
                await query.edit_message_text(
                    "📚 Задание 24. Выберите тип:",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )
                return
            if num == 26 and subtask is None:
                keyboard = [
                    [
                        InlineKeyboardButton("26.1", callback_data="ege_task_26_1"),
                        InlineKeyboardButton("26.2", callback_data="ege_task_26_2"),
                        InlineKeyboardButton("26.3", callback_data="ege_task_26_3"),
                    ],
                    [
                        InlineKeyboardButton("26.4", callback_data="ege_task_26_4"),
                        InlineKeyboardButton("26.5", callback_data="ege_task_26_5"),
                    ],
                    [InlineKeyboardButton("📚 К списку заданий", callback_data="student_ege")],
                ]
                keyboard.extend(KEYBOARD_BACK_TO_MAIN)
                await query.edit_message_text(
                    "📚 Задание 26. Выберите тип:",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )
                return
            if num == 27 and subtask is None:
                keyboard = [
                    [InlineKeyboardButton("Задача 27.1", callback_data="ege_task_27_1"), InlineKeyboardButton("Задача 27.2", callback_data="ege_task_27_2")],
                    [InlineKeyboardButton("📚 К списку заданий", callback_data="student_ege")],
                ]
                keyboard.extend(KEYBOARD_BACK_TO_MAIN)
                await query.edit_message_text(
                    "📚 Задание 27. Выберите тип:",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )
                return
            task = await db.get_ege_task(num, subtask=subtask)
            has_any = task and (
                (task.get("task_image") or "").strip()
                or (task.get("solution_image") or "").strip()
                or (task.get("explanation") or "").strip()
                or (task.get("example_solution") or "").strip()
            )
            if not has_any:
                msg = (
                    f"📚 Задание {num}\n\n"
                    "Контент пока не добавлен. Разбор заданий можно посмотреть на сайте:\n"
                    "https://code-enjoy.ru/courses/kurs_ege_po_informatike/"
                )
                keyboard = [
                    [InlineKeyboardButton("📚 К списку заданий", callback_data="student_ege")],
                ]
                keyboard.extend(KEYBOARD_BACK_TO_MAIN)
                await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(keyboard))
                return
            label = f"{num}.{subtask}" if ((num in (8, 11, 14, 17, 19, 20, 21, 22, 24, 26, 27)) and subtask) else str(num)
            title = (task.get("title") or "").strip() or f"Задание {label}"
            chat_id = query.message.chat_id
            task_image = (task.get("task_image") or "").strip()
            solution_callback = f"ege_show_solution_{num}_{subtask}" if ((num in (8, 11, 14, 17, 19, 20, 21, 22, 24, 26, 27)) and subtask) else f"ege_show_solution_{num}"
            # Несколько фото задания (через "|"): отправляем подряд
            task_images = [p.strip() for p in task_image.split("|") if p.strip()]
            if task_images:
                root = Path(__file__).parent
                for idx, one in enumerate(task_images):
                    try:
                        if one.startswith("http://") or one.startswith("https://"):
                            cap = f"📋 Задание {label}. {title}" if idx == 0 else f"📋 Задание {label} (продолжение)"
                            await context.bot.send_photo(chat_id=chat_id, photo=one, caption=cap)
                        else:
                            path = root / one
                            if path.is_file():
                                cap = f"📋 Задание {label}. {title}" if idx == 0 else f"📋 Задание {label} (продолжение)"
                                with open(path, "rb") as f:
                                    await context.bot.send_photo(chat_id=chat_id, photo=InputFile(f, filename=path.name), caption=cap)
                    except Exception as e:
                        logger.warning("ege_task_%s фото %s: %s", label, idx, e)
            msg = f"📚 Задание {label}. {title}\n\n👇 Нажмите кнопку ниже, чтобы получить решение."
            keyboard = [
                [InlineKeyboardButton("📎 Показать решение", callback_data=solution_callback)],
                [InlineKeyboardButton("📚 К списку заданий", callback_data="student_ege")],
            ]
            keyboard.extend(KEYBOARD_BACK_TO_MAIN)
            await context.bot.send_message(
                chat_id=chat_id,
                text=msg,
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
            await query.edit_message_text(f"Задание {label} открыто. 👇 Решение — в сообщении ниже.")

        elif data.startswith("ege_show_solution_"):
            parts = data.split("_")
            try:
                num = int(parts[3])
                subtask = int(parts[4]) if len(parts) >= 5 else None
            except (IndexError, ValueError):
                num = 0
                subtask = None
            if not (1 <= num <= 27):
                await query.answer("Некорректный номер.")
                return
            task = await db.get_ege_task(num, subtask=subtask)
            if not task:
                await query.answer("Задание не найдено.", show_alert=True)
                return
            example = (task.get("example_solution") or "").strip()
            solution_image_raw = (task.get("solution_image") or "").strip()
            # Несколько скринов решений через "|" (например для задания 18)
            solution_images = [p.strip() for p in solution_image_raw.split("|") if p.strip()]
            solution_image = solution_images[0] if solution_images else ""
            chat_id = query.message.chat_id

            def _send_back_to_tasks():
                kbd = [
                    [InlineKeyboardButton("📚 К списку заданий", callback_data="student_ege")],
                ]
                kbd.extend(KEYBOARD_BACK_TO_MAIN)
                return context.bot.send_message(
                    chat_id=chat_id,
                    text="Можно вернуться к списку заданий или на главную.",
                    reply_markup=InlineKeyboardMarkup(kbd),
                )

            def _looks_like_code(t: str) -> bool:
                if not t or len(t) < 20:
                    return False
                t = t.lower()
                return ("def " in t or "for " in t or "while " in t or "in range(" in t) and (
                    "print(" in t or "return " in t or "range(" in t
                )

            # Решение-код: выводим в блоке ``` и затем при наличии — скрин с текстом
            if example and _looks_like_code(example):
                code_msg = "Решение (код):\n\n```python\n" + example + "\n```"
                if len(code_msg) > 4000:
                    code_msg = code_msg[:3980] + "\n\n… (обрезано)\n```"
                try:
                    await context.bot.send_message(chat_id=chat_id, text=code_msg, parse_mode="Markdown")
                except Exception as e:
                    logger.warning("ege_show_solution markdown failed, fallback to HTML: %s", e)
                    code_html = _format_homework_reply_for_telegram(f"Решение (код):\n\n{example}")[0]
                    await context.bot.send_message(chat_id=chat_id, text=code_html, parse_mode="HTML")
                # Скрин(ы) решения: для 2, 9, 13 — один; для 18 — несколько; для 19–21 — по скрину на тип
                if solution_images:
                    try:
                        root = Path(__file__).parent
                        for idx, one in enumerate(solution_images):
                            cap = "📎 Решение через Excel (скрин)." if num == 9 and idx == 0 else "📎 Текст к решению (скрин)." if num == 2 and idx == 0 else (f"📎 Решение. Задание {num}.{subtask}" if subtask and idx == 0 else f"📎 Решение. Задание {num}") + (" (продолжение)" if idx > 0 else "")
                            if one.startswith("http://") or one.startswith("https://"):
                                await context.bot.send_photo(chat_id=chat_id, photo=one, caption=cap)
                            else:
                                path = root / one
                                if path.is_file():
                                    with open(path, "rb") as f:
                                        await context.bot.send_photo(chat_id=chat_id, photo=InputFile(f, filename=path.name), caption=cap)
                                else:
                                    logger.warning("ege_show_solution_%s image %s not found: %s", num, idx, one)
                        await _send_back_to_tasks()
                        await query.answer("Решение отправлено.")
                        return
                    except Exception as e:
                        logger.warning("ege_show_solution_%s images after code: %s", num, e)
                await _send_back_to_tasks()
                await query.answer("Решение отправлено.")
                return

            if solution_images:
                try:
                    root = Path(__file__).parent
                    for idx, one in enumerate(solution_images):
                        cap = f"📎 Решение. Задание {num}" if idx == 0 else f"📎 Решение. Задание {num} (продолжение)"
                        if one.startswith("http://") or one.startswith("https://"):
                            await context.bot.send_photo(chat_id=chat_id, photo=one, caption=cap)
                        else:
                            path = root / one
                            if path.is_file():
                                with open(path, "rb") as f:
                                    await context.bot.send_photo(chat_id=chat_id, photo=InputFile(f, filename=path.name), caption=cap)
                            else:
                                logger.warning("ege_show_solution_%s image %s not found: %s", num, idx, one)
                    await _send_back_to_tasks()
                    await query.answer("Решение отправлено.")
                except Exception as e:
                    logger.warning("ege_show_solution_%s: %s", num, e)
                    await query.answer("Не удалось отправить фото.", show_alert=True)
                return
            if example:
                body_html, parse_mode = _format_homework_reply_for_telegram(f"Решение:\n\n{example}")
                if len(body_html) > 4000:
                    body_html = body_html[:3990] + "\n\n… (обрезано)"
                await context.bot.send_message(chat_id=chat_id, text=body_html, parse_mode=parse_mode)
                await _send_back_to_tasks()
                await query.answer("Решение отправлено.")
                return
            await query.answer("Решение для этого задания не добавлено.", show_alert=True)

        elif data == "admin_add_tutor":
            if not is_admin(user_id, context.bot_data):
                await query.edit_message_text(MSG_ONLY_TUTOR)
                return
            await query.edit_message_text(
                "➕ Добавить репетитора\n\n"
                "Сейчас репетиторов задают в настройках бота (Railway Variables или config.py).\n\n"
                "Чтобы добавить репетитора по его Telegram ID:\n"
                "• В Railway: переменная TUTOR_USER_IDS — перечисли ID через запятую, например:\n"
                "  2071587097,123456789\n"
                "  (твой ID уже считается репетитором как админ). После изменения сделай Redeploy.\n\n"
                "Когда будет готова команда добавления из бота — подскажешь, добавлю.",
                reply_markup=InlineKeyboardMarkup(KEYBOARD_BACK_TO_MAIN),
            )

        elif data == "admin_download_db":
            if not is_tutor(user_id, context.bot_data):
                await query.edit_message_text(MSG_ONLY_TUTOR)
                return
            try:
                path = db.DB_PATH
                if not path.exists():
                    await query.edit_message_text(
                        "📥 Скачать БД\n\nФайл базы данных ещё не создан (нет уроков/записей). "
                        "После первого создания урока файл появится.",
                        reply_markup=InlineKeyboardMarkup(KEYBOARD_BACK_TO_MAIN),
                    )
                    return
                with open(path, "rb") as f:
                    data_bytes = f.read()
                await query.edit_message_text("📥 Отправляю файл базы данных…")
                await context.bot.send_document(
                    chat_id=query.message.chat_id,
                    document=InputFile(io.BytesIO(data_bytes), filename="tutor_bot.db"),
                    caption="Резервная копия базы (уроки, записи, слоты). Сохрани на ноутбук при переносе сервера.",
                )
                await query.edit_message_text(
                    "✅ Файл базы отправлен в чат. Сохрани его на ноутбук — при переносе сервера можно будет использовать эту копию.",
                    reply_markup=InlineKeyboardMarkup(KEYBOARD_BACK_TO_MAIN),
                )
            except Exception as e:
                logger.exception("admin_download_db: %s", e)
                await query.edit_message_text(
                    f"❌ Не удалось отправить базу: {e}. Проверь логи на сервере.",
                    reply_markup=InlineKeyboardMarkup(KEYBOARD_BACK_TO_MAIN),
                )

        elif data == "tutor_add_lesson":
            if not is_tutor(user_id, context.bot_data):
                await query.edit_message_text(MSG_ONLY_TUTOR)
                return
            _clear_other_flows(context, "add_lesson")
            context.user_data["add_lesson"] = {"step": "title"}
            await query.edit_message_text(
                "✏️ Создание урока\n\n"
                "Шаг 1/7 · Название\n"
                "Напиши название урока, например:\n"
                "Математика, 8 класс",
            )

        elif data == "tutor_schedule":
            if not is_tutor(user_id, context.bot_data):
                await query.edit_message_text(MSG_ONLY_TUTOR)
                return
            text, reply_markup = await _build_schedule_message(context)
            await query.edit_message_text(text, reply_markup=reply_markup)

        elif data == "tutor_schedule_set_range":
            if not is_tutor(user_id, context.bot_data):
                await query.edit_message_text(MSG_ONLY_TUTOR)
                return
            _clear_other_flows(context, "schedule_range_input")
            context.user_data["schedule_range_input"] = {"step": "from"}
            await query.edit_message_text(
                "📅 Показать расписание за период\n\n"
                "Шаг 1/2 · Начальная дата (ДД.ММ.ГГГГ или 20.02.2025):",
            )

        elif data == "tutor_schedule_clear_range":
            if not is_tutor(user_id, context.bot_data):
                await query.edit_message_text(MSG_ONLY_TUTOR)
                return
            try:
                context.user_data.pop("schedule_range", None)
                text, reply_markup = await _build_schedule_message(context)
                if len(text) > 4090:
                    text = text[:4080] + "\n\n… (много уроков — задайте период)"
                await query.edit_message_text(text, reply_markup=reply_markup)
            except Exception as e:
                logger.exception("tutor_schedule_clear_range: %s", e)
                try:
                    context.user_data.pop("schedule_range", None)
                    text, reply_markup = await _build_schedule_message(context)
                    await query.message.reply_text(
                        text[:4090] if len(text) > 4090 else text,
                        reply_markup=reply_markup,
                    )
                except Exception:
                    await query.edit_message_text(
                        "Период сброшен. Нажмите «Расписание» в меню или /schedule.",
                    )

        elif data == "tutor_summary":
            if not is_tutor(user_id, context.bot_data):
                await query.edit_message_text(MSG_ONLY_TUTOR)
                return
            tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            lessons = await db.get_lessons_on_date(tomorrow)
            await query.edit_message_text(
                _format_summary(tomorrow, lessons),
                reply_markup=InlineKeyboardMarkup(KEYBOARD_BACK_TO_MAIN),
            )

        elif data == "tutor_clear_schedule":
            if not is_tutor(user_id, context.bot_data):
                await query.edit_message_text(MSG_ONLY_TUTOR)
                return
            keyboard = [
                [InlineKeyboardButton("✅ Подтвердить", callback_data="tutor_clear_schedule_confirm")],
                [InlineKeyboardButton("❌ Отмена", callback_data="tutor_clear_schedule_cancel")],
            ]
            await query.edit_message_text(
                "🗑 Очистить всё расписание?\n\n"
                "Будут удалены все уроки, все записи и все занятые слоты. Это нельзя отменить.",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )

        elif data == "tutor_clear_schedule_confirm":
            if not is_tutor(user_id, context.bot_data):
                await query.edit_message_text(MSG_ONLY_TUTOR)
                return
            lesson_ids = await db.get_all_lesson_ids()
            jq = context.application.job_queue
            if jq and jq.scheduler:
                for lid in lesson_ids:
                    for name in (f"remind_1d_{lid}", f"remind_1h_{lid}"):
                        try:
                            jq.scheduler.remove_job(name)
                        except Exception:
                            pass
            n_lessons, n_slots = await db.clear_all_schedule()
            text, reply_markup = await _build_schedule_message(context)
            await query.edit_message_text(
                f"✅ Очищено: уроков {n_lessons}, слотов {n_slots}.\n\n" + text,
                reply_markup=reply_markup,
            )

        elif data == "tutor_clear_chat_help":
            if not is_tutor(user_id, context.bot_data):
                await query.edit_message_text(MSG_ONLY_TUTOR)
                return
            await query.answer()
            await query.message.reply_text(
                "💬 Как очистить чат с ботом\n\n"
                "Бот не может удалить сообщения за вас. Сделайте так:\n\n"
                "• iPhone/Android: откройте чат с ботом → нажмите на название бота вверху → «Очистить историю» или «Удалить чат».\n\n"
                "• Telegram Desktop: правый клик по чату → «Очистить историю».",
                reply_markup=InlineKeyboardMarkup(KEYBOARD_BACK_TO_MAIN),
            )

        elif data == "tutor_clear_schedule_cancel":
            if not is_tutor(user_id, context.bot_data):
                await query.edit_message_text(MSG_ONLY_TUTOR)
                return
            await _refresh_schedule_message(query, context)

        elif data == "tutor_block_slot":
            if not is_tutor(user_id, context.bot_data):
                await query.edit_message_text(MSG_ONLY_TUTOR)
                return
            # Не сбрасывать диалог, если уже идёт — иначе случайное нажатие кнопки обнуляет ввод
            if context.user_data.get("block_slot"):
                step = context.user_data["block_slot"].get("step", "")
                next_hint = {"name": "имя ученика", "day": "день (пн, вт...)", "time": "время (19:00)", "username": "@username или минус", "more_slot": "да или нет"}.get(step, "следующий шаг")
                await query.answer()
                await query.edit_message_text(
                    "🔒 Вы уже закрепляете слот.\n\n"
                    f"Продолжайте ввод ({next_hint}) или напишите «отмена», чтобы выйти.",
                )
                return
            _clear_other_flows(context, "block_slot")
            context.user_data["block_slot"] = {"step": "name"}
            await query.edit_message_text(
                "🔒 Закрепить слот за учеником\n\n"
                "Шаг 1/4 · Имя ученика (как запомнить слот):",
            )

        elif data.startswith("unblock_"):
            if not is_tutor(user_id, context.bot_data):
                await query.edit_message_text(MSG_ONLY_TUTOR)
                return
            slot_id = int(data.split("_")[1])
            ok = await db.delete_blocked_slot(slot_id)
            if ok:
                await _refresh_schedule_message(query, context)
            else:
                await query.edit_message_text("Не удалось снять слот.", reply_markup=InlineKeyboardMarkup(KEYBOARD_BACK_TO_MAIN))

        elif data == "tutor_preview_student":
            if not is_tutor(user_id, context.bot_data):
                await query.edit_message_text(MSG_ONLY_TUTOR)
                return
            title = context.bot_data.get("bot_title") or "Репетитор"
            preview_text = (
                "👋 Привет, друг!\n\n"
                f"Я бот записи на уроки — {title}.\n\n"
                "Выберите действие:"
            )
            keyboard = [
                [InlineKeyboardButton("📅 Записаться на урок", callback_data="student_lessons")],
                [InlineKeyboardButton("📌 Мои записи и слоты", callback_data="student_my")],
                [InlineKeyboardButton("🕐 Записаться на свободное время", callback_data="student_freetime")],
                [InlineKeyboardButton("👤 Репетитор", callback_data="student_tutor")],
            ]
            if context.bot_data.get("openai_api_key"):
                keyboard.append([InlineKeyboardButton("📝 Помощь с домашкой", callback_data="student_homework_help")])
            keyboard.append([InlineKeyboardButton("📚 Раздел ЕГЭ", callback_data="student_ege")])
            await query.message.reply_text(
                "👀 Так видят ученики:\n━━━━━━━━━━━━━━━━━━━━",
            )
            await context.bot.send_message(
                chat_id=user_id,
                text=preview_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
            )

        elif data.startswith("book_"):
            lesson_id = int(data.split("_")[1])
            ok, msg = await db.book_lesson(
                lesson_id,
                user_id,
                username=query.from_user.username,
                first_name=query.from_user.first_name,
            )
            await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(KEYBOARD_BACK_TO_MAIN))
            if ok:
                lesson = await db.get_lesson(lesson_id)
                if lesson:
                    student_name = query.from_user.first_name or query.from_user.username or f"ID{user_id}"
                    notify = (
                        "🔔 Новая запись на урок\n\n"
                        f"👤 {student_name}"
                    )
                    if query.from_user.username:
                        notify += f" @{query.from_user.username}"
                    notify += f"\n\n▫️ {lesson['title']}\n📅 {lesson['lesson_date']}  ·  🕐 {lesson['lesson_time']}"
                    try:
                        await context.bot.send_message(chat_id=tutor_id, text=notify)
                    except Exception:
                        pass

        elif data.startswith("student_unblock_"):
            slot_id = int(data.split("_")[2])
            slot = await db.get_blocked_slot_by_id(slot_id)
            if not slot:
                await query.edit_message_text("Слот уже снят.", reply_markup=InlineKeyboardMarkup(KEYBOARD_BACK_TO_MAIN))
                return
            student_username = (slot.get("student_username") or "").strip().lower()
            my_username = (query.from_user.username or "").strip().lower()
            if student_username and student_username != my_username:
                await query.edit_message_text("Этот слот закреплён за другим учеником.", reply_markup=InlineKeyboardMarkup(KEYBOARD_BACK_TO_MAIN))
                return
            await db.delete_blocked_slot(slot_id)
            username = (query.from_user.username or "").strip()
            text, reply_markup = await _build_my_bookings_message(user_id, username)
            if text is None:
                await query.edit_message_text(
                    "✅ Слот отменён.\n\n📌 У вас больше нет записей. Нажми «Записаться на урок» или /lessons.",
                    reply_markup=InlineKeyboardMarkup(KEYBOARD_BACK_TO_MAIN),
                )
                return
            await query.edit_message_text("✅ Слот отменён.\n\n" + text, reply_markup=reply_markup)

        elif data.startswith("cancel_"):
            lesson_id = int(data.split("_")[1])
            ok, msg = await db.cancel_booking(lesson_id, user_id)
            await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(KEYBOARD_BACK_TO_MAIN))

        elif data.startswith("tutor_bookings_"):
            lesson_id = int(data.split("_")[2])
            if not is_tutor(user_id, context.bot_data):
                await query.edit_message_text(MSG_ONLY_TUTOR)
                return
            bookings = await db.get_bookings_for_lesson(lesson_id)
            if not bookings:
                text = "👥 На этот урок пока никто не записан."
            else:
                lines = [f"   • {b.get('first_name') or b.get('username') or 'ID' + str(b['user_id'])} (id {b['user_id']})" for b in bookings]
                text = "👥 Кто записан\n\n" + "\n".join(lines)
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(KEYBOARD_BACK_TO_MAIN))

        elif data.startswith("tutor_del_"):
            lesson_id = int(data.split("_")[2])
            if not is_tutor(user_id, context.bot_data):
                await query.edit_message_text(MSG_ONLY_TUTOR)
                return
            ok, lesson, user_ids = await db.delete_lesson(lesson_id)
            if ok and lesson:
                cancel_text = (
                    f"❌ Урок отменён\n\n"
                    f"▫️ {lesson['title']}\n"
                    f"📅 {lesson['lesson_date']}  ·  🕐 {lesson['lesson_time']}"
                )
                for uid in user_ids:
                    try:
                        await context.bot.send_message(chat_id=uid, text=cancel_text)
                    except Exception:
                        pass
                jq = context.application.job_queue
                if jq and jq.scheduler:
                    for name in (f"remind_1d_{lesson_id}", f"remind_1h_{lesson_id}"):
                        try:
                            jq.scheduler.remove_job(name)
                        except Exception:
                            pass
            await query.edit_message_text(
                "✅ Урок удалён." if ok else "❌ Не удалось удалить.",
                reply_markup=InlineKeyboardMarkup(KEYBOARD_BACK_TO_MAIN),
            )

        else:
            logger.warning("Unknown callback_data: %r", data)
            try:
                user = query.from_user
                text, keyboard = _build_main_menu_content(user.id, user.first_name, context.bot_data)
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            except Exception:
                pass

    except Exception as e:
        logger.exception("Callback error: %s", e)
        try:
            user = query.from_user
            text, keyboard = _build_main_menu_content(user.id, user.first_name, context.bot_data)
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        except Exception:
            pass


# ——— Репетитор: добавить урок ———

def parse_date(s: str) -> str | None:
    """Принимает YYYY-MM-DD или DD.MM.YYYY."""
    s = s.strip()
    if re.match(r"\d{4}-\d{2}-\d{2}", s):
        return s
    m = re.match(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", s)
    if m:
        d, mo, y = m.groups()
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    return None


def parse_time(s: str) -> str | None:
    """Принимает HH:MM или H:MM."""
    m = re.match(r"(\d{1,2}):(\d{2})", s.strip())
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        if 0 <= h <= 23 and 0 <= mi <= 59:
            return f"{h:02d}:{mi:02d}"
    return None


def _normalize_slot_time(t: str) -> str:
    """Единый формат времени для группировки слотов (20:00 и 20:00 — один ключ)."""
    if not t:
        return t
    parsed = parse_time(t)
    return parsed if parsed else t.strip()


def parse_max_students(s: str) -> int | None:
    """Число от 1 до 100."""
    try:
        n = int(s.strip())
        if 1 <= n <= 100:
            return n
    except ValueError:
        pass
    return None


DAY_NAMES = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")
DAY_NAMES_FULL = ("понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье")


def parse_day_of_week(s: str) -> int | None:
    """День недели: пн/вт/.../вс или понедельник/... или 0-6. Возвращает 0=пн..6=вс."""
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


async def _schedule_reminders(context: ContextTypes.DEFAULT_TYPE, lesson_id: int) -> None:
    """Ставит напоминания за 1 день и за 1 час до урока."""
    lesson = await db.get_lesson(lesson_id)
    if not lesson:
        return
    try:
        dt = datetime.strptime(f"{lesson['lesson_date']} {lesson['lesson_time']}", "%Y-%m-%d %H:%M")
    except ValueError:
        return
    job_queue = context.application.job_queue
    if not job_queue:
        return
    when_1d = dt - timedelta(days=1)
    when_1h = dt - timedelta(hours=1)
    if when_1d > datetime.now():
        job_queue.run_once(
            _reminder_callback,
            when_1d,
            data={"lesson_id": lesson_id, "kind": "1day"},
            name=f"remind_1d_{lesson_id}",
        )
    if when_1h > datetime.now():
        job_queue.run_once(
            _reminder_callback,
            when_1h,
            data={"lesson_id": lesson_id, "kind": "1hour"},
            name=f"remind_1h_{lesson_id}",
        )


async def _reminder_callback(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет напоминание репетитору и записанным ученикам."""
    job = context.job
    lesson_id = job.data.get("lesson_id")
    kind = job.data.get("kind", "")
    lesson = await db.get_lesson(lesson_id)
    if not lesson:
        return
    tutor_id = context.bot_data.get("tutor_user_id")
    text = (
        f"⏰ Напоминание: через {'1 день' if kind == '1day' else '1 час'} урок\n\n"
        f"▫️ {lesson['title']}\n"
        f"📅 {lesson['lesson_date']}  ·  🕐 {lesson['lesson_time']}"
    )
    try:
        await context.bot.send_message(chat_id=tutor_id, text=text)
    except Exception:
        pass
    bookings = await db.get_bookings_for_lesson(lesson_id)
    for b in bookings:
        try:
            await context.bot.send_message(chat_id=b["user_id"], text=text)
        except Exception:
            pass


async def _post_lesson_to_channel(context: ContextTypes.DEFAULT_TYPE, lesson: dict, bot_username: str) -> None:
    """Постит анонс урока в канал."""
    channel_id = context.bot_data.get("channel_id")
    if not channel_id or not bot_username:
        return
    link = f"https://t.me/{bot_username.lstrip('@')}"
    text = (
        f"📚 Новый урок\n\n"
        f"▫️ {lesson['title']}\n"
        f"📅 {lesson['lesson_date']}  ·  🕐 {lesson['lesson_time']}\n\n"
        f"Записаться: {link}"
    )
    try:
        await context.bot.send_message(chat_id=channel_id, text=text)
    except Exception:
        pass


async def _send_confirm_summary(update: Update, context: ContextTypes.DEFAULT_TYPE, data: dict) -> None:
    """Отправляет итоговое сообщение перед созданием урока(ов)."""
    weeks = data.get("repeat_weeks", 1)
    times = data.get("times") or [data["time"]]
    summary = (
        "✏️ Шаг 7/7 · Проверь и подтверди\n\n"
        f"▫️ {data['title']}\n"
        f"🕐 Время: {', '.join(times)}  ·  👥 мест: {data.get('max_students', 1)}\n"
    )
    if data.get("description"):
        summary += f"📝 {data['description']}\n"
    total = weeks * len(times)
    if weeks >= 2 or len(times) > 1:
        summary += f"\n📅 Будет создано уроков: {total}\n"
    summary += f"\n📅 Дата: {data['date']}" + (f" (и ещё {weeks - 1} нед.)" if weeks > 1 else "")
    summary += "\n\nСоздать? Напиши да или нет."
    await update.message.reply_text(summary)


async def _do_create_lessons(update: Update, context: ContextTypes.DEFAULT_TYPE, data: dict) -> None:
    """Создаёт уроки по data (без проверки занятости слотов)."""
    weeks = data.get("repeat_weeks", 1)
    times = data.get("times") or [data["time"]]
    base_date = datetime.strptime(data["date"], "%Y-%m-%d").date()
    created = []
    for i in range(weeks):
        lesson_date = (base_date + timedelta(weeks=i)).strftime("%Y-%m-%d")
        for t in times:
            lesson_id = await db.add_lesson(
                title=data["title"],
                lesson_date=lesson_date,
                lesson_time=t,
                max_students=data.get("max_students", 1),
                description=data.get("description", ""),
            )
            await _schedule_reminders(context, lesson_id)
            created.append((lesson_id, lesson_date, t))
    if context.bot_data.get("channel_id") and created:
        lesson = await db.get_lesson(created[0][0])
        if lesson:
            await _post_lesson_to_channel(context, lesson, context.bot_data.get("bot_username", ""))
    n = len(created)
    if n == 1:
        await update.message.reply_text(
            f"✅ Урок создан (ID {created[0][0]}).\n\n"
            "Ученики увидят его в /lessons и смогут записаться.",
        )
    else:
        sample = ", ".join(f"{d} {t}" for _, d, t in created[:5])
        if n > 5:
            sample += f" … ещё {n - 5}"
        await update.message.reply_text(
            f"✅ Создано уроков: {n}\n\n{sample}\n\nУченики видят их в /lessons.",
        )


async def add_lesson_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_tutor(update.effective_user.id, context.bot_data):
        await update.message.reply_text(MSG_ONLY_TUTOR)
        return
    _clear_other_flows(context, "add_lesson")
    context.user_data["add_lesson"] = {"step": "title"}
    await update.message.reply_text(
        "✏️ Создание урока\n\n"
        "Шаг 1/7 · Название\n"
        "Напиши название урока, например:\n"
        "Математика, 8 класс",
    )


async def add_lesson_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_tutor(user_id, context.bot_data):
        return
    data = context.user_data.get("add_lesson")
    if not data:
        return
    text = update.message.text.strip()
    step = data.get("step", "title")

    if step == "title":
        data["title"] = text
        data["step"] = "date"
        await update.message.reply_text(
            "✏️ Шаг 2/7 · Дата\n\n"
            "Напиши дату в формате 20.02.2025 или 2025-02-20",
        )
        return
    if step == "date":
        date = parse_date(text)
        if not date:
            await update.message.reply_text("❌ Неверный формат. Пример: 20.02.2025 или 2025-02-20")
            return
        data["date"] = date
        data["step"] = "time"
        await update.message.reply_text(
            "✏️ Шаг 3/7 · Время\n\n"
            "Напиши время начала, например: 14:00",
        )
        return
    if step == "time":
        time = parse_time(text)
        if not time:
            await update.message.reply_text("❌ Неверный формат. Пример: 14:00")
            return
        data["time"] = time
        data["times"] = [time]
        data["step"] = "more_time"
        await update.message.reply_text(
            "✏️ Добавить ещё время в этот же день?\n\n"
            "Напиши ещё одно время (например 10:00) или минус (-) чтобы перейти дальше.",
        )
        return
    if step == "more_time":
        if text.strip() == "-":
            data["step"] = "max_students"
            await update.message.reply_text(
                "✏️ Шаг 4/7 · Мест на урок\n\n"
                "Сколько человек может записаться? (число от 1 до 100)",
            )
            return
        time = parse_time(text)
        if not time:
            await update.message.reply_text("❌ Неверный формат. Пример: 10:00 или минус (-)")
            return
        data["times"].append(time)
        times_str = ", ".join(data["times"])
        await update.message.reply_text(
            f"Время добавлено. Сейчас: {times_str}\n\n"
            "Ещё время или минус (-) чтобы дальше:",
        )
        return
    if step == "max_students":
        n = parse_max_students(text)
        if n is None:
            await update.message.reply_text("❌ Введи число от 1 до 100.")
            return
        data["max_students"] = n
        data["step"] = "description"
        await update.message.reply_text(
            "✏️ Шаг 5/7 · Описание (необязательно)\n\n"
            "Напиши пару слов об уроке или минус (-), чтобы пропустить.",
        )
        return
    if step == "description":
        data["description"] = text if text != "-" else ""
        data["step"] = "repeat"
        await update.message.reply_text(
            "✏️ Шаг 6/7 · Повторение\n\n"
            "Повторять этот урок еженедельно? Напиши да или нет.",
        )
        return
    if step == "repeat":
        if text.lower() in ("да", "yes", "д", "y"):
            data["step"] = "repeat_weeks"
            await update.message.reply_text(
                "✏️ Сколько недель подряд создать? (число от 2 до 52)\n\n"
                "Например: 4 — получится 4 урока с шагом в неделю.",
            )
            return
        data["repeat_weeks"] = 1
        data["step"] = "confirm"
        await _send_confirm_summary(update, context, data)
        return
    if step == "repeat_weeks":
        try:
            n = int(text.strip())
            if 2 <= n <= 52:
                data["repeat_weeks"] = n
                data["step"] = "confirm"
                await _send_confirm_summary(update, context, data)
                return
        except ValueError:
            pass
        await update.message.reply_text("❌ Введи число от 2 до 52.")
        return
    if step == "confirm":
        if text.lower() in ("да", "yes", "д", "y"):
            weeks = data.get("repeat_weeks", 1)
            times = data.get("times") or [data["time"]]
            base_date = datetime.strptime(data["date"], "%Y-%m-%d").date()
            # Проверяем, есть ли закреплённые слоты на это время (несколько учеников — ок)
            blocked_names_by_dt = []
            for i in range(weeks):
                d = base_date + timedelta(weeks=i)
                for t in times:
                    slots = await db.get_blocked_slots(d.weekday(), t)
                    if slots:
                        names = ", ".join(s["student_name"] for s in slots)
                        blocked_names_by_dt.append((d.strftime("%d.%m"), t, names))
            if blocked_names_by_dt:
                parts = [f"{d} {t} — {names}" for d, t, names in blocked_names_by_dt[:5]]
                msg = "В это время уже закреплено за: " + "; ".join(parts)
                if len(blocked_names_by_dt) > 5:
                    msg += " …"
                msg += "\n\nОбъединить урок? (создать один урок, имена будут показаны рядом) да/нет"
                data["step"] = "confirm_merge"
                await update.message.reply_text(msg)
                return
            await _do_create_lessons(update, context, data)
            context.user_data.pop("add_lesson", None)
            return
        await update.message.reply_text("Отменено.")
        context.user_data.pop("add_lesson", None)
        return
    if step == "confirm_merge":
        if text.lower() in ("да", "yes", "д", "y"):
            await _do_create_lessons(update, context, data)
        else:
            await update.message.reply_text("Отменено.")
        context.user_data.pop("add_lesson", None)
        return


def _format_summary(tomorrow: str, lessons: list) -> str:
    if not lessons:
        return f"📊 Сводка на завтра ({tomorrow})\n\nУроков нет."
    total_booked = sum(l.get("booked_count", 0) or 0 for l in lessons)
    lines = [format_lesson(l, with_id=True) for l in lessons]
    return (
        f"📊 Сводка на завтра ({tomorrow})\n\n"
        f"Уроков: {len(lessons)}  ·  Записано человек: {total_booked}\n\n"
        + "\n\n".join(lines)
    )


async def summary_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Сводка на завтра для репетитора."""
    if not is_tutor(update.effective_user.id, context.bot_data):
        await update.message.reply_text(MSG_ONLY_TUTOR)
        return
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    lessons = await db.get_lessons_on_date(tomorrow)
    await update.message.reply_text(_format_summary(tomorrow, lessons))


async def daily_summary_callback(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ежедневная сводка репетитору (вызывается по расписанию)."""
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    lessons = await db.get_lessons_on_date(tomorrow)
    tutor_id = context.bot_data.get("tutor_user_id")
    if not tutor_id:
        return
    try:
        await context.bot.send_message(
            chat_id=tutor_id,
            text=_format_summary(tomorrow, lessons),
        )
    except Exception:
        pass


def _format_date_header(lesson_date: str) -> str:
    """Понедельник, 17.02.2025"""
    d = datetime.strptime(lesson_date, "%Y-%m-%d").date()
    return f"{DAY_NAMES_FULL[d.weekday()].capitalize()}, {d.strftime('%d.%m.%Y')}"


async def _build_schedule_message(context: ContextTypes.DEFAULT_TYPE):
    """Возвращает (text, keyboard) для экрана расписания. Период из context.user_data['schedule_range']."""
    user_data = (getattr(context, "user_data", None) or {}) if context else {}
    range_dates = user_data.get("schedule_range")
    if range_dates:
        from_date, to_date = range_dates
        lessons = await db.get_lessons_in_range(from_date, to_date)
        d1 = datetime.strptime(from_date, "%Y-%m-%d").strftime("%d.%m.%Y")
        d2 = datetime.strptime(to_date, "%Y-%m-%d").strftime("%d.%m.%Y")
        period_label = f"{d1} — {d2}"
    else:
        lessons = await db.get_upcoming_lessons(limit=60)
        period_label = None
    blocked = await db.get_all_blocked_slots()
    text = "📅 Расписание"
    if period_label:
        text += f" ({period_label})\n\n"
    else:
        text += "\n\n"
    if lessons:
        by_date = {}
        for l in lessons:
            d = l["lesson_date"]
            by_date.setdefault(d, []).append(l)
        for date in sorted(by_date.keys()):
            text += f"\n——— {_format_date_header(date)} ———\n\n"
            for l in by_date[date]:
                text += format_lesson(l, with_id=True) + "\n\n"
    else:
        text += "Уроков пока нет.\n\n"
    if blocked:
        # Группируем по (день, время); время нормализуем, чтобы 20:00 и "20:00 " не разъезжались
        by_slot = {}
        for b in blocked:
            key = (b["day_of_week"], _normalize_slot_time(b.get("lesson_time", "") or ""))
            by_slot.setdefault(key, []).append(b)
        text += "\n\n🔒 Занятые слоты (это время нельзя бронировать):\n"
        for (dow, lt), slots in sorted(by_slot.items(), key=lambda x: (x[0][0], x[0][1])):
            day = DAY_NAMES[dow]
            names = ", ".join(s["student_name"] for s in slots)
            text += f"   • {day} {lt} — {names}\n"
    keyboard = []
    for l in lessons:
        keyboard.append([
            InlineKeyboardButton(f"👥 Кто записан · {l['title']} ({l['lesson_date']})", callback_data=f"tutor_bookings_{l['id']}"),
        ])
        keyboard.append([
            InlineKeyboardButton("🗑 Удалить урок", callback_data=f"tutor_del_{l['id']}"),
        ])
    for b in blocked:
        day = DAY_NAMES[b["day_of_week"]]
        keyboard.append([
            InlineKeyboardButton(f"🔓 Снять слот · {b['student_name']} ({day} {b['lesson_time']})", callback_data=f"unblock_{b['id']}"),
        ])
    keyboard.append([
        InlineKeyboardButton("🔒 Закрепить слот за учеником", callback_data="tutor_block_slot"),
    ])
    keyboard.append([
        InlineKeyboardButton("📅 Задать период", callback_data="tutor_schedule_set_range"),
        InlineKeyboardButton("Показать всё", callback_data="tutor_schedule_clear_range"),
    ])
    keyboard.append([
        InlineKeyboardButton("🗑 Очистить всё расписание", callback_data="tutor_clear_schedule"),
    ])
    keyboard.extend(KEYBOARD_BACK_TO_MAIN)
    return text, InlineKeyboardMarkup(keyboard)


async def schedule_tutor(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_tutor(update.effective_user.id, context.bot_data):
        await update.message.reply_text(MSG_ONLY_TUTOR)
        return
    text, reply_markup = await _build_schedule_message(context)
    await update.message.reply_text(text, reply_markup=reply_markup)


async def schedule_range_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Ввод периода для расписания (начальная и конечная дата)."""
    data = context.user_data.get("schedule_range_input")
    if not data:
        return False
    text = update.message.text.strip()
    step = data.get("step")
    if step == "from":
        from_date = parse_date(text)
        if not from_date:
            await update.message.reply_text("❌ Неверный формат. Пример: 20.02.2025 или 2025-02-20")
            return True
        data["from_date"] = from_date
        data["step"] = "to"
        await update.message.reply_text(
            "📅 Шаг 2/2 · Конечная дата (ДД.ММ.ГГГГ):",
        )
        return True
    if step == "to":
        to_date = parse_date(text)
        if not to_date:
            await update.message.reply_text("❌ Неверный формат. Пример: 27.02.2025")
            return True
        from_date = data["from_date"]
        if to_date < from_date:
            await update.message.reply_text("❌ Конечная дата должна быть не раньше начальной.")
            return True
        context.user_data["schedule_range"] = (from_date, to_date)
        context.user_data.pop("schedule_range_input", None)
        text_msg, reply_markup = await _build_schedule_message(context)
        await update.message.reply_text(text_msg, reply_markup=reply_markup)
        return True
    return False


async def block_slot_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Обработка ввода для «Закрепить слот за учеником». Возвращает True если обработано."""
    data = context.user_data.get("block_slot")
    if not data:
        return False
    text = update.message.text.strip()
    if text.lower() in ("отмена", "отменить", "cancel"):
        context.user_data.pop("block_slot", None)
        await update.message.reply_text("Закрепление слота отменено.")
        return True
    step = data.get("step")

    if step == "name":
        data["student_name"] = text
        data["step"] = "day"
        await update.message.reply_text(
            "🔒 Шаг 2/4 · День недели\n\n"
            "Напиши: пн, вт, ср, чт, пт, сб или вс",
        )
        return True
    if step == "day":
        day = parse_day_of_week(text)
        if day is None:
            await update.message.reply_text("❌ Неверно. Напиши: пн, вт, ср, чт, пт, сб или вс")
            return True
        data["day_of_week"] = day
        data["step"] = "time"
        await update.message.reply_text(
            "🔒 Шаг 3/4 · Время\n\n"
            "Напиши время, например: 19:00",
        )
        return True
    if step == "time":
        time = parse_time(text)
        if not time:
            await update.message.reply_text("❌ Неверный формат. Пример: 19:00")
            return True
        data["time"] = time
        # Если уже закрепляем не первый слот — используем того же ученика, не спрашиваем @
        if data.get("student_username") is not None:
            ok, msg = await db.add_blocked_slot(
                data["student_name"],
                data["day_of_week"],
                data["time"],
                student_username=data["student_username"],
            )
            data["slots_added"] = data.get("slots_added", 0) + 1
            out = msg + "\n\nЗакрепить ещё один слот за этим учеником? Напиши да или нет."
            data["step"] = "more_slot"
            await update.message.reply_text(out)
            return True
        data["step"] = "username"
        await update.message.reply_text(
            "🔒 Шаг 4/4 · Telegram ученика\n\n"
            "Введите @username ученика (без @), чтобы он видел этот слот в «Мои записи» и мог отменить. Или минус (-), если не привязывать.",
        )
        return True
    if step == "username":
        student_username = "" if text == "-" else text.strip().lstrip("@")
        ok, msg = await db.add_blocked_slot(
            data["student_name"],
            data["day_of_week"],
            data["time"],
            student_username=student_username,
        )
        data["student_username"] = student_username
        data["slots_added"] = data.get("slots_added", 0) + 1
        out = msg + "\n\nЭто время нельзя бронировать для других уроков."
        if student_username:
            out += f"\n\nУченик @{student_username} увидит слот в «Мои записи» и сможет отменить."
        out += "\n\nЗакрепить ещё один слот за этим учеником? Напиши да или нет."
        data["step"] = "more_slot"
        await update.message.reply_text(out)
        return True
    if step == "more_slot":
        name = data.get("student_name", "ученика")
        if text.lower() in ("да", "yes", "д", "y"):
            data["step"] = "day"
            await update.message.reply_text(
                f"🔒 Ещё слот для {name}\n\n"
                "День недели: пн, вт, ср, чт, пт, сб или вс",
            )
            return True
        if text.lower() in ("нет", "no", "н", "n"):
            n = data.get("slots_added", 1)
            context.user_data.pop("block_slot", None)
            await update.message.reply_text(
                f"✅ Готово. Закреплено слотов за {name}: {n}.",
            )
            return True
        await update.message.reply_text("Напиши да или нет.")
        return True
    return False


async def _refresh_schedule_message(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обновляет сообщение расписания (после unblock и т.п.)."""
    text, reply_markup = await _build_schedule_message(context)
    if len(text) > 4090:
        text = text[:4080] + "\n\n… (обрезано, задайте период)"
    await query.edit_message_text(text, reply_markup=reply_markup)
