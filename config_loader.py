"""
Конфиг: из config.py (локально) или из переменных окружения (Railway, Docker и т.д.).
На Railway в Variables задай: BOT_TOKEN, TUTOR_USER_ID (и при необходимости остальное).
"""
import os

try:
    import config
except ModuleNotFoundError:
    import sys
    # Нет config.py — читаем из окружения (деплой на Railway и др.)
    _uid = os.environ.get("TUTOR_USER_ID", "0")
    _h = os.environ.get("SUMMARY_DAILY_HOUR", "")
    try:
        _tutor_id = int(_uid)
    except (ValueError, TypeError):
        _tutor_id = 0

    _token_raw = os.environ.get("BOT_TOKEN", "")
    if not _token_raw or not _token_raw.strip():
        print("DEBUG: BOT_TOKEN в окружении не задан. Переменные:", list(os.environ.keys()), file=sys.stderr)
    else:
        print("DEBUG: BOT_TOKEN задан (длина %d)" % len(_token_raw), file=sys.stderr)

    class config:  # noqa: A001
        BOT_TOKEN = (_token_raw or "").strip()
        TUTOR_USER_ID = _tutor_id
        BOT_TITLE = os.environ.get("BOT_TITLE") or None
        MATERIALS_CHANNEL_LINK = os.environ.get("MATERIALS_CHANNEL_LINK") or None
        CHANNEL_ID = os.environ.get("CHANNEL_ID") or None
        SUMMARY_DAILY_HOUR = int(_h) if _h and str(_h).strip().isdigit() else None
        YANDEX_API_KEY = os.environ.get("YANDEX_API_KEY") or None
        YANDEX_FOLDER_ID = os.environ.get("YANDEX_FOLDER_ID") or None
