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
    8: "Задача 8.1",
    9: "Электронные таблицы, среднее",
    10: "Поиск «сам» в составе слов",
    11: "Задача 11.1",
    12: "Исполнитель МТ (машина Тьюринга)",
    13: "IP-адреса, маска сети",
    14: "Задача 14.1",
    15: "Логическое выражение (наибольшее A)",
    16: "Рекурсия F(n) = n² + F(n-1)",
    17: "Задача 17.1",
    18: "Робот на поле, макс/мин сумма монет",
    19: "Задача 19.1 — куча камней, ходы −1 и −3",
    20: "Задача 20.1 — Петя выигрывает 2-м ходом",
    21: "Задача 21.1 — Ваня выигрывает 1-м или 2-м",
    22: "Задача 22.1 — процессы, сколько одновременно в 14 мс",
    23: "Исполнитель: −3 и :3, траектория через 27",
    24: "Задача 24.1 — строка D и 50 цифр",
}

# Задание 18: решение — несколько скринов (таблица, ДП макс/мин). Пути через "|".
TASK_18_SOLUTION_IMAGES = "ege_images/18_solution_1.png|ege_images/18_solution_2.png|ege_images/18_solution_3.png"

TASK_19_1_CODE = """from functools import lru_cache

@lru_cache(None)
def game(x):
    if x <= 11:  # условие выигрыша
        return 0
    moves = [game(x - 1), game(x - 3)]  # перечисляем ходы
    n = [i for i in moves if i <= 0]
    if n:
        return -max(n) + 1
    return -max(moves)

for i in range(12, 100):
    if game(i - 1) == 1 or game(i - 3) == 1:  # Если Петя поддаётся
        print(i)
# Ответ: 17"""

TASK_19_2_CODE = """from functools import lru_cache

@lru_cache(None)
def game(x):
    if x <= 25:  # условие выигрыша
        return 0
    moves = [game(x - 3), game(x - 6)]  # перечисляем ходы
    if x > 0:
        moves.append(game(x // 3))
    n = [i for i in moves if i <= 0]
    if n:
        return -max(n) + 1
    return -max(moves)

for i in range(26, 100):
    if game(i) == -1:
        print(i)
# Ответ: 78"""

TASK_20_1_CODE = """from functools import lru_cache

@lru_cache(None)
def game(x):
    if x <= 11:
        return 0
    moves = [game(x - 1), game(x - 3)]
    n = [i for i in moves if i <= 0]
    if n:
        return -max(n) + 1
    return -max(moves)

for i in range(12, 100):
    if game(i) == 2:
        print(i)
# Ответ: 16 18"""

TASK_20_2_CODE = """from functools import lru_cache

@lru_cache(None)
def game(x):
    if x <= 25:
        return 0
    moves = [game(x - 3), game(x - 6)]
    if x > 0:
        moves.append(game(x // 3))
    n = [i for i in moves if i <= 0]
    if n:
        return -max(n) + 1
    return -max(moves)

for i in range(26, 100):
    if game(i) == 2:
        print(i)
# Ответ: 81 82"""

TASK_21_1_CODE = """from functools import lru_cache

@lru_cache(None)
def game(x):
    if x <= 11:
        return 0
    moves = [game(x - 1), game(x - 3)]
    n = [i for i in moves if i <= 0]
    if n:
        return -max(n) + 1
    return -max(moves)

for i in range(12, 100):
    if game(i) == -2:
        print(i)
# Ответ: 19"""

TASK_21_2_CODE = """from functools import lru_cache

@lru_cache(None)
def game(x):
    if x <= 25:
        return 0
    moves = [game(x - 3), game(x - 6)]
    if x > 0:
        moves.append(game(x // 3))
    n = [i for i in moves if i <= 0]
    if n:
        return -max(n) + 1
    return -max(moves)

for i in range(26, 100):
    if game(i) == -2:
        print(i)
# Ответ: 87"""

