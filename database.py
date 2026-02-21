"""
База данных: уроки и записи учеников.
Путь к файлу: из переменной окружения DATABASE_PATH (для Railway Volume) или по умолчанию tutor_bot.db в папке проекта.
"""
import os
import aiosqlite
from datetime import datetime

from config_loader import now_tz
from pathlib import Path

_db_path = os.environ.get("DATABASE_PATH", "").strip()
DB_PATH = Path(_db_path) if _db_path else Path(__file__).parent / "tutor_bot.db"


async def init_db():
    """Создаёт таблицы, если их нет. Директорию для файла БД создаёт при необходимости (для Railway Volume)."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS lessons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                lesson_date TEXT NOT NULL,
                lesson_time TEXT NOT NULL,
                duration_minutes INTEGER DEFAULT 60,
                max_students INTEGER DEFAULT 1,
                description TEXT DEFAULT '',
                lesson_link TEXT DEFAULT '',
                created_at TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lesson_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT,
                first_name TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(lesson_id, user_id),
                FOREIGN KEY (lesson_id) REFERENCES lessons(id)
            )
        """)
        try:
            await db.execute("ALTER TABLE lessons ADD COLUMN description TEXT DEFAULT ''")
        except Exception:
            pass
        try:
            await db.execute("ALTER TABLE lessons ADD COLUMN lesson_link TEXT DEFAULT ''")
        except Exception:
            pass
        try:
            await db.execute("ALTER TABLE blocked_slots ADD COLUMN lesson_link TEXT DEFAULT ''")
        except Exception:
            pass
        try:
            await db.execute("ALTER TABLE blocked_slots ADD COLUMN student_user_id INTEGER")
        except Exception:
            pass
        # blocked_slots: несколько учеников на одно время (без UNIQUE)
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='blocked_slots'"
        )
        has_blocked = (await cursor.fetchone()) is not None
        if has_blocked:
            await db.execute("""
                CREATE TABLE blocked_slots_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_name TEXT NOT NULL,
                    day_of_week INTEGER NOT NULL,
                    lesson_time TEXT NOT NULL,
                    student_username TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    lesson_link TEXT DEFAULT '',
                    student_user_id INTEGER
                )
            """)
            # Копируем все колонки; lesson_link и student_user_id могли быть добавлены ALTER'ами выше
            await db.execute("""
                INSERT INTO blocked_slots_new
                SELECT id, student_name, day_of_week, lesson_time, COALESCE(student_username,''), created_at,
                       COALESCE(lesson_link,''), student_user_id
                FROM blocked_slots
            """)
            await db.execute("DROP TABLE blocked_slots")
            await db.execute("ALTER TABLE blocked_slots_new RENAME TO blocked_slots")
        else:
            await db.execute("""
                CREATE TABLE blocked_slots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_name TEXT NOT NULL,
                    day_of_week INTEGER NOT NULL,
                    lesson_time TEXT NOT NULL,
                    student_username TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    lesson_link TEXT DEFAULT '',
                    student_user_id INTEGER
                )
            """)
        # Раздел ЕГЭ: 27 заданий (пример решения + краткое объяснение), источник — code-enjoy.ru
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ege_tasks (
                task_number INTEGER PRIMARY KEY CHECK (task_number >= 1 AND task_number <= 27),
                title TEXT NOT NULL DEFAULT '',
                example_solution TEXT NOT NULL DEFAULT '',
                explanation TEXT NOT NULL DEFAULT '',
                source_url TEXT DEFAULT '',
                solution_image TEXT DEFAULT '',
                task_image TEXT DEFAULT ''
            )
        """)
        for col in ("solution_image", "task_image", "subtasks"):
            try:
                await db.execute(f"ALTER TABLE ege_tasks ADD COLUMN {col} TEXT DEFAULT ''")
            except Exception:
                pass
        # Репетиторы, добавленные админом через бота (объединяются с TUTOR_USER_IDS из конфига)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tutor_user_ids (
                user_id INTEGER PRIMARY KEY
            )
        """)
        # Заявки учеников на свободное время (раздел для репетитора)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS free_time_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT DEFAULT '',
                first_name TEXT DEFAULT '',
                requested_date TEXT NOT NULL,
                requested_time TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        await db.commit()


