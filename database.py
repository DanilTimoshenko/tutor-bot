"""
База данных: уроки и записи учеников.
Путь к файлу: из переменной окружения DATABASE_PATH (для Railway Volume) или по умолчанию tutor_bot.db в папке проекта.
"""
import os
import aiosqlite
from datetime import datetime
from pathlib import Path

_db_path = os.environ.get("DATABASE_PATH", "").strip()
DB_PATH = Path(_db_path) if _db_path else Path(__file__).parent / "tutor_bot.db"


async def init_db():
    """Создаёт таблицы, если их нет."""
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
                    created_at TEXT NOT NULL
                )
            """)
            await db.execute("INSERT INTO blocked_slots_new SELECT id, student_name, day_of_week, lesson_time, COALESCE(student_username,''), created_at FROM blocked_slots")
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
                    created_at TEXT NOT NULL
                )
            """)
        await db.commit()


async def add_lesson(
    title: str,
    lesson_date: str,
    lesson_time: str,
    duration_minutes: int = 60,
    max_students: int = 1,
    description: str = "",
) -> int:
    """Добавляет урок. Возвращает id урока."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            """INSERT INTO lessons (title, lesson_date, lesson_time, duration_minutes, max_students, description, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (title, lesson_date, lesson_time, duration_minutes, max_students, description or "", datetime.utcnow().isoformat()),
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


async def get_upcoming_lessons(limit: int = 50):
    """Список предстоящих уроков (дата >= сегодня), отсортированных по дате и времени."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
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
    today = datetime.utcnow().strftime("%Y-%m-%d")
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
