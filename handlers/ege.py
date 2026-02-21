"""
EGE-related callback handling: ege_menu, student_ege (информатика), ege_math (математика), ege_task_*, ege_show_solution_*, ege_math_*.
"""
import logging
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile

from .common import KEYBOARD_BACK_TO_MAIN, _format_homework_reply_for_telegram
import database as db

logger = logging.getLogger(__name__)

# Project root so ege_images/ works
root = Path(__file__).resolve().parent.parent


async def handle_callback(query, context, data: str, user_id: int) -> bool:
    """Handle EGE callbacks. Returns True when handled."""
    # Подменю ЕГЭ: Информатика | Математика
    if data == "ege_menu":
        text = "📚 Раздел ЕГЭ\n\nВыбери предмет:"
        keyboard = [
            [InlineKeyboardButton("📘 Информатика", callback_data="student_ege")],
            [InlineKeyboardButton("📐 Математика", callback_data="ege_math")],
        ]
        keyboard.extend(KEYBOARD_BACK_TO_MAIN)
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return True

    # Математика: меню с кнопкой «Случайное задание»
    if data == "ege_math":
        text = (
            "📐 ЕГЭ — Математика\n\n"
            "19 заданий. Нажми кнопку — получи случайное задание. Решение откроется по нажатию «Показать решение»."
        )
        keyboard = [
            [InlineKeyboardButton("🎲 Случайное задание", callback_data="ege_math_random")],
            [InlineKeyboardButton("📚 К разделу ЕГЭ", callback_data="ege_menu")],
        ]
        keyboard.extend(KEYBOARD_BACK_TO_MAIN)
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return True

    # Случайное задание по математике
    if data == "ege_math_random":
        task = await db.get_ege_math_random_task()
        if not task:
            await query.edit_message_text(
                "Пока нет заданий по математике. Репетитор добавит их позже.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("📚 К разделу ЕГЭ", callback_data="ege_menu")]] + KEYBOARD_BACK_TO_MAIN
                ),
            )
            return True
        num = task["task_number"]
        task_text = (task.get("task_text") or "").strip()
        if len(task_text) > 4000:
            task_text = task_text[:3990] + "\n\n… (текст обрезан)"
        keyboard = [
            [InlineKeyboardButton("✅ Показать решение", callback_data=f"ege_math_show_{num}")],
            [InlineKeyboardButton("🎲 Другое задание", callback_data="ege_math_random")],
            [InlineKeyboardButton("📐 К математике", callback_data="ege_math")],
        ]
        keyboard.extend(KEYBOARD_BACK_TO_MAIN)
        await query.edit_message_text(
            f"📐 Задание {num}\n\n{task_text}",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return True

    # Показать решение по математике
    if data.startswith("ege_math_show_"):
        try:
            num = int(data.replace("ege_math_show_", ""))
        except ValueError:
            num = 0
        if not (1 <= num <= 19):
            await query.answer("Некорректный номер.")
            return True
        task = await db.get_ege_math_task(num)
        if not task:
            await query.answer("Задание не найдено.", show_alert=True)
            return True
        solution = (task.get("solution_text") or "").strip()
        if not solution:
            await query.answer("Решение для этого задания ещё не добавлено.", show_alert=True)
            return True
        if len(solution) > 4000:
            solution = solution[:3990] + "\n\n… (обрезано)"
        body, parse_mode = _format_homework_reply_for_telegram(f"✅ Решение. Задание {num}\n\n{solution}")
        keyboard = [
            [InlineKeyboardButton("🎲 Другое задание", callback_data="ege_math_random")],
            [InlineKeyboardButton("📐 К математике", callback_data="ege_math")],
        ]
        keyboard.extend(KEYBOARD_BACK_TO_MAIN)
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=body,
            parse_mode=parse_mode,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        await query.answer("Решение отправлено.")
        return True

    if data == "student_ege":
        ege_author = (context.bot_data.get("ege_author_tg") or "").strip()
        author_line = f"\n\nАвтор разборов: {ege_author}" if ege_author else ""
        text = (
            "📚 Раздел ЕГЭ по информатике\n\n"
            "Выбери номер задания (1–27). Откроется пример решения и краткое объяснение."
            + author_line
        )
        keyboard = []
        for row_start in range(1, 28, 3):
            row = [
                InlineKeyboardButton(f"{row_start}", callback_data=f"ege_task_{row_start}"),
                InlineKeyboardButton(f"{row_start + 1}", callback_data=f"ege_task_{row_start + 1}"),
                InlineKeyboardButton(f"{row_start + 2}", callback_data=f"ege_task_{row_start + 2}"),
            ]
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("📚 К разделу ЕГЭ", callback_data="ege_menu")])
        keyboard.extend(KEYBOARD_BACK_TO_MAIN)
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return True

    if data.startswith("ege_task_"):
        parts = data.split("_")
        try:
            num = int(parts[2])
            subtask = int(parts[3]) if len(parts) >= 4 else None  # 8_1 или 8_2
        except (IndexError, ValueError):
            num = 0
            subtask = None
        if not (1 <= num <= 27):
            await query.edit_message_text("Некорректный номер задания.", reply_markup=InlineKeyboardMarkup(KEYBOARD_BACK_TO_MAIN))
            return True
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
            return True
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
            return True
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
            return True
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
            return True
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
            return True
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
            return True
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
            return True
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
            return True
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
            return True
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
            return True
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
            return True
        task = await db.get_ege_task(num, subtask=subtask)
        has_any = task and (
            (task.get("task_image") or "").strip()
            or (task.get("solution_image") or "").strip()
            or (task.get("explanation") or "").strip()
            or (task.get("example_solution") or "").strip()
        )
        if not has_any:
            ege_author = (context.bot_data.get("ege_author_tg") or "").strip()
            author_line = f"\n\nАвтор разборов: {ege_author}" if ege_author else ""
            msg = (
                f"📚 Задание {num}\n\n"
                "Контент пока не добавлен."
                + author_line
            )
            keyboard = [
                [InlineKeyboardButton("📚 К списку заданий", callback_data="student_ege")],
            ]
            keyboard.extend(KEYBOARD_BACK_TO_MAIN)
            await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(keyboard))
            return True
        label = f"{num}.{subtask}" if ((num in (8, 11, 14, 17, 19, 20, 21, 22, 24, 26, 27)) and subtask) else str(num)
        title = (task.get("title") or "").strip() or f"Задание {label}"
        chat_id = query.message.chat_id
        task_image = (task.get("task_image") or "").strip()
        solution_callback = f"ege_show_solution_{num}_{subtask}" if ((num in (8, 11, 14, 17, 19, 20, 21, 22, 24, 26, 27)) and subtask) else f"ege_show_solution_{num}"
        # Несколько фото задания (через "|"): отправляем подряд
        task_images = [p.strip() for p in task_image.split("|") if p.strip()]
        if task_images:
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
        return True

    if data.startswith("ege_show_solution_"):
        parts = data.split("_")
        try:
            num = int(parts[3])
            subtask = int(parts[4]) if len(parts) >= 5 else None
        except (IndexError, ValueError):
            num = 0
            subtask = None
        if not (1 <= num <= 27):
            await query.answer("Некорректный номер.")
            return True
        task = await db.get_ege_task(num, subtask=subtask)
        if not task:
            await query.answer("Задание не найдено.", show_alert=True)
            return True
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
            # Скрин после кода: 9 — Excel, 13 — пояснение, 26 — решение и кодом и скринами (таблицы/разбор).
            if solution_images and num in (9, 13, 26):
                try:
                    for idx, one in enumerate(solution_images):
                        cap = "📎 Решение через Excel (скрин)." if num == 9 and idx == 0 else "📎 Пояснение к решению (скрин)."
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
                    return True
                except Exception as e:
                    logger.warning("ege_show_solution_%s images after code: %s", num, e)
            await _send_back_to_tasks()
            await query.answer("Решение отправлено.")
            return True

        if solution_images:
            try:
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
            return True
        if example:
            body_html, parse_mode = _format_homework_reply_for_telegram(f"Решение:\n\n{example}")
            if len(body_html) > 4000:
                body_html = body_html[:3990] + "\n\n… (обрезано)"
            await context.bot.send_message(chat_id=chat_id, text=body_html, parse_mode=parse_mode)
            await _send_back_to_tasks()
            await query.answer("Решение отправлено.")
            return True
        await query.answer("Решение для этого задания не добавлено.", show_alert=True)
        return True

    return False