async def get_tutor_user_ids_from_db() -> set:
    """ID репетиторов, добавленных через бота (админ)."""
    result = set()
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute("SELECT user_id FROM tutor_user_ids")
        rows = await cursor.fetchall()
        for (uid,) in rows:
            result.add(uid)
    return result


async def add_tutor_user_id(user_id: int) -> bool:
    """Добавить репетитора по ID (из админ-меню бота). Возвращает True если добавлен."""
    async with aiosqlite.connect(DB_PATH) as conn:
        try:
            await conn.execute("INSERT OR IGNORE INTO tutor_user_ids (user_id) VALUES (?)", (user_id,))
            await conn.commit()
            return True
        except Exception:
            return False


async def remove_tutor_user_id(user_id: int) -> bool:
    """Убрать репетитора из списка (добавленного через бота)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute("DELETE FROM tutor_user_ids WHERE user_id = ?", (user_id,))
        await conn.commit()
        return cursor.rowcount > 0


async def add_lesson(
    title: str,
    lesson_date: str,
    lesson_time: str,
    duration_minutes: int = 60,
    max_students: int = 1,
    description: str = "",
    lesson_link: str = "",
) -> int:
    """Добавляет урок. Возвращает id урока."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            """INSERT INTO lessons (title, lesson_date, lesson_time, duration_minutes, max_students, description, lesson_link, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (title, lesson_date, lesson_time, duration_minutes, max_students, description or "", (lesson_link or "").strip(), datetime.utcnow().isoformat()),
        )
        await conn.commit()
        return cursor.lastrowid


async def get_lessons_on_date(lesson_date: str):
    """Уроки на указанную дату (YYYY-MM-DD) с количеством записей."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """SELECT l.*,
                      (SELECT COUNT(*) FROM bookings b WHERE b.lesson_id = l.id) AS booked_count
               FROM lessons l
               WHERE l.lesson_date = ?
               ORDER BY l.lesson_time""",
            (lesson_date,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_lessons_at(lesson_date: str, lesson_time: str):
    """Уроки на указанные дату и время (для отправки ссылки за минуту до начала)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM lessons WHERE lesson_date = ? AND lesson_time = ?",
            (lesson_date, lesson_time),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_upcoming_lessons(limit: int = 50):
    """Список предстоящих уроков (дата >= сегодня), отсортированных по дате и времени.
    Используется дата в настроенном часовом поясе (TIMEZONE) или локальная."""
    today = now_tz().strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT l.*,
                      (SELECT COUNT(*) FROM bookings b WHERE b.lesson_id = l.id) AS booked_count
               FROM lessons l
               WHERE l.lesson_date >= ?
               ORDER BY l.lesson_date, l.lesson_time
               LIMIT ?""",
            (today, limit),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_lessons_in_range(from_date: str, to_date: str):
    """Уроки в диапазоне дат (включительно), по дате и времени."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT l.*,
                      (SELECT COUNT(*) FROM bookings b WHERE b.lesson_id = l.id) AS booked_count
               FROM lessons l
               WHERE l.lesson_date >= ? AND l.lesson_date <= ?
               ORDER BY l.lesson_date, l.lesson_time""",
            (from_date, to_date),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def add_blocked_slot(
    student_name: str,
    day_of_week: int,
    lesson_time: str,
    student_username: str = "",
) -> tuple[bool, str]:
    """Закрепляет слот за учеником. На одно время можно несколько учеников."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO blocked_slots (student_name, day_of_week, lesson_time, student_username, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (student_name.strip(), day_of_week, lesson_time, (student_username or "").strip().lstrip("@"), datetime.utcnow().isoformat()),
        )
        await db.commit()
    return True, f"Слот закреплён за {student_name.strip()}"


