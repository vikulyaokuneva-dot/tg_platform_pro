import json
import logging
import os
from typing import Any, Dict, List, Optional

from gigachat import GigaChat
from gigachat.exceptions import NotFoundError

logger = logging.getLogger(__name__)

PROMPTS = {
    "DEFAULT": (
        "Ты — опытный редактор Telegram-канала. Твоя задача — прочитать новость и подготовить пост.\n"
        "Пиши для русской аудитории. Если исходный текст на английском — переведи на русский перед обработкой.\n"
        "Тон: информативный, деловой, без воды.\n"
        "Сделай заголовок цепляющим (1 уместный эмодзи).\n"
        "Саммари: 2–4 коротких абзаца или буллита.\n"
        "В конце — короткий вывод или вопрос аудитории.\n"
        "Верни результат строго в JSON, без Markdown, без пояснений."
    ),
    "IT_HUMOR": (
        "Ты — стендап-комик и программист. Подготовь пост для IT-юмор канала.\n"
        "Если текст на английском — переведи на русский.\n"
        "Можно сленг (деплой, баги, фича, костыли), но без токсичности.\n"
        "Верни результат строго в JSON, без Markdown, без пояснений."
    ),
    "CRYPTO_NEWS": (
        "Ты — крипто-аналитик. Кратко перескажи новость и подчеркни влияние на рынок.\n"
        "Если текст на английском — переведи на русский.\n"
        "Тон: сдержанный, профессиональный.\n"
        "Верни результат строго в JSON, без Markdown, без пояснений."
    ),
    "STARTUPS_VC": (
        "Ты — венчурный инвестор. Подготовь пост про стартап/новость.\n"
        "Если текст на английском — переведи на русский.\n"
        "Тон: деловой, вдохновляющий, но конкретный.\n"
        "Верни результат строго в JSON, без Markdown, без пояснений."
    ),
}


def _json_schema_hint() -> str:
    return (
        "Формат JSON (пример):\n"
        "{\n"
        "  \"title\": \"...\",\n"
        "  \"summary\": \"...\",\n"
        "  \"hashtags\": [\"#tag1\", \"#tag2\"]\n"
        "}\n"
        "Правила: title 5–12 слов, summary до 900 символов, hashtags 5–10 штук."
    )


def _strip_code_fences(s: str) -> str:
    """Убирает обёртки ``` и ```json вокруг JSON."""
    s = (s or "").strip()
    if not s.startswith("```"):
        return s

    # Важно: strip("`") удаляет все backticks по краям (и много), это ок для нашей задачи
    s = s.strip("`").strip()

    if s.lower().startswith("json\n"):
        s = s.split("\n", 1)[1].strip()

    return s


def _safe_json_loads(raw: str) -> Dict[str, Any]:
    """
    Более устойчивый парсинг JSON:
    - убираем ```json ... ```
    - если модель добавила текст вокруг JSON, вырезаем от первой '{' до последней '}'
    """
    raw = _strip_code_fences(raw)

    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        raw = raw[start : end + 1]

    return json.loads(raw)


class AIWriter:
    def __init__(self, api_key: Optional[str], model_name: Optional[str] = None):
        self.api_key = api_key

        # У тебя работает Lite v2 как "GigaChat-2"
        self.model_name = model_name or os.getenv("GIGACHAT_MODEL") or "GigaChat-2"

        self.enabled = bool(api_key)
        if not self.enabled:
            logger.warning("GIGACHAT_API_KEY is missing. AI features disabled.")

        # Таймаут на запрос к модели (сек). Можно переопределить через env
        self.timeout_sec = int(os.getenv("GIGACHAT_TIMEOUT_SEC", "30"))

    def generate_post(self, text: str, category: str = "DEFAULT") -> Dict[str, Any]:
        fallback = {
            "title": "Коротко о главном",
            "summary": (text or "").strip()[:900],
            "hashtags": [],
        }

        if not self.enabled:
            return fallback

        system_prompt = PROMPTS.get(category, PROMPTS["DEFAULT"])

        # Уменьшаем вход, чтобы реже ловить таймауты
        limit = 3500 if category == "IT_HUMOR" else 6000
        input_text = (text or "").strip()[:limit]

        prompt = (
            f"{system_prompt}\n\n"
            f"{_json_schema_hint()}\n\n"
            "Текст новости:\n"
            f"{input_text}"
        )

        # Пытаемся максимум 2 раза:
        # 1) выбранная модель (например GigaChat-2)
        # 2) резервная "GigaChat" (обычно самая стабильная)
        candidates: List[str] = []
        if self.model_name:
            candidates.append(self.model_name)
        if "GigaChat" not in candidates:
            candidates.append("GigaChat")

        last_error: Optional[Exception] = None

        # Главное изменение: не делаем "with GigaChat(...)" на каждую попытку,
        # чтобы не дергать OAuth лишний раз. Создаем клиента один раз на попытку модели.
        giga_client: Optional[GigaChat] = None

        for candidate in candidates:
            try:
                # Закрываем предыдущий клиент (если был), и создаём новый под нужную модель
                if giga_client is not None:
                    try:
                        giga_client.close()
                    except Exception:
                        pass
                    giga_client = None

                giga_client = GigaChat(
                    credentials=self.api_key,
                    verify_ssl_certs=False,
                    model=candidate,
                    timeout=self.timeout_sec,
                )

                response = giga_client.chat(prompt)
                content = response.choices[0].message.content

                # Устойчивый парсинг JSON
                data = _safe_json_loads(content)

                title = str(data.get("title", "")).strip() or fallback["title"]
                summary = str(data.get("summary", "")).strip() or fallback["summary"]
                hashtags = data.get("hashtags", [])
                if not isinstance(hashtags, list):
                    hashtags = []

                cleaned: List[str] = []
                for tag in hashtags:
                    if not isinstance(tag, str):
                        continue
                    t = tag.strip()
                    if not t:
                        continue
                    if not t.startswith("#"):
                        t = "#" + t
                    t = t.replace(" ", "")
                    if len(t) > 1:
                        cleaned.append(t)

                # Важно: НЕ мутируем self.model_name здесь.
                logger.info(f"Using GigaChat model: {candidate}")

                return {
                    "title": title[:160],
                    "summary": summary[:1200],
                    "hashtags": cleaned[:12],
                }

            except NotFoundError as e:
                logger.warning(f"Model not found: {candidate}. Trying next... ({e})")
                last_error = e
                continue
            except Exception as e:
                # Важно: при JSON ошибке полезно видеть начало ответа (но без риска залить весь текст в лог)
                msg = str(e)
                if "Expecting value" in msg or "JSON" in msg:
                    try:
                        preview = (content or "")[:800]
                        logger.warning(
                            f"GigaChat returned non-JSON for model {candidate}. "
                            f"Error: {e}. Preview: {preview!r}"
                        )
                    except Exception:
                        logger.warning(f"GigaChat attempt failed with model {candidate}: {e}")
                else:
                    logger.warning(f"GigaChat attempt failed with model {candidate}: {e}")

                last_error = e
                continue
            finally:
                # Закрываем клиент аккуратно
                if giga_client is not None:
                    try:
                        giga_client.close()
                    except Exception:
                        pass
                    giga_client = None

        logger.error(f"GigaChat error: {last_error}")
        return fallback
