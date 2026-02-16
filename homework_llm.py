"""
Помощь с домашкой: Yandex GPT API.
Нужны YANDEX_API_KEY и YANDEX_FOLDER_ID (каталог в Yandex Cloud).
"""
import logging

logger = logging.getLogger(__name__)

YANDEX_COMPLETION_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"

SYSTEM_PROMPT = (
    "Ты помощник по учёбе для школьников и студентов. "
    "Отвечай на вопросы по домашним заданиям понятно и по-русски. "
    "Объясняй шаг за шагом, не давай только ответ — покажи ход решения. "
    "Если вопрос не по учёбе, вежливо предложи сформулировать учебный вопрос."
)


async def ask_homework(user_text: str, api_key: str, folder_id: str = "") -> str | None:
    """
    Отправляет вопрос в Yandex GPT, возвращает ответ или None при ошибке/отсутствии ключа.
    """
    api_key = (api_key or "").strip()
    folder_id = (folder_id or "").strip()
    if not api_key or not folder_id or len(user_text.strip()) < 2:
        return None
    model_uri = f"gpt://{folder_id}/yandexgpt-lite/latest"
    payload = {
        "modelUri": model_uri,
        "completionOptions": {
            "stream": False,
            "temperature": 0.6,
            "maxTokens": "1500",
        },
        "messages": [
            {"role": "system", "text": SYSTEM_PROMPT},
            {"role": "user", "text": user_text.strip()},
        ],
    }
    headers = {
        "Authorization": f"Api-Key {api_key}",
        "Content-Type": "application/json",
    }
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(
                YANDEX_COMPLETION_URL, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    logger.warning("Yandex GPT API error %s: %s", resp.status, text)
                    return None
                data = await resp.json()
    except Exception as e:
        logger.exception("Yandex GPT request failed: %s", e)
        return None
    try:
        result = data.get("result", {})
        alternatives = result.get("alternatives", [])
        if alternatives and "message" in alternatives[0]:
            return alternatives[0]["message"].get("text", "").strip()
        return None
    except (KeyError, IndexError, TypeError):
        logger.warning("Unexpected Yandex GPT response: %s", data)
        return None