# 22.1: процессы из 22.xls, время старта минимально — сколько выполняются в 14 мс
TASK_22_1_CODE = """# Данные из 22.xls: ID, время (мс), зависимости через ";". 0 = нет зависимостей.
# Читаем файл или задаём список: (id, duration, [dep_ids])
def count_at_t(processes, t_ms):
    end_time = {}
    for pid, duration, deps in processes:
        start = 0 if not deps or deps == [0] else max(end_time.get(d, 0) for d in deps)
        end_time[pid] = start + duration
    return sum(1 for pid, duration, deps in processes
               if (0 if not deps or deps == [0] else max(end_time.get(d, 0) for d in deps)) < t_ms
               <= (0 if not deps or deps == [0] else max(end_time.get(d, 0) for d in deps)) + duration)

# Пример: разбор из 22.txt (id;duration;deps)
# with open('22.txt') as f: ...
# Для 22.xls — openpyxl. Ответ: число процессов в 14 мс."""

# 22.2: минимальное общее время выполнения всех процессов
TASK_22_2_CODE = """# Те же данные. Ответ = максимум из (время_окончания) по всем процессам.
def min_total_time(processes):
    end_time = {}
    for pid, duration, deps in processes:
        start = 0 if not deps or deps == [0] else max(end_time.get(d, 0) for d in deps)
        end_time[pid] = start + duration
    return max(end_time.values())

# processes = [(id, duration, [dep_ids]), ...] из 22.xls
# print(min_total_time(processes))"""

TASK_23_CODE = """def f(a, b):
    if a < b:
        return 0
    if a == b:
        return 1
    return f(a - 3, b) + f(a // 3, b)

print(f(81, 27) * f(27, 3))
# Ответ: 10"""

# 24.1: макс длина подстроки: начинается с D, ровно 50 цифр, других D нет. Два способа.
TASK_24_1_CODE = """# Способ 1 — регулярное выражение
from re import findall
f = open('24.txt')
s = f.readline()
reg = r'D(?:[A-CE-Z]*[0-9]){50}[A-CE-Z]*'
print(len(max(findall(reg, s), key=len)))

# Способ 2 — проход по строке
# f = open('24.txt')
# s = f.readline()
# ans = 0
# for i in range(len(s)):
#     if s[i] == 'D':
#         cnt_digits = 0
#         for j in range(i + 1, len(s)):
#             if s[j] in '0123456789':
#                 cnt_digits += 1
#             if cnt_digits == 50:
#                 ans = max(ans, j - i + 1)
#             elif cnt_digits > 50:
#                 ans = max(ans, j - i)
#                 break
#             if s[j] == 'D':
#                 break
# print(ans)"""

# 24.2: макс длина: с нечётной цифры, ровно 30 букв F, других нечётных цифр нет. Два способа.
TASK_24_2_CODE = """# Способ 1 — регулярное выражение
from re import findall
f = open('24.txt')
s = f.readline()
reg = r'[13579](?:[02468A-EG-Z]*F){30}[02468A-EG-Z]*'
res = findall(reg, s)
print(len(max(res, key=len)) if res else 0)

# Способ 2 — проход по строке
# f = open('24.txt')
# s = f.readline()
# ans = 0
# for i in range(len(s)):
#     if s[i] in '13579':
#         cnt_f = 0
#         for j in range(i + 1, len(s)):
#             if s[j] == 'F':
#                 cnt_f += 1
#             if cnt_f > 30:
#                 ans = max(ans, j - i)
#                 break
#             if s[j] in '13579':
#                 break
# print(ans)"""

TASK_15_CODE = """def f(a):
    for x in range(1000):
        for y in range(1000):
            if not ((x + 3 * y > a) or (x < 18) or (y < 33)):
                return False
    return True

for a in range(1000, 0, -1):
    if f(a):
        print(a)
        break
# Ответ: 116"""

TASK_16_CODE = """from functools import lru_cache

@lru_cache(None)
def f(n):
    if n == 1:
        return 1
    return n ** 2 + f(n - 1)

for i in range(1, 2026):
    f(i)
print(f(2025) - f(2022))
# Ответ: 12289730"""

