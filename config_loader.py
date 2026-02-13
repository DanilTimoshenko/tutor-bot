"""
Конфиг: из config.py (локально) или из переменных окружения (Railway, Docker и т.д.).
На Railway в Variables задай: BOT_TOKEN, TUTOR_USER_ID (и при необходимости остальное).
"""
import os

try:
    import config
except ModuleNotFoundError:
    # Нет config.py — читаем из окружения (деплой на Railway и др.)
    _uid = os.environ.get("TUTOR_USER_ID", "0")
    _h = os.environ.get("SUMMARY_DAILY_HOUR", "")
    try:
        _tutor_id = int(_uid)
    except (ValueError, TypeError):
        _tutor_id = 0

    class config:  # noqa: A001
        BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
        TUTOR_USER_ID = _tutor_id
        BOT_TITLE = os.environ.get("BOT_TITLE") or None
        MATERIALS_CHANNEL_LINK = os.environ.get("MATERIALS_CHANNEL_LINK") or None
        CHANNEL_ID = os.environ.get("CHANNEL_ID") or None
        SUMMARY_DAILY_HOUR = int(_h) if _h and str(_h).strip().isdigit() else None
