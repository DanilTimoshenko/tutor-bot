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

TASK_8_1_CODE = """from itertools import *
number = 1
for s in product(sorted("BEHPA"), repeat=5):
    x = "".join(s)
    if (x[0] != "H") and (x.count("B") == 2) and (number % 2 == 1):
        print(x, number)
    number += 1
# Ответ: 3107"""

TASK_8_2_CODE = """from itertools import product
cnt = 1
ans = -1
for word in product('ЕИОРТЯ', repeat=6):
    s = ''.join(word)
    if cnt % 2 != 0 and s[0] not in 'ЕИО' and s.count('Т') == 1:
        ans = cnt
    cnt += 1
print(ans)
# Ответ: 46655"""

TASK_9_CODE = """f = open("9.txt")
res = []
for i in f:
    a = [int(x) for x in i.split(";")]
    p3 = [x for x in a if a.count(x) == 3]
    np = [x for x in a if a.count(x) == 1]
    if len(p3) == 3 and len(np) == 3:
        if p3[0] < min(np) * 2:
            res += a
print(sum(res) // len(res))"""


EGE_TITLES = {
    1: "Графы, таблица дорог",
    2: "Таблицы истинности, логические выражения",
    3: "Базы данных, выручка",
    4: "Кодирование Фано",
    5: "Алгоритм, троичная система",
    6: "Исполнитель Черепаха",
    7: "Объём изображения, экономия трафика",
    8: "Задача 8.1",  # 8.2 в subtasks
    9: "Электронные таблицы, среднее",
}


async def fill_ege_tasks_1_6() -> None:
    """Заполняет задания 1–6: task_image, solution_image, код решений для 2, 5, 6."""
    for num in range(1, 7):
        task_image = f"ege_images/{num}_task.png"
        solution_image = f"ege_images/2_solution_text.png" if num == 2 else f"ege_images/{num}_solution.png"
        example = ""
        if num == 2:
            example = TASK_2_CODE
        elif num == 5:
            example = TASK_5_CODE
        elif num == 6:
            example = TASK_6_CODE
        await db.set_ege_task(
            task_number=num,
            title=EGE_TITLES.get(num, f"Задание {num}"),
            example_solution=example,
            explanation="",
            source_url="https://code-enjoy.ru/courses/kurs_ege_po_informatike/",
            solution_image=solution_image,
            task_image=task_image,
        )


async def fill_ege_tasks_7_9() -> None:
    """Заполняет задания 7, 8 (8.1 + 8.2), 9."""
    await db.set_ege_task(
        task_number=7,
        title=EGE_TITLES.get(7, "Задание 7"),
        example_solution="",
        explanation="",
        source_url="https://code-enjoy.ru/courses/kurs_ege_po_informatike/",
        solution_image="ege_images/7_solution.png",
        task_image="ege_images/7_task.png",
    )
    # Задание 8.1 — основная строка
    await db.set_ege_task(
        task_number=8,
        title="Задача 8.1 — пятибуквенные слова",
        example_solution=TASK_8_1_CODE,
        explanation="",
        source_url="https://code-enjoy.ru/courses/kurs_ege_po_informatike/",
        solution_image="ege_images/8_1_solution.png",
        task_image="ege_images/8_1_task.png",
    )
    # Задание 8.2 — в subtasks
    await db.set_ege_task_8_subtask(
        part=2,
        title="Задача 8.2 — шестибуквенные слова",
        task_image="ege_images/8_2_task.png",
        solution_image="ege_images/8_2_solution.png",
        example_solution=TASK_8_2_CODE,
    )
    await db.set_ege_task(
        task_number=9,
        title=EGE_TITLES.get(9, "Задание 9"),
        example_solution=TASK_9_CODE,
        explanation="",
        source_url="https://code-enjoy.ru/courses/kurs_ege_po_informatike/",
        solution_image="",
        task_image="ege_images/9_task.png",
    )


async def ensure_ege_tasks_1_6() -> None:
    """При старте бота: если у любого из заданий 1–9 нет условия или решения — заполняет 1–9 заново."""
    for num in range(1, 10):
        if num == 8:
            task = await db.get_ege_task(8)
            if not task or not (task.get("task_image") or "").strip():
                await fill_ege_tasks_1_6()
                await fill_ege_tasks_7_9()
                return
            task2 = await db.get_ege_task(8, subtask=2)
            if not task2 or not (task2.get("task_image") or "").strip():
                await fill_ege_tasks_1_6()
                await fill_ege_tasks_7_9()
                return
        else:
            task = await db.get_ege_task(num)
            if not task:
                await fill_ege_tasks_1_6()
                await fill_ege_tasks_7_9()
                return
            ti = (task.get("task_image") or "").strip()
            si = (task.get("solution_image") or "").strip()
            ex = (task.get("example_solution") or "").strip()
            if not ti or (not si and not ex):
                await fill_ege_tasks_1_6()
                await fill_ege_tasks_7_9()
                return
    return


async def main() -> None:
    await db.init_db()
    await fill_ege_tasks_1_6()
    await fill_ege_tasks_7_9()
    for num in range(1, 10):
        print(f"Задание {num}: настроено")
    print("Готово. Задания 1–9 настроены (8 = 8.1 и 8.2).")


if __name__ == "__main__":
    asyncio.run(main())