TASK_17_1_CODE = """f = open('17.14.txt')
a = [int(x) for x in f.readlines()]
max_13 = max([x for x in a if abs(x) % 100 == 13])
cnt = 0
max_sum = -10000
for i in range(len(a) - 2):
    n = a[i:i + 3]
    t = [10_000 <= abs(x) < 100_000 for x in n]
    if sum(t) == 2 and sum(n) <= max_13:
        cnt += 1
        max_sum = max(max_sum, sum(n))
print(cnt, max_sum)"""

TASK_17_2_CODE = """f = open('17.txt')
a = [int(x) for x in f]
max_19 = max([x for x in a if abs(x) % 100 == 19])
res = []
for i in range(len(a) - 1):
    if (10 <= abs(a[i]) <= 99) != (10 <= abs(a[i+1]) <= 99) and (a[i] + a[i+1] <= max_19):
        res.append(a[i] + a[i+1])
print(len(res), max(res))"""

TASK_13_CODE = """from ipaddress import *
net = ip_network('186.215.243.5/255.255.192.0', 0)
# Предпоследний адрес — последний допустимый для компьютера (последний — широковещательный)
print(str(net[-2]).replace('.', ''))
# Ответ: 186215255254"""

TASK_14_1_CODE = """for x in range(0, 27):
    a1 = 2*27**7 + 1*27**6 + 7*27**4 + x*27**3 + 7*27**2 + 9*27**1 + 2
    a2 = 5*27**6 + 6*27**5 + 5*27**4 + x*27**3 + 2*27**2 + 1*27 + 1
    a = a1 + a2
    if a % 26 == 0:
        print(a // 26)
        break
# Ответ: 897607140"""

TASK_14_2_CODE = """def ss(n):
    res = ""
    while n > 0:
        res = str(n % 5) + res
        n //= 5
    return res

mx = 0
ans = 0
for x in range(2030 + 1):
    s = 7**150 - 7**100 - x
    nulls = ss(s)
    if nulls.count("0") >= mx:
        mx = nulls.count("0")
        ans = x
print(ans)
# Ответ: 623"""


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
        solution_image="ege_images/9_solution_excel.png",  # скрин «Решение через Excel»
        task_image="ege_images/9_task.png",
    )


async def fill_ege_tasks_10_11_12() -> None:
    """Заполняет задания 10, 11 (11.1 + 11.2), 12."""
    await db.set_ege_task(
        task_number=10,
        title=EGE_TITLES.get(10, "Задание 10"),
        example_solution="",
        explanation="",
        source_url="https://code-enjoy.ru/courses/kurs_ege_po_informatike/",
        solution_image="ege_images/10_solution.png",
        task_image="ege_images/10_task.png",
    )
    await db.set_ege_task(
        task_number=11,
        title="Задача 11.1 — серийные номера, мощность алфавита",
        example_solution="",
        explanation="",
        source_url="https://code-enjoy.ru/courses/kurs_ege_po_informatike/",
        solution_image="ege_images/11_1_solution.png",
        task_image="ege_images/11_1_task.png",
    )
    await db.set_ege_task_11_subtask(
        part=2,
        title="Задача 11.2 — серийные номера, 248 символов",
        task_image="ege_images/11_2_task.png",
        solution_image="ege_images/11_2_solution.png",
        example_solution="",
    )
    # Задание 12: два скрина условия (отправляются оба сразу)
    await db.set_ege_task(
        task_number=12,
        title=EGE_TITLES.get(12, "Задание 12"),
        example_solution="",
        explanation="",
        source_url="https://code-enjoy.ru/courses/kurs_ege_po_informatike/",
        solution_image="ege_images/12_solution.png",
        task_image="ege_images/12_task1.png|ege_images/12_task2.png",
    )


