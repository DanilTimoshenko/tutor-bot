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
    "Объясняй шаг за шагом, не давай только ответ — показывай ход решения. "
    "Числа с запятой (результаты вычислений) пиши в обычном виде и округляй до двух знаков после запятой, "
    "если явно не просят другое (например: 3.91, 0.25, 1.33). "
    "Не используй формат кода или LaTeX для формул: пиши текстом «логарифм по основанию 2 от 15» "
    "или «log₂ 15», но не `log_2(15)` и не \\log_2 15. "
    "Если вопрос не по учёбе, вежливо предложи сформулировать учебный вопрос."
)


async def ask_homework(user_text: str, api_key: str, folder_id: str = "") -> str | None:
    """
    Отправляет вопрос в Yandex GPT, возвращает ответ или None при ошибке/отсутствии ключа.
    """
    api_key = (api_key or "").strip()
    folder_id = (folder_id or "").strip()
    if not api_key or not folder_id:
        logger.warning(
            "Yandex GPT: запрос пропущен — не заданы YANDEX_API_KEY или YANDEX_FOLDER_ID в Variables."
        )
        return None
    if len(user_text.strip()) < 2:
        return None
    model_uri = f"gpt://{folder_id}/yandexgpt/latest"
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
                    preview = text[:1000] + ("..." if len(text) > 1000 else "")
                    logger.warning(
                        "Yandex GPT API error: status=%s, body=%s. "
                        "Проверь YANDEX_API_KEY, YANDEX_FOLDER_ID, квоты и доступ к YandexGPT в каталоге.",
                        resp.status,
                        preview,
                    )
                    return None
                data = await resp.json()
    except Exception as e:
        logger.exception("Yandex GPT request failed (сеть/таймаут/разбор ответа): %s", e)
        return None
    try:
        result = data.get("result", {})
        alternatives = result.get("alternatives", [])
        if alternatives and "message" in alternatives[0]:
            return alternatives[0]["message"].get("text", "").strip()
        return None
    except (KeyError, IndexError, TypeError) as e:
        logger.warning(
            "Yandex GPT: неожиданная структура ответа (result/alternatives/text). "
            "Ответ: %s. Ошибка: %s",
            data,
            e,
        )
        return None
