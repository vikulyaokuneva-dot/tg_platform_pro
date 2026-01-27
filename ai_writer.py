import json
import logging
from typing import Any, Dict, List, Optional

from gigachat import GigaChat


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
    # Отдельным блоком, чтобы модель реже "плыла".
    return (
        "Формат JSON (пример):\n"
        "{\n"
        "  \"title\": \"...\",\n"
        "  \"summary\": \"...\",\n"
        "  \"hashtags\": [\"#tag1\", \"#tag2\"]\n"
        "}\n"
        "Правила: title 5–12 слов, summary до 900 символов, hashtags 5–10 штук."
    )


class AIWriter:
    def __init__(self, api_key: Optional[str], model_name: str = "GigaChat-2-Lite"):
        self.api_key = api_key
        self.model_name = model_name
        self.enabled = bool(api_key)
        if not self.enabled:
            logger.warning("GIGACHAT_API_KEY is missing. AI features disabled.")

    def generate_post(self, text: str, category: str = "DEFAULT") -> Dict[str, Any]:
        """Возвращает dict: {title, summary, hashtags[]}.

        Никогда не бросает исключения наружу: на ошибке вернёт fallback.
        """
        fallback = {
            "title": "Коротко о главном",
            "summary": (text or "").strip()[:900],
            "hashtags": [],
        }

        if not self.enabled:
            return fallback

        system_prompt = PROMPTS.get(category, PROMPTS["DEFAULT"])
        input_text = (text or "").strip()[:8000]

        prompt = (
            f"{system_prompt}\n\n"
            f"{_json_schema_hint()}\n\n"
            "Текст новости:\n"
            f"{input_text}"
        )

        try:
            with GigaChat(credentials=self.api_key, verify_ssl_certs=False, model=self.model_name) as giga:
                response = giga.chat(prompt)
                content = response.choices[0].message.content

            # Иногда модель оборачивает JSON в код-блок — вычищаем.
            content = content.strip()
            if content.startswith("```"):
                content = content.strip("`")
                # может остаться "json\n{...}".
                content = content.replace("json\n", "", 1).strip()

            data = json.loads(content)

            title = str(data.get("title", "")).strip() or fallback["title"]
            summary = str(data.get("summary", "")).strip() or fallback["summary"]
            hashtags = data.get("hashtags", [])
            if not isinstance(hashtags, list):
                hashtags = []

            # Нормализация хэштегов
            cleaned: List[str] = []
            for tag in hashtags:
                if not isinstance(tag, str):
                    continue
                t = tag.strip()
                if not t:
                    continue
                if not t.startswith("#"):
                    t = "#" + t
                # минимальная чистка пробелов
                t = t.replace(" ", "")
                if len(t) > 1:
                    cleaned.append(t)

            return {
                "title": title[:160],
                "summary": summary[:1200],
                "hashtags": cleaned[:12],
            }
        except Exception as e:
            logger.error(f"GigaChat error: {e}")
            return fallback