async def get_blocked_slots_for_student(username: str) -> list:
    """Занятые слоты, привязанные к этому ученику (по Telegram @username)."""
    if not (username or "").strip():
        return []
    u = (username or "").strip().lower().lstrip("@")
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM blocked_slots WHERE LOWER(TRIM(student_username)) = ? ORDER BY day_of_week, lesson_time",
            (u,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_blocked_slot_by_id(slot_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM blocked_slots WHERE id = ?", (slot_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_all_blocked_slots():
    """Все занятые слоты, отсортированные по дню и времени."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM blocked_slots ORDER BY day_of_week, lesson_time"
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_blocked_slot(day_of_week: int, lesson_time: str):
    """Возвращает первый занятый слот или None (для обратной совместимости)."""
    slots = await get_blocked_slots(day_of_week, lesson_time)
    return slots[0] if slots else None


async def get_blocked_slots(day_of_week: int, lesson_time: str) -> list:
    """Возвращает список слотов (несколько учеников на одно время)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM blocked_slots WHERE day_of_week = ? AND lesson_time = ? ORDER BY id",
            (day_of_week, lesson_time),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_blocked_slots_for_day(day_of_week: int) -> list:
    """Все закреплённые слоты на один день недели (для рассылки ссылки и сводки)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM blocked_slots WHERE day_of_week = ? ORDER BY lesson_time",
            (day_of_week,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def delete_blocked_slot(slot_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("DELETE FROM blocked_slots WHERE id = ?", (slot_id,))
        await db.commit()
        return cursor.rowcount > 0


async def get_lesson(lesson_id: int):
    """Один урок по id."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM lessons WHERE id = ?", (lesson_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def update_lesson_link(lesson_id: int, link: str) -> bool:
    """Установить или убрать ссылку на урок. Возвращает True если урок найден."""
    link = (link or "").strip()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "UPDATE lessons SET lesson_link = ? WHERE id = ?",
            (link, lesson_id),
        )
        await db.commit()
        return cursor.rowcount > 0


async def get_bookings_for_lesson(lesson_id: int):
    """Список записей на урок."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM bookings WHERE lesson_id = ? ORDER BY created_at",
            (lesson_id,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def book_lesson(lesson_id: int, user_id: int, username: str = None, first_name: str = None) -> tuple[bool, str]:
    """
    Записать ученика на урок.
    Возвращает (успех, сообщение).
    """
    lesson = await get_lesson(lesson_id)
    if not lesson:
        return False, "Урок не найден."
    lesson_date = lesson["lesson_date"]
    lesson_time = lesson["lesson_time"]
    max_students = lesson["max_students"]

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM bookings WHERE lesson_id = ?", (lesson_id,)
        )
        (count,) = (await cursor.fetchone())
        if count >= max_students:
            return False, f"На этот урок уже записано максимум человек ({max_students})."

        try:
            await db.execute(
                """INSERT INTO bookings (lesson_id, user_id, username, first_name, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (lesson_id, user_id, username or "", first_name or "", datetime.utcnow().isoformat()),
            )
            await db.commit()
            return True, f"✅ Вы записаны на урок «{lesson['title']}» — {lesson_date} в {lesson_time}."
        except aiosqlite.IntegrityError:
            return False, "Вы уже записаны на этот урок."


async def cancel_booking(lesson_id: int, user_id: int) -> tuple[bool, str]:
    """Отменить запись на урок."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM bookings WHERE lesson_id = ? AND user_id = ?",
            (lesson_id, user_id),
        )
        await db.commit()
        if cursor.rowcount:
            return True, "✅ Запись отменена."
        return False, "Запись не найдена."


async def get_my_bookings(user_id: int):
    """Уроки, на которые записан пользователь (предстоящие)."""
    today = now_tz().strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT l.*, b.created_at AS booked_at
               FROM bookings b
               JOIN lessons l ON l.id = b.lesson_id
               WHERE b.user_id = ? AND l.lesson_date >= ?
               ORDER BY l.lesson_date, l.lesson_time""",
            (user_id, today),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def delete_lesson(lesson_id: int) -> tuple[bool, dict | None, list]:
    """Удалить урок и все записи. Возвращает (успех, урок или None, список {user_id} записанных)."""
    lesson = await get_lesson(lesson_id)
    if not lesson:
        return False, None, []
    bookings = await get_bookings_for_lesson(lesson_id)
    user_ids = [b["user_id"] for b in bookings]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM bookings WHERE lesson_id = ?", (lesson_id,))
        cursor = await db.execute("DELETE FROM lessons WHERE id = ?", (lesson_id,))
        await db.commit()
        return (cursor.rowcount > 0, lesson, user_ids)


async def get_all_lesson_ids():
    """Все id уроков (для очистки напоминаний)."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT id FROM lessons")
        rows = await cursor.fetchall()
        return [r[0] for r in rows]


async def add_free_time_request(
    user_id: int,
    username: str,
    first_name: str,
    requested_date: str,
    requested_time: str,
) -> None:
    """Сохранить заявку ученика на свободное время."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO free_time_requests (user_id, username, first_name, requested_date, requested_time, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, username or "", first_name or "", requested_date, requested_time, datetime.utcnow().isoformat()),
        )
        await db.commit()


async def get_free_time_requests(limit: int = 50):
    """Список заявок на свободное время (новые сверху)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT * FROM free_time_requests ORDER BY created_at DESC LIMIT ?""",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def clear_all_schedule() -> tuple[int, int]:
    """Удаляет все уроки, записи и занятые слоты. Возвращает (кол-во уроков, кол-во слотов)."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM lessons")
        (n_lessons,) = (await cursor.fetchone())
        cursor = await db.execute("SELECT COUNT(*) FROM blocked_slots")
        (n_slots,) = (await cursor.fetchone())
        await db.execute("DELETE FROM bookings")
        await db.execute("DELETE FROM lessons")
        await db.execute("DELETE FROM blocked_slots")
        await db.commit()
    return (n_lessons, n_slots)


async def clear_lessons_only() -> int:
    """Удаляет только уроки и записи на них; занятые слоты не трогает. Возвращает кол-во удалённых уроков."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM lessons")
        (n,) = (await cursor.fetchone())
        await db.execute("DELETE FROM bookings")
        await db.execute("DELETE FROM lessons")
        await db.commit()
    return n


