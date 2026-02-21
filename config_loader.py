"""
Конфиг: из config.py (локально) или из переменных окружения (Railway, Docker и т.д.).
На Railway в Variables задай: BOT_TOKEN, TUTOR_USER_ID (и при необходимости остальное).
"""
import logging
import os

logger = logging.getLogger(__name__)

try:
    import config
except ModuleNotFoundError:
    import sys
    # Нет config.py — читаем из окружения (деплой на Railway и др.)
    _uid = os.environ.get("TUTOR_USER_ID", "0")
    _admin_uid = os.environ.get("ADMIN_USER_ID", "").strip() or _uid
    _tutor_ids_raw = os.environ.get("TUTOR_USER_IDS", "").strip()
    _h = os.environ.get("SUMMARY_DAILY_HOUR", "")
    try:
        _tutor_id = int(_uid)
    except (ValueError, TypeError):
        _tutor_id = 0
    try:
        _admin_id = int(_admin_uid)
    except (ValueError, TypeError):
        _admin_id = _tutor_id
    _tutor_ids = set()
    if _tutor_ids_raw:
        for part in _tutor_ids_raw.replace(",", " ").split():
            try:
                _tutor_ids.add(int(part.strip()))
            except (ValueError, TypeError):
                pass
    if not _tutor_ids:
        _tutor_ids = {_tutor_id}
    if _admin_id not in _tutor_ids:
        _tutor_ids.add(_admin_id)

    _token_raw = os.environ.get("BOT_TOKEN", "")
    if not _token_raw or not _token_raw.strip():
        logger.debug("BOT_TOKEN в окружении не задан. Переменные: %s", list(os.environ.keys()))
    else:
        logger.debug("BOT_TOKEN задан (длина %d)", len(_token_raw))

    _yandex_key = os.environ.get("YANDEX_API_KEY") or None
    _yandex_folder = os.environ.get("YANDEX_FOLDER_ID") or None
    _yandex_ok = bool(_yandex_key and _yandex_key.strip() and _yandex_folder and _yandex_folder.strip())
    logger.debug(
        "YANDEX_API_KEY=%s, YANDEX_FOLDER_ID=%s (Помощь с домашкой: %s)",
        "задан" if (_yandex_key and _yandex_key.strip()) else "НЕ ЗАДАН",
        "задан" if (_yandex_folder and _yandex_folder.strip()) else "НЕ ЗАДАН",
        "да" if _yandex_ok else "нет",
    )
    if not _yandex_ok and any(k for k in os.environ if "YANDEX" in k.upper()):
        logger.debug("Переменные с YANDEX в окружении: %s", [k for k in os.environ if "YANDEX" in k.upper()])

    class config:  # noqa: A001
        BOT_TOKEN = (_token_raw or "").strip()
        TUTOR_USER_ID = _tutor_id
        ADMIN_USER_ID = _admin_id
        TUTOR_USER_IDS = _tutor_ids
        BOT_TITLE = os.environ.get("BOT_TITLE") or None
        MATERIALS_CHANNEL_LINK = os.environ.get("MATERIALS_CHANNEL_LINK") or None
        CHANNEL_ID = os.environ.get("CHANNEL_ID") or None
        SUMMARY_DAILY_HOUR = int(_h) if _h and str(_h).strip().isdigit() else None
        LESSON_LINK = (os.environ.get("LESSON_LINK") or "").strip() or None
        EGE_AUTHOR_TG = (os.environ.get("EGE_AUTHOR_TG") or "").strip() or None
        TUTOR_DISPLAY_NAME = (os.environ.get("TUTOR_DISPLAY_NAME") or "").strip() or None
        TIMEZONE = (os.environ.get("TIMEZONE") or "").strip() or None
        YANDEX_API_KEY = _yandex_key
        YANDEX_FOLDER_ID = _yandex_folder


def now_tz():
    """Текущее время в настроенном часовом поясе (или локальное, если TIMEZONE не задан)."""
    from datetime import datetime
    tz = (getattr(config, "TIMEZONE", None) or "").strip() or None
    if tz:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(tz))
    return datetime.now()


def localize_naive(dt):
    """Делает naive datetime осознанным в TIMEZONE (если задан)."""
    if not dt or dt.tzinfo:
        return dt
    tz = (getattr(config, "TIMEZONE", None) or "").strip() or None
    if tz:
        from zoneinfo import ZoneInfo
        return dt.replace(tzinfo=ZoneInfo(tz))
    return dt
