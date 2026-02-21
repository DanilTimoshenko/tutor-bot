"""
Добавить или обновить задание ЕГЭ Математика (1–19).
Запуск:
  python set_ege_math_task.py <номер 1-19> --task "Текст задания" --solution "Текст решения"
  python set_ege_math_task.py 5 --task-file task_5.txt --solution-file solution_5.txt
"""
import argparse
import asyncio
import sys

import database as db


async def main() -> None:
    parser = argparse.ArgumentParser(description="Добавить задание ЕГЭ Математика (1–19)")
    parser.add_argument("number", type=int, help="Номер задания (1–19)")
    parser.add_argument("--task", type=str, default="", help="Текст задания")
    parser.add_argument("--solution", type=str, default="", help="Текст решения")
    parser.add_argument("--task-file", type=str, help="Файл с текстом задания")
    parser.add_argument("--solution-file", type=str, help="Файл с текстом решения")
    args = parser.parse_args()

    if not (1 <= args.number <= 19):
        print("Номер задания должен быть от 1 до 19.", file=sys.stderr)
        sys.exit(1)

    task_text = args.task.strip()
    solution_text = args.solution.strip()
    if args.task_file:
        with open(args.task_file, "r", encoding="utf-8") as f:
            task_text = f.read().strip()
    if args.solution_file:
        with open(args.solution_file, "r", encoding="utf-8") as f:
            solution_text = f.read().strip()

    await db.set_ege_math_task(args.number, task_text=task_text, solution_text=solution_text)
    print(f"Задание {args.number} сохранено. task_text: {len(task_text)} символов, solution_text: {len(solution_text)} символов.")


if __name__ == "__main__":
    asyncio.run(main())
