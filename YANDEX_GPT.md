# Подключение Yandex GPT для «Помощь с домашкой»

1. Зайди в [Yandex Cloud](https://console.cloud.yandex.ru).
2. Создай каталог (или выбери существующий) — нужен **ID каталога** (Folder ID), вид `b1gxxxxxxxxxxxxxxxxxx`.
3. Включи сервис **YandexGPT** в каталоге: раздел «Искусственный интеллект» → YandexGPT (Foundation Models).
4. Создай **API-ключ** для доступа к API: IAM → Сервисные аккаунты → создать аккаунт → выдать роль `ai.languageModels.user` → Создать API-ключ. Скопируй ключ (показывается один раз).
5. В боте задай:
   - **YANDEX_API_KEY** — скопированный API-ключ.
   - **YANDEX_FOLDER_ID** — ID каталога из шага 2.

Локально в `config.py`:
```python
YANDEX_API_KEY = "AQVN..."
YANDEX_FOLDER_ID = "b1g..."
```

На Railway в Variables добавь переменные `YANDEX_API_KEY` и `YANDEX_FOLDER_ID`.

Подробнее: [документация Yandex Cloud — YandexGPT](https://cloud.yandex.ru/docs/yandexgpt/).