async def fill_ege_tasks_13_14() -> None:
    """Задание 13 — два решения (код + скрин). Задание 14 — два типа (14.1 и 14.2)."""
    await db.set_ege_task(
        task_number=13,
        title=EGE_TITLES.get(13, "Задание 13"),
        example_solution=TASK_13_CODE,
        explanation="",
        source_url="https://code-enjoy.ru/courses/kurs_ege_po_informatike/",
        solution_image="ege_images/13_solution_text.png",
        task_image="ege_images/13_task.png",
    )
    await db.set_ege_task(
        task_number=14,
        title="Задача 14.1 — система счисления с основанием 27",
        example_solution=TASK_14_1_CODE,
        explanation="",
        source_url="https://code-enjoy.ru/courses/kurs_ege_po_informatike/",
        solution_image="ege_images/14_1_solution.png",
        task_image="ege_images/14_1_task.png",
    )
    await db.set_ege_task_14_subtask(
        part=2,
        title="Задача 14.2 — пятеричная система, максимум нулей",
        task_image="ege_images/14_2_task.png",
        solution_image="ege_images/14_2_solution.png",
        example_solution=TASK_14_2_CODE,
    )


async def fill_ege_tasks_15_16_17() -> None:
    """Задания 15, 16 и 17 (17.1 + 17.2)."""
    await db.set_ege_task(
        task_number=15,
        title=EGE_TITLES.get(15, "Задание 15"),
        example_solution=TASK_15_CODE,
        explanation="",
        source_url="https://code-enjoy.ru/courses/kurs_ege_po_informatike/",
        solution_image="ege_images/15_solution.png",
        task_image="ege_images/15_task.png",
    )
    await db.set_ege_task(
        task_number=16,
        title=EGE_TITLES.get(16, "Задание 16"),
        example_solution=TASK_16_CODE,
        explanation="",
        source_url="https://code-enjoy.ru/courses/kurs_ege_po_informatike/",
        solution_image="ege_images/16_solution.png",
        task_image="ege_images/16_task.png",
    )
    await db.set_ege_task(
        task_number=17,
        title="Задача 17.1 — тройки, файл 17.14.txt",
        example_solution=TASK_17_1_CODE,
        explanation="",
        source_url="https://code-enjoy.ru/courses/kurs_ege_po_informatike/",
        solution_image="ege_images/17_1_solution.png",
        task_image="ege_images/17_1_task.png",
    )
    await db.set_ege_task_17_subtask(
        part=2,
        title="Задача 17.2 — пары, двузначные, файл 17.txt",
        task_image="ege_images/17_2_task.png",
        solution_image="ege_images/17_2_solution.png",
        example_solution=TASK_17_2_CODE,
    )


async def fill_ege_tasks_18_19_20_21() -> None:
    """Задание 18 — несколько скринов решений; 19–21 — по два типа."""
    await db.set_ege_task(
        task_number=18,
        title=EGE_TITLES.get(18, "Задание 18"),
        example_solution="",
        explanation="",
        source_url="https://code-enjoy.ru/courses/kurs_ege_po_informatike/",
        solution_image=TASK_18_SOLUTION_IMAGES,
        task_image="ege_images/18_task.png",
    )
    await db.set_ege_task(
        task_number=19,
        title="Задача 19.1 — Ваня выиграл первым ходом после хода Пети",
        example_solution=TASK_19_1_CODE,
        explanation="",
        source_url="https://code-enjoy.ru/courses/kurs_ege_po_informatike/",
        solution_image="ege_images/19_1_solution.png",
        task_image="ege_images/19_1_task.png",
    )
    await db.set_ege_task_19_subtask(
        part=2,
        title="Задача 19.2 — куча, ходы −3, −6, :3; конец при ≤25",
        task_image="ege_images/19_2_task.png",
        solution_image="ege_images/19_2_solution.png",
        example_solution=TASK_19_2_CODE,
    )
    await db.set_ege_task(
        task_number=20,
        title="Задача 20.1 — Петя выигрывает вторым ходом (игра из 19.1)",
        example_solution=TASK_20_1_CODE,
        explanation="",
        source_url="https://code-enjoy.ru/courses/kurs_ege_po_informatike/",
        solution_image="ege_images/20_1_solution.png",
        task_image="ege_images/20_1_task.png",
    )
    await db.set_ege_task_20_subtask(
        part=2,
        title="Задача 20.2 — два наименьших S (игра из задания 19)",
        task_image="ege_images/20_2_task.png",
        solution_image="ege_images/20_2_solution.png",
        example_solution=TASK_20_2_CODE,
    )
    await db.set_ege_task(
        task_number=21,
        title="Задача 21.1 — макс S: Ваня выигрывает 1-м или 2-м, не только 1-м",
        example_solution=TASK_21_1_CODE,
        explanation="",
        source_url="https://code-enjoy.ru/courses/kurs_ege_po_informatike/",
        solution_image="ege_images/21_1_solution.png",
        task_image="ege_images/21_1_task.png",
    )
    await db.set_ege_task_21_subtask(
        part=2,
        title="Задача 21.2 — мин S: те же условия",
        task_image="ege_images/21_2_task.png",
        solution_image="ege_images/21_2_solution.png",
        example_solution=TASK_21_2_CODE,
    )