async def update_blocked_slot_link(slot_id: int, link: str) -> bool:
    """Установить ссылку для закреплённого слота."""
    link = (link or "").strip()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "UPDATE blocked_slots SET lesson_link = ? WHERE id = ?",
            (link, slot_id),
        )
        await db.commit()
        return cursor.rowcount > 0


async def update_blocked_slots_user_id(username: str, user_id: int) -> None:
    """Привязать user_id к слотам с данным username (чтобы отправлять ссылку за минуту до времени)."""
    if not (username or "").strip():
        return
    u = (username or "").strip().lower().lstrip("@")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE blocked_slots SET student_user_id = ? WHERE LOWER(TRIM(REPLACE(COALESCE(student_username,''), '@', ''))) = ?",
            (user_id, u),
        )
        await db.commit()


# ——— Раздел ЕГЭ (27 заданий) ———

def _subtask_row(task_number: int, row: dict, part: int, default_title: str) -> dict | None:
    import json
    raw = (row.get("subtasks") or "").strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
        sub = data.get(str(part)) or {}
        return {
            "task_number": task_number,
            "title": sub.get("title", default_title),
            "example_solution": sub.get("example_solution", ""),
            "explanation": sub.get("explanation", ""),
            "source_url": row.get("source_url", ""),
            "solution_image": sub.get("solution_image", ""),
            "task_image": sub.get("task_image", ""),
        }
    except Exception:
        return None


