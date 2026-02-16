#!/usr/bin/env python3
"""
Извлечение заданий ЕГЭ (1–27) из PDF и загрузка в БД.
Использование:
  python load_ege_from_pdf.py "Первый__день_ЕГЭ__ (1).pdf"
  или
  python load_ege_from_pdf.py  # ищет .pdf в текущей папке
"""
import asyncio
import os
import re
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from pypdf import PdfReader

import database as db


def extract_text_from_pdf(path: str) -> str:
    reader = PdfReader(path)
    parts = []
    for page in reader.pages:
        try:
            t = page.extract_text()
            if t:
                parts.append(t)
        except Exception as e:
            print(f"Страница: {e}", file=sys.stderr)
    return "\n".join(parts)


def split_into_tasks(full_text: str) -> dict[int, str]:
    """Разбивает текст по заголовкам «1 Задача 1», «2 Задача 2», «Задача 8.1» и т.д. Объединяет подзадачи."""
    # Убираем водяной знак
    text = re.sub(r"shkolkovo\.online\s*", "", full_text)
    text = re.sub(r"%d[0-9a-f]+%\s*", "", text)
    # На страницах контента: "1 Задача 1\nНа рисунке..." или "Задача 8.1\n..."
    # Не совпадаем с оглавлением "1 Задача 1 4" (там после номера идёт страница) — требуем \n после номера
    pattern = re.compile(r"(?:^|\n)\s*(?:\d+\s+)?Задача\s*(\d+)(?:\.\d+)?\s*\n", re.IGNORECASE)
    matches = list(pattern.finditer(text))
    blocks_by_num: dict[int, list[str]] = {}
    for i, m in enumerate(matches):
        num = int(m.group(1))
        if not (1 <= num <= 27):
            continue
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end].strip()
        # отсекаем короткие фрагменты (остатки оглавления)
        if len(block) < 50:
            continue
        blocks_by_num.setdefault(num, []).append(block)
    return {num: "\n\n".join(blocks) for num, blocks in blocks_by_num.items()}


def split_explanation_and_example(block: str) -> tuple[str, str]:
    """Пытается разделить блок на «объяснение» и «пример решения» по ключевым словам."""
    block = block.strip()
    for sep in ("Решение:", "Пример решения:", "Пример:", "Решение\n", "Код:", "Программа:"):
        if sep in block:
            i = block.find(sep)
            explanation = block[:i].strip()
            example = block[i + len(sep):].strip()
            if explanation and example:
                return explanation, example
    # Всё в одно поле «объяснение»
    return block, ""


async def main() -> None:
    if len(sys.argv) > 1:
        pdf_path = os.path.abspath(sys.argv[1])
    else:
        candidates = [f for f in os.listdir(SCRIPT_DIR) if f.endswith(".pdf") and "егэ" in f.lower() or "ege" in f.lower()]
        if not candidates:
            candidates = [f for f in os.listdir(SCRIPT_DIR) if f.endswith(".pdf")]
        if not candidates:
            print("Укажите путь к PDF: python load_ege_from_pdf.py 'файл.pdf'", file=sys.stderr)
            sys.exit(1)
        pdf_path = os.path.join(SCRIPT_DIR, candidates[0])
    if not os.path.isfile(pdf_path):
        print(f"Файл не найден: {pdf_path}", file=sys.stderr)
        sys.exit(1)
    print(f"Читаю PDF: {pdf_path}")
    text = extract_text_from_pdf(pdf_path)
    if not text or len(text) < 100:
        print("Не удалось извлечь достаточно текста из PDF (возможно, скан).", file=sys.stderr)
        sys.exit(1)
    tasks = split_into_tasks(text)
    if not tasks:
        print("В тексте не найдены блоки «Задача 1», «Задача 2» и т.д. Проверьте PDF.", file=sys.stderr)
        sys.exit(1)
    print(f"Найдено заданий: {len(tasks)} — номера {sorted(tasks.keys())}")
    await db.init_db()
    source_url = "https://code-enjoy.ru/courses/kurs_ege_po_informatike/"
    for num in range(1, 28):
        block = tasks.get(num, "").strip()
        if not block:
            continue
        explanation, example = split_explanation_and_example(block)
        title = f"Задание {num}"
        if explanation:
            first_line = explanation.split("\n")[0].strip()[:80]
            if first_line and len(first_line) > 5:
                title = first_line
        await db.set_ege_task(
            task_number=num,
            title=title,
            example_solution=example,
            explanation=explanation,
            source_url=source_url,
        )
        print(f"  Задание {num} загружено.")
    print("Готово.")


if __name__ == "__main__":
    asyncio.run(main())
