"""
Помощь с домашкой: Yandex GPT API + Yandex Vision OCR для фото.
Нужны YANDEX_API_KEY и YANDEX_FOLDER_ID (каталог в Yandex Cloud).
"""
import base64
import logging

logger = logging.getLogger(__name__)

YANDEX_COMPLETION_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
YANDEX_VISION_URL = "https://vision.api.cloud.yandex.net/vision/v1/batchAnalyze"

# Специальное значение, когда пользователь отправил только фото и OCR не смог распознать текст
OCR_FAILED = "__OCR_FAILED__"

SYSTEM_PROMPT = (
    "Ты помощник по учёбе для школьников и студентов. "
    "Отвечай на вопросы по домашним заданиям понятно и по-русски. "
    "Объясняй шаг за шагом, не давай только ответ — показывай ход решения. "
    "Числа с запятой (результаты вычислений) пиши в обычном виде и округляй до двух знаков после запятой, "
    "если явно не просят другое (например: 3.91, 0.25, 1.33). "
    "Формулы и математику пиши так, чтобы они читались в обычном чате без LaTeX: "
    "не используй \\( \\), \\[ \\], \\frac{}, ^{} и т.п. Пиши степени как ² ³ или «в квадрате», "
    "дроби как a/b или (числитель)/(знаменатель), производные как f'(x), корень как √. "
    "Логарифмы: «log₂ 15» или текстом. "
    "Главную формулу ответа оформляй отдельным блоком: с новой строки три обратных кавычки, слово formula, с новой строки — сама формула (одна или несколько строк, без LaTeX), затем закрой блок тремя обратными кавычками. Так она отобразится аккуратно отдельным блоком. "
    "Когда показываешь программный код (Python, JavaScript и т.д.), всегда оформляй его отдельным блоком: "
    "с новой строки напиши три обратных кавычек (```), затем слово языка (python, javascript, cpp и т.д.), "
    "с новой строки — сам код, затем с новой строки закрой блок тремя обратными кавычками. "
    "Не вставляй код одной строкой в середину предложения — только отдельным блоком. "
    "Если вопрос не по учёбе, вежливо предложи сформулировать учебный вопрос."
)


async def _ocr_image(image_bytes: bytes, api_key: str) -> str | None:
    """Извлекает текст с изображения через Yandex Vision OCR. Возвращает None при ошибке."""
    api_key = (api_key or "").strip()
    if not api_key:
        return None
    payload = {
        "analyze_specs": [{
            "content": base64.b64encode(image_bytes).decode("ascii"),
            "features": [{
                "type": "TEXT_DETECTION",
                "text_detection_config": {"language_codes": ["ru", "en"]},
            }],
        }],
    }
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(
                YANDEX_VISION_URL,
                json=payload,
                headers={"Authorization": f"Api-Key {api_key}", "Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    preview = (body[:500] + "...") if len(body) > 500 else body
                    logger.warning(
                        "Yandex Vision OCR: status=%s, body=%s. "
                        "Проверь API-ключ и роль ai.vision.user у сервисного аккаунта.",
                        resp.status,
                        preview,
                    )
                    return None
                data = await resp.json()
    except Exception as e:
        logger.warning("Yandex Vision OCR failed: %s", e)
        return None
    try:
        results = data.get("results", [])
        if not results:
            logger.warning("Yandex Vision: пустой results, ключи ответа: %s", list(data.keys()))
            return None
        first = results[0]
        inner_results = first.get("results")
        if not inner_results:
            logger.warning(
                "Yandex Vision: нет results[0].results, ключи results[0]: %s",
                list(first.keys()) if isinstance(first, dict) else type(first),
            )
            return None
        inner = inner_results[0]
        text_det = inner.get("textDetection") or {}
        pages = text_det.get("pages") or []
        lines = []
        for page in pages:
            for block in page.get("blocks") or []:
                for line in block.get("lines") or []:
                    words = [w.get("text", "") for w in (line.get("words") or [])]
                    if words:
                        lines.append(" ".join(words))
        out = "\n".join(lines).strip() if lines else None
        if out:
            logger.info("Yandex Vision OCR: распознано %s символов", len(out))
        else:
            logger.warning("Yandex Vision: текст не извлечён (pages=%s)", len(pages))
        return out
    except (KeyError, IndexError, TypeError) as e:
        logger.warning(
            "Yandex Vision: неожиданная структура ответа: %s. results[0].keys=%s",
            e,
            list(results[0].keys()) if results and isinstance(results[0], dict) else None,
        )
        return None


async def ask_homework(user_text: str, api_key: str, folder_id: str = "", image_bytes: bytes | None = None) -> str | None:
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
    # Если есть фото — сначала OCR, затем объединяем с текстом
    if image_bytes:
        ocr_text = await _ocr_image(image_bytes, api_key)
        if ocr_text:
            user_text = f"Текст с фото задания:\n{ocr_text}\n\n" + (user_text.strip() or "Помоги решить это задание.")
        elif user_text.strip():
            user_text = user_text.strip()
        else:
            # Только фото, OCR не вернул текст — репетитор увидит причину в логах
            return OCR_FAILED
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