async def get_ege_task(task_number: int, subtask: int | None = None) -> dict | None:
    """Возвращает задание ЕГЭ по номеру (1–27). Для 8 и 11: subtask=1 (.X.1) или 2 (.X.2)."""
    if not (1 <= task_number <= 27):
        return None
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT task_number, title, example_solution, explanation, source_url, solution_image, task_image, subtasks FROM ege_tasks WHERE task_number = ?",
            (task_number,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        row = dict(row)
        if task_number == 8 and subtask == 2:
            out = _subtask_row(8, row, 2, "Задача 8.2")
            if out:
                return out
            return None
        if task_number == 11 and subtask == 2:
            out = _subtask_row(11, row, 2, "Задача 11.2")
            if out:
                return out
            return None
        if task_number == 14 and subtask == 2:
            out = _subtask_row(14, row, 2, "Задача 14.2")
            if out:
                return out
            return None
        if task_number == 17 and subtask == 2:
            out = _subtask_row(17, row, 2, "Задача 17.2")
            if out:
                return out
            return None
        if task_number == 19 and subtask == 2:
            out = _subtask_row(19, row, 2, "Задача 19.2")
            if out:
                return out
            return None
        if task_number == 20 and subtask == 2:
            out = _subtask_row(20, row, 2, "Задача 20.2")
            if out:
                return out
            return None
        if task_number == 21 and subtask == 2:
            out = _subtask_row(21, row, 2, "Задача 21.2")
            if out:
                return out
            return None
        if task_number == 22 and subtask == 2:
            out = _subtask_row(22, row, 2, "Задача 22.2")
            if out:
                return out
            return None
        if task_number == 24 and subtask == 2:
            out = _subtask_row(24, row, 2, "Задача 24.2")
            if out:
                return out
            return None
        if task_number == 26 and subtask is not None and 2 <= subtask <= 5:
            out = _subtask_row(26, row, subtask, f"Задача 26.{subtask}")
            if out:
                return out
            return None
        if task_number == 27 and subtask == 2:
            out = _subtask_row(27, row, 2, "Задача 27.2")
            if out:
                return out
            return None
        row.pop("subtasks", None)
        return row


async def set_ege_task(
    task_number: int,
    title: str = "",
    example_solution: str = "",
    explanation: str = "",
    source_url: str = "",
    solution_image: str = "",
    task_image: str = "",
) -> None:
    """Создаёт или обновляет задание ЕГЭ (1–27). task_image/solution_image — путь (ege_images/1_task.png) или URL."""
    if not (1 <= task_number <= 27):
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO ege_tasks (task_number, title, example_solution, explanation, source_url, solution_image, task_image)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(task_number) DO UPDATE SET
                 title = excluded.title,
                 example_solution = excluded.example_solution,
                 explanation = excluded.explanation,
                 source_url = excluded.source_url,
                 solution_image = excluded.solution_image,
                 task_image = excluded.task_image""",
            (task_number, title or "", example_solution or "", explanation or "", source_url or "", solution_image or "", task_image or ""),
        )
        await db.commit()


async def set_ege_task_8_subtask(part: int, title: str = "", task_image: str = "", solution_image: str = "", example_solution: str = "") -> None:
    """Обновляет подзадание 8.2 (part=2) в JSON subtasks строки task_number=8."""
    if part != 2:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT subtasks FROM ege_tasks WHERE task_number = 8")
        row = await cursor.fetchone()
        import json
        raw = (row[0] if row else "") or "{}"
        try:
            data = json.loads(raw)
        except Exception:
            data = {}
        data["2"] = {
            "title": title,
            "task_image": task_image or "",
            "solution_image": solution_image or "",
            "example_solution": example_solution or "",
        }
        await db.execute("UPDATE ege_tasks SET subtasks = ? WHERE task_number = 8", (json.dumps(data, ensure_ascii=False),))
        await db.commit()


async def set_ege_task_11_subtask(part: int, title: str = "", task_image: str = "", solution_image: str = "", example_solution: str = "") -> None:
    """Обновляет подзадание 11.2 (part=2) в JSON subtasks строки task_number=11."""
    if part != 2:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT subtasks FROM ege_tasks WHERE task_number = 11")
        row = await cursor.fetchone()
        import json
        raw = (row[0] if row else "") or "{}"
        try:
            data = json.loads(raw)
        except Exception:
            data = {}
        data["2"] = {
            "title": title,
            "task_image": task_image or "",
            "solution_image": solution_image or "",
            "example_solution": example_solution or "",
        }
        await db.execute("UPDATE ege_tasks SET subtasks = ? WHERE task_number = 11", (json.dumps(data, ensure_ascii=False),))
        await db.commit()


async def set_ege_task_14_subtask(part: int, title: str = "", task_image: str = "", solution_image: str = "", example_solution: str = "") -> None:
    """Обновляет подзадание 14.2 (part=2) в JSON subtasks строки task_number=14."""
    if part != 2:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT subtasks FROM ege_tasks WHERE task_number = 14")
        row = await cursor.fetchone()
        import json
        raw = (row[0] if row else "") or "{}"
        try:
            data = json.loads(raw)
        except Exception:
            data = {}
        data["2"] = {
            "title": title,
            "task_image": task_image or "",
            "solution_image": solution_image or "",
            "example_solution": example_solution or "",
        }
        await db.execute("UPDATE ege_tasks SET subtasks = ? WHERE task_number = 14", (json.dumps(data, ensure_ascii=False),))
        await db.commit()


async def set_ege_task_17_subtask(part: int, title: str = "", task_image: str = "", solution_image: str = "", example_solution: str = "") -> None:
    """Обновляет подзадание 17.2 (part=2) в JSON subtasks строки task_number=17."""
    if part != 2:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT subtasks FROM ege_tasks WHERE task_number = 17")
        row = await cursor.fetchone()
        import json
        raw = (row[0] if row else "") or "{}"
        try:
            data = json.loads(raw)
        except Exception:
            data = {}
        data["2"] = {
            "title": title,
            "task_image": task_image or "",
            "solution_image": solution_image or "",
            "example_solution": example_solution or "",
        }
        await db.execute("UPDATE ege_tasks SET subtasks = ? WHERE task_number = 17", (json.dumps(data, ensure_ascii=False),))
        await db.commit()


async def set_ege_task_19_subtask(part: int, title: str = "", task_image: str = "", solution_image: str = "", example_solution: str = "") -> None:
    """Обновляет подзадание 19.2 (part=2) в JSON subtasks строки task_number=19."""
    if part != 2:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT subtasks FROM ege_tasks WHERE task_number = 19")
        row = await cursor.fetchone()
        import json
        raw = (row[0] if row else "") or "{}"
        try:
            data = json.loads(raw)
        except Exception:
            data = {}
        data["2"] = {
            "title": title,
            "task_image": task_image or "",
            "solution_image": solution_image or "",
            "example_solution": example_solution or "",
        }
        await db.execute("UPDATE ege_tasks SET subtasks = ? WHERE task_number = 19", (json.dumps(data, ensure_ascii=False),))
        await db.commit()


async def set_ege_task_20_subtask(part: int, title: str = "", task_image: str = "", solution_image: str = "", example_solution: str = "") -> None:
    """Обновляет подзадание 20.2 (part=2) в JSON subtasks строки task_number=20."""
    if part != 2:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT subtasks FROM ege_tasks WHERE task_number = 20")
        row = await cursor.fetchone()
        import json
        raw = (row[0] if row else "") or "{}"
        try:
            data = json.loads(raw)
        except Exception:
            data = {}
        data["2"] = {
            "title": title,
            "task_image": task_image or "",
            "solution_image": solution_image or "",
            "example_solution": example_solution or "",
        }
        await db.execute("UPDATE ege_tasks SET subtasks = ? WHERE task_number = 20", (json.dumps(data, ensure_ascii=False),))
        await db.commit()


async def set_ege_task_21_subtask(part: int, title: str = "", task_image: str = "", solution_image: str = "", example_solution: str = "") -> None:
    """Обновляет подзадание 21.2 (part=2) в JSON subtasks строки task_number=21."""
    if part != 2:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT subtasks FROM ege_tasks WHERE task_number = 21")
        row = await cursor.fetchone()
        import json
        raw = (row[0] if row else "") or "{}"
        try:
            data = json.loads(raw)
        except Exception:
            data = {}
        data["2"] = {
            "title": title,
            "task_image": task_image or "",
            "solution_image": solution_image or "",
            "example_solution": example_solution or "",
        }
        await db.execute("UPDATE ege_tasks SET subtasks = ? WHERE task_number = 21", (json.dumps(data, ensure_ascii=False),))
        await db.commit()


async def set_ege_task_22_subtask(part: int, title: str = "", task_image: str = "", solution_image: str = "", example_solution: str = "") -> None:
    """Обновляет подзадание 22.2 (part=2) в JSON subtasks строки task_number=22."""
    if part != 2:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT subtasks FROM ege_tasks WHERE task_number = 22")
        row = await cursor.fetchone()
        import json
        raw = (row[0] if row else "") or "{}"
        try:
            data = json.loads(raw)
        except Exception:
            data = {}
        data["2"] = {
            "title": title,
            "task_image": task_image or "",
            "solution_image": solution_image or "",
            "example_solution": example_solution or "",
        }
        await db.execute("UPDATE ege_tasks SET subtasks = ? WHERE task_number = 22", (json.dumps(data, ensure_ascii=False),))
        await db.commit()


async def set_ege_task_24_subtask(part: int, title: str = "", task_image: str = "", solution_image: str = "", example_solution: str = "") -> None:
    """Обновляет подзадание 24.2 (part=2) в JSON subtasks строки task_number=24."""
    if part != 2:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT subtasks FROM ege_tasks WHERE task_number = 24")
        row = await cursor.fetchone()
        import json
        raw = (row[0] if row else "") or "{}"
        try:
            data = json.loads(raw)
        except Exception:
            data = {}
        data["2"] = {
            "title": title,
            "task_image": task_image or "",
            "solution_image": solution_image or "",
            "example_solution": example_solution or "",
        }
        await db.execute("UPDATE ege_tasks SET subtasks = ? WHERE task_number = 24", (json.dumps(data, ensure_ascii=False),))
        await db.commit()


async def set_ege_task_26_subtask(part: int, title: str = "", task_image: str = "", solution_image: str = "", example_solution: str = "") -> None:
    """Обновляет подзадание 26.2–26.5 (part=2,3,4,5) в JSON subtasks строки task_number=26."""
    if part not in (2, 3, 4, 5):
        return
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT subtasks FROM ege_tasks WHERE task_number = 26")
        row = await cursor.fetchone()
        import json
        raw = (row[0] if row else "") or "{}"
        try:
            data = json.loads(raw)
        except Exception:
            data = {}
        data[str(part)] = {
            "title": title,
            "task_image": task_image or "",
            "solution_image": solution_image or "",
            "example_solution": example_solution or "",
        }
        await db.execute("UPDATE ege_tasks SET subtasks = ? WHERE task_number = 26", (json.dumps(data, ensure_ascii=False),))
        await db.commit()


async def set_ege_task_27_subtask(part: int, title: str = "", task_image: str = "", solution_image: str = "", example_solution: str = "") -> None:
    """Обновляет подзадание 27.2 (part=2) в JSON subtasks строки task_number=27."""
    if part != 2:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT subtasks FROM ege_tasks WHERE task_number = 27")
        row = await cursor.fetchone()
        import json
        raw = (row[0] if row else "") or "{}"
        try:
            data = json.loads(raw)
        except Exception:
            data = {}
        data["2"] = {
            "title": title,
            "task_image": task_image or "",
            "solution_image": solution_image or "",
            "example_solution": example_solution or "",
        }
        await db.execute("UPDATE ege_tasks SET subtasks = ? WHERE task_number = 27", (json.dumps(data, ensure_ascii=False),))
        await db.commit()


async def get_all_ege_task_numbers() -> list[int]:
    """Номера заданий ЕГЭ, для которых есть запись в БД."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT task_number FROM ege_tasks ORDER BY task_number")
        rows = await cursor.fetchall()
        return [r[0] for r in rows]
