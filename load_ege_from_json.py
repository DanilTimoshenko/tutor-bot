#!/usr/bin/env python3
"""
Загрузка заданий ЕГЭ (1–27) в БД из JSON-файла.
Данные можно взять с https://code-enjoy.ru/courses/kurs_ege_po_informatike/
и оформить в JSON вручную или дописать скрипт парсинга сайта.

Запуск:
  python load_ege_from_json.py [путь/к/ege_tasks.json]
Если путь не указан, используется ege_tasks.json в папке проекта (или ege_tasks_example.json).
"""
import asyncio
import json
import os
import sys

# путь к проекту
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import database as db


def get_json_path() -> str:
    if len(sys.argv) > 1:
        return sys.argv[1]
    for name in ("ege_tasks.json", "ege_tasks_example.json"):
        path = os.path.join(SCRIPT_DIR, name)
        if os.path.isfile(path):
            return path
    return os.path.join(SCRIPT_DIR, "ege_tasks_example.json")


async def main() -> None:
    path = get_json_path()
    if not os.path.isfile(path):
        print(f"Файл не найден: {path}", file=sys.stderr)
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        print("Ожидается JSON-массив объектов с полями task_number, title, explanation, example_solution, source_url, solution_image", file=sys.stderr)
        sys.exit(1)
    await db.init_db()
    for item in data:
        num = item.get("task_number")
        if num is None or not (1 <= int(num) <= 27):
            print(f"Пропуск элемента с task_number={num}", file=sys.stderr)
            continue
        await db.set_ege_task(
            task_number=int(num),
            title=item.get("title") or "",
            example_solution=item.get("example_solution") or "",
            explanation=item.get("explanation") or "",
            source_url=item.get("source_url") or "",
            solution_image=item.get("solution_image") or "",
            task_image=item.get("task_image") or "",
        )
        print(f"Задание {num} загружено.")
    print("Готово.")


if __name__ == "__main__":
    asyncio.run(main())
