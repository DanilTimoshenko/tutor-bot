"""Проверка, что основные модули импортируются без ошибок."""

import os

# Без config.py — config_loader создаёт config из env
os.environ.setdefault("BOT_TOKEN", "123456789:test_token_placeholder_for_ci")
os.environ.setdefault("TUTOR_USER_ID", "1")


def test_import_config_loader():
    from config_loader import config
    assert hasattr(config, "BOT_TOKEN")


def test_import_database():
    import database
    assert hasattr(database, "init_db")
    assert hasattr(database, "get_upcoming_lessons")