async def fill_ege_tasks_22_23_24() -> None:
    """Задание 22 — два типа (22.1, 22.2); 23 — одно; 24 — два типа (24.1, 24.2), по два кода."""
    await db.set_ege_task(
        task_number=22,
        title="Задача 22.1 — процессы из 22.xls, сколько одновременно в 14 мс",
        example_solution=TASK_22_1_CODE,
        explanation="",
        source_url="https://code-enjoy.ru/courses/kurs_ege_po_informatike/",
        solution_image="ege_images/22_1_solution.png",
        task_image="ege_images/22_1_task.png",
    )
    await db.set_ege_task_22_subtask(
        part=2,
        title="Задача 22.2 — минимальное общее время выполнения",
        task_image="ege_images/22_2_task.png",
        solution_image="ege_images/22_2_solution.png",
        example_solution=TASK_22_2_CODE,
    )
    await db.set_ege_task(
        task_number=23,
        title=EGE_TITLES.get(23, "Задание 23"),
        example_solution=TASK_23_CODE,
        explanation="",
        source_url="https://code-enjoy.ru/courses/kurs_ege_po_informatike/",
        solution_image="ege_images/23_solution.png",
        task_image="ege_images/23_task.png",
    )
    await db.set_ege_task(
        task_number=24,
        title="Задача 24.1 — строка D, ровно 50 цифр, без других D",
        example_solution=TASK_24_1_CODE,
        explanation="",
        source_url="https://code-enjoy.ru/courses/kurs_ege_po_informatike/",
        solution_image="ege_images/24_1_solution.png",
        task_image="ege_images/24_1_task.png",
    )
    await db.set_ege_task_24_subtask(
        part=2,
        title="Задача 24.2 — с нечётной цифры, ровно 30 F",
        task_image="ege_images/24_2_task.png",
        solution_image="ege_images/24_2_solution.png",
        example_solution=TASK_24_2_CODE,
    )


