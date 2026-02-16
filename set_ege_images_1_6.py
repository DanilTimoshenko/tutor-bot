#!/usr/bin/env python3
"""
Проставляет для заданий ЕГЭ 1–6 пути к фото задания и решения (ege_images/N_task.png, ege_images/N_solution.png)
и при необходимости текст решения-кода (для 2, 5, 6 — тогда «Показать решение» выдаёт код текстом).

Запуск: python set_ege_images_1_6.py
"""
import asyncio
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import database as db

# Код решений для заданий 2, 5, 6 — бот выдаст их текстом по кнопке «Показать решение»
TASK_2_CODE = """for x in range(2):
    for y in range(2):
        for z in range(2):
            for w in range(2):
                if (z or (z == w) or (not (y <= x))) == False:
                    print(x, y, z, w)
# Получаем строки: 0 0 0 1; 1 0 0 1; 1 1 0 1.
# По таблице: первый столбец — w, третий — z; по строкам второй столбец — x, четвёртый — y.
# Ответ: wxzy"""

TASK_5_CODE = """def f3(n):
    s = ''
    while n > 0:
        s += str(n % 3)
        n //= 3
    return s[::-1]

for n in range(3, 1000):
    s = f3(n)
    if n % 3 == 0:
        s += s[-2:]
    else:
        s += f3((n % 3) * 5)
    r = int(s, 3)
    if r >= 290:
        print(n)
        break
# Ответ: 11"""

TASK_6_CODE = """from turtle import *
left(90)
k = 20
tracer(0)
screensize(2000, 2000)
pd()
for i in range(2):
    forward(24 * k)
    right(90)
    forward(20 * k)
    right(90)
pu()
forward(7 * k)
right(90)
forward(7 * k)
left(90)
pd()
for j in range(2):
    forward(30 * k)
    right(90)
    forward(27 * k)
    right(90)
pu()
for x in range(-100, 100):
    for y in range(-100, 100):
        goto(x * k, y * k)
        dot(3)
done()
# Ответ: 1141"""


EGE_1_6_TITLES = {
    1: "Графы, таблица дорог",
    2: "Таблицы истинности, логические выражения",
    3: "Базы данных, выручка",
    4: "Кодирование Фано",
    5: "Алгоритм, троичная система",
    6: "Исполнитель Черепаха",
}


async def fill_ege_tasks_1_6() -> None:
    """Заполняет задания 1–6: task_image, solution_image, код решений для 2, 5, 6."""
    for num in range(1, 7):
        task_image = f"ege_images/{num}_task.png"
        solution_image = f"ege_images/{num}_solution.png"
        example = ""
        if num == 2:
            example = TASK_2_CODE
        elif num == 5:
            example = TASK_5_CODE
        elif num == 6:
            example = TASK_6_CODE
        await db.set_ege_task(
            task_number=num,
            title=EGE_1_6_TITLES.get(num, f"Задание {num}"),
            example_solution=example,
            explanation="",
            source_url="https://code-enjoy.ru/courses/kurs_ege_po_informatike/",
            solution_image=solution_image,
            task_image=task_image,
        )


async def ensure_ege_tasks_1_6() -> None:
    """При старте бота: если задание 1 без task_image — заполняет 1–6. Чтобы задания 1–6 всегда были с фото и решением."""
    task1 = await db.get_ege_task(1)
    if task1 and (task1.get("task_image") or "").strip():
        return
    await fill_ege_tasks_1_6()


async def main() -> None:
    await db.init_db()
    await fill_ege_tasks_1_6()
    for num in range(1, 7):
        print(f"Задание {num}: ege_images/{num}_task.png, ege_images/{num}_solution.png")
    print("Готово. Задания 1–6 настроены.")


if __name__ == "__main__":
    asyncio.run(main())
