#!/usr/bin/env python3
"""
Проверка доступа к Yandex GPT API без бота.
Запуск:
  python3 test_yandex_gpt.py "API_KEY" "FOLDER_ID"
  или задай в config.py / переменных окружения.
"""
import os
import sys

api_key = ""
folder_id = ""
# Прямая передача: python3 test_yandex_gpt.py "ключ" "b1g..."
if len(sys.argv) >= 3:
    api_key = (sys.argv[1] or "").strip()
    folder_id = (sys.argv[2] or "").strip()
else:
    # Читаем config.py из папки скрипта
    _script_dir = os.path.dirname(os.path.abspath(__file__))
    _config_path = os.path.join(_script_dir, "config.py")
    if os.path.isfile(_config_path):
        import re
        with open(_config_path, "r", encoding="utf-8-sig") as f:
            text = f.read()
        m = re.search(r'YANDEX_API_KEY\s*=\s*["\']([^"\']*?)["\']', text, re.IGNORECASE)
        if m:
            api_key = m.group(1).strip()
        m = re.search(r'YANDEX_FOLDER_ID\s*=\s*["\']([^"\']*?)["\']', text, re.IGNORECASE)
        if m:
            folder_id = m.group(1).strip()
        if not api_key or not folder_id:
            for line in text.splitlines():
                line = line.strip()
                if line.startswith("YANDEX_API_KEY") and "=" in line:
                    part = line.split("=", 1)[1].strip().strip("\"'").split("#")[0].strip().strip("\"'")
                    if part:
                        api_key = part
                elif line.startswith("YANDEX_FOLDER_ID") and "=" in line:
                    part = line.split("=", 1)[1].strip().strip("\"'").split("#")[0].strip().strip("\"'")
                    if part:
                        folder_id = part
    if not api_key or not folder_id:
        api_key = (os.environ.get("YANDEX_API_KEY") or "").strip()
        folder_id = (os.environ.get("YANDEX_FOLDER_ID") or "").strip()

if not api_key or not folder_id:
    print("Использование: python3 test_yandex_gpt.py \"API_KEY\" \"FOLDER_ID\"")
    print("Или задай YANDEX_API_KEY и YANDEX_FOLDER_ID в config.py или в переменных окружения.")
    sys.exit(1)

url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
model_uri = f"gpt://{folder_id}/yandexgpt/latest"
payload = {
    "modelUri": model_uri,
    "completionOptions": {"stream": False, "temperature": 0.6, "maxTokens": "500"},
    "messages": [
        {"role": "system", "text": "Ты помощник. Отвечай кратко по-русски."},
        {"role": "user", "text": "Сколько будет 2+2? Ответь одним числом."},
    ],
}
headers = {
    "Authorization": f"Api-Key {api_key}",
    "Content-Type": "application/json",
}

print("Запрос к Yandex GPT API...")
print("  URL:", url)
print("  modelUri:", model_uri)
print("  (ключ: задан, длина %d)" % len(api_key))
print()

try:
    import urllib.request
    import json
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": "Api-Key %s" % api_key,
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.load(resp)
        text = data.get("result", {}).get("alternatives", [{}])[0].get("message", {}).get("text", "")
        print("OK, статус:", resp.status)
        print("Ответ модели:", text[:500] if text else "(пусто)")
except urllib.error.HTTPError as e:
    body = e.read().decode("utf-8", errors="replace")
    print("Ошибка HTTP:", e.code)
    print("Тело ответа:", body[:1500])
except Exception as e:
    print("Ошибка:", e)