async def ensure_ege_tasks_1_6() -> None:
    """При старте бота: если у любого из заданий 1–24 нет условия или решения — заполняет заново."""
    for num in range(1, 25):
        if num == 8:
            task = await db.get_ege_task(8)
            if not task or not (task.get("task_image") or "").strip():
                await fill_ege_tasks_1_6()
                await fill_ege_tasks_7_9()
                await fill_ege_tasks_10_11_12()
                await fill_ege_tasks_13_14()
                await fill_ege_tasks_15_16_17()
                await fill_ege_tasks_18_19_20_21()
                await fill_ege_tasks_22_23_24()
                return
            task2 = await db.get_ege_task(8, subtask=2)
            if not task2 or not (task2.get("task_image") or "").strip():
                await fill_ege_tasks_1_6()
                await fill_ege_tasks_7_9()
                await fill_ege_tasks_10_11_12()
                await fill_ege_tasks_13_14()
                await fill_ege_tasks_15_16_17()
                await fill_ege_tasks_18_19_20_21()
                await fill_ege_tasks_22_23_24()
                return
        elif num == 11:
            task = await db.get_ege_task(11)
            if not task or not (task.get("task_image") or "").strip():
                await fill_ege_tasks_1_6()
                await fill_ege_tasks_7_9()
                await fill_ege_tasks_10_11_12()
                await fill_ege_tasks_13_14()
                await fill_ege_tasks_15_16_17()
                await fill_ege_tasks_18_19_20_21()
                await fill_ege_tasks_22_23_24()
                return
            task2 = await db.get_ege_task(11, subtask=2)
            if not task2 or not (task2.get("task_image") or "").strip():
                await fill_ege_tasks_1_6()
                await fill_ege_tasks_7_9()
                await fill_ege_tasks_10_11_12()
                await fill_ege_tasks_13_14()
                await fill_ege_tasks_15_16_17()
                await fill_ege_tasks_18_19_20_21()
                await fill_ege_tasks_22_23_24()
                return
        elif num == 14:
            task = await db.get_ege_task(14)
            if not task or not (task.get("task_image") or "").strip():
                await fill_ege_tasks_1_6()
                await fill_ege_tasks_7_9()
                await fill_ege_tasks_10_11_12()
                await fill_ege_tasks_13_14()
                await fill_ege_tasks_15_16_17()
                await fill_ege_tasks_18_19_20_21()
                await fill_ege_tasks_22_23_24()
                return
            task2 = await db.get_ege_task(14, subtask=2)
            if not task2 or not (task2.get("task_image") or "").strip():
                await fill_ege_tasks_1_6()
                await fill_ege_tasks_7_9()
                await fill_ege_tasks_10_11_12()
                await fill_ege_tasks_13_14()
                await fill_ege_tasks_15_16_17()
                await fill_ege_tasks_18_19_20_21()
                await fill_ege_tasks_22_23_24()
                return
        elif num == 17:
            task = await db.get_ege_task(17)
            if not task or not (task.get("task_image") or "").strip():
                await fill_ege_tasks_1_6()
                await fill_ege_tasks_7_9()
                await fill_ege_tasks_10_11_12()
                await fill_ege_tasks_13_14()
                await fill_ege_tasks_15_16_17()
                await fill_ege_tasks_18_19_20_21()
                await fill_ege_tasks_22_23_24()
                return
            task2 = await db.get_ege_task(17, subtask=2)
            if not task2 or not (task2.get("task_image") or "").strip():
                await fill_ege_tasks_1_6()
                await fill_ege_tasks_7_9()
                await fill_ege_tasks_10_11_12()
                await fill_ege_tasks_13_14()
                await fill_ege_tasks_15_16_17()
                await fill_ege_tasks_18_19_20_21()
                await fill_ege_tasks_22_23_24()
                return
        elif num == 19:
            task = await db.get_ege_task(19)
            if not task or not (task.get("task_image") or "").strip():
                await fill_ege_tasks_1_6()
                await fill_ege_tasks_7_9()
                await fill_ege_tasks_10_11_12()
                await fill_ege_tasks_13_14()
                await fill_ege_tasks_15_16_17()
                await fill_ege_tasks_18_19_20_21()
                await fill_ege_tasks_22_23_24()
                return
            task2 = await db.get_ege_task(19, subtask=2)
            if not task2 or not (task2.get("task_image") or "").strip():
                await fill_ege_tasks_1_6()
                await fill_ege_tasks_7_9()
                await fill_ege_tasks_10_11_12()
                await fill_ege_tasks_13_14()
                await fill_ege_tasks_15_16_17()
                await fill_ege_tasks_18_19_20_21()
                return
        elif num == 20:
            task = await db.get_ege_task(20)
            if not task or not (task.get("task_image") or "").strip():
                await fill_ege_tasks_1_6()
                await fill_ege_tasks_7_9()
                await fill_ege_tasks_10_11_12()
                await fill_ege_tasks_13_14()
                await fill_ege_tasks_15_16_17()
                await fill_ege_tasks_18_19_20_21()
                await fill_ege_tasks_22_23_24()
                return
            task2 = await db.get_ege_task(20, subtask=2)
            if not task2 or not (task2.get("task_image") or "").strip():
                await fill_ege_tasks_1_6()
                await fill_ege_tasks_7_9()
                await fill_ege_tasks_10_11_12()
                await fill_ege_tasks_13_14()
                await fill_ege_tasks_15_16_17()
                await fill_ege_tasks_18_19_20_21()
                await fill_ege_tasks_22_23_24()
                return
        elif num == 21:
            task = await db.get_ege_task(21)
            if not task or not (task.get("task_image") or "").strip():
                await fill_ege_tasks_1_6()
                await fill_ege_tasks_7_9()
                await fill_ege_tasks_10_11_12()
                await fill_ege_tasks_13_14()
                await fill_ege_tasks_15_16_17()
                await fill_ege_tasks_18_19_20_21()
                await fill_ege_tasks_22_23_24()
                return
            task2 = await db.get_ege_task(21, subtask=2)
            if not task2 or not (task2.get("task_image") or "").strip():
                await fill_ege_tasks_1_6()
                await fill_ege_tasks_7_9()
                await fill_ege_tasks_10_11_12()
                await fill_ege_tasks_13_14()
                await fill_ege_tasks_15_16_17()
                await fill_ege_tasks_18_19_20_21()
                await fill_ege_tasks_22_23_24()
                return
        elif num == 22:
            task = await db.get_ege_task(22)
            if not task or not (task.get("task_image") or "").strip():
                await fill_ege_tasks_1_6()
                await fill_ege_tasks_7_9()
                await fill_ege_tasks_10_11_12()
                await fill_ege_tasks_13_14()
                await fill_ege_tasks_15_16_17()
                await fill_ege_tasks_18_19_20_21()
                await fill_ege_tasks_22_23_24()
                return
            task2 = await db.get_ege_task(22, subtask=2)
            if not task2 or not (task2.get("task_image") or "").strip():
                await fill_ege_tasks_1_6()
                await fill_ege_tasks_7_9()
                await fill_ege_tasks_10_11_12()
                await fill_ege_tasks_13_14()
                await fill_ege_tasks_15_16_17()
                await fill_ege_tasks_18_19_20_21()
                await fill_ege_tasks_22_23_24()
                return
        elif num == 24:
            task = await db.get_ege_task(24)
            if not task or not (task.get("task_image") or "").strip():
                await fill_ege_tasks_1_6()
                await fill_ege_tasks_7_9()
                await fill_ege_tasks_10_11_12()
                await fill_ege_tasks_13_14()
                await fill_ege_tasks_15_16_17()
                await fill_ege_tasks_18_19_20_21()
                await fill_ege_tasks_22_23_24()
                return
            task2 = await db.get_ege_task(24, subtask=2)
            if not task2 or not (task2.get("task_image") or "").strip():
                await fill_ege_tasks_1_6()
                await fill_ege_tasks_7_9()
                await fill_ege_tasks_10_11_12()
                await fill_ege_tasks_13_14()
                await fill_ege_tasks_15_16_17()
                await fill_ege_tasks_18_19_20_21()
                await fill_ege_tasks_22_23_24()
                return
        else:
            task = await db.get_ege_task(num)
            if not task:
                await fill_ege_tasks_1_6()
                await fill_ege_tasks_7_9()
                await fill_ege_tasks_10_11_12()
                await fill_ege_tasks_13_14()
                await fill_ege_tasks_15_16_17()
                await fill_ege_tasks_18_19_20_21()
                await fill_ege_tasks_22_23_24()
                return
            ti = (task.get("task_image") or "").strip()
            si = (task.get("solution_image") or "").strip()
            ex = (task.get("example_solution") or "").strip()
            if not ti or (not si and not ex):
                await fill_ege_tasks_1_6()
                await fill_ege_tasks_7_9()
                await fill_ege_tasks_10_11_12()
                await fill_ege_tasks_13_14()
                await fill_ege_tasks_15_16_17()
                await fill_ege_tasks_18_19_20_21()
                await fill_ege_tasks_22_23_24()
                return
    return


async def main() -> None:
    await db.init_db()
    await fill_ege_tasks_1_6()
    await fill_ege_tasks_7_9()
    await fill_ege_tasks_10_11_12()
    await fill_ege_tasks_13_14()
    await fill_ege_tasks_15_16_17()
    await fill_ege_tasks_18_19_20_21()
    await fill_ege_tasks_22_23_24()
    for num in range(1, 25):
        print(f"Задание {num}: настроено")
    print("Готово. Задания 1–24 (8, 11, 14, 17, 19, 20, 21, 22, 24 — по два типа; 18 — несколько скринов решений).")


if __name__ == "__main__":
    asyncio.run(main())
