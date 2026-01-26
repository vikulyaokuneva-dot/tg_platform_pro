import logging
from gigachat import GigaChat

# Промпты остались те же, они хорошие
PROMPTS = {
    "DEFAULT": (
        "Ты — опытный редактор Telegram-канала. Твоя задача — прочитать новость и пересказать её "
        "для русской аудитории. \n"
        "Требования:\n"
        "1. Заголовок должен быть цепляющим (кликбейт в меру), используй 1 эмодзи.\n"
        "2. Основной текст: 2-3 коротких абзаца или буллита. Только суть.\n"
        "3. Стиль: информативный, деловой, но не скучный.\n"
        "4. В конце сделай вывод или задай вопрос аудитории.\n"
        "5. Итоговый текст должен быть на русском языке."
    ),
    "IT_HUMOR": (
        "Ты — стендап-комик и программист. Прочитай этот текст (или шутку) и перескажи её для IT-канала. "
        "Сделай это максимально смешно, используй сленг (деплой, баги, фича, костыли). "
        "Если это просто новость — обстеби её."
    ),
    "CRYPTO_NEWS": (
        "Ты — крипто-аналитик. Перескажи новость кратко. Выдели главное для инвестора: "
        "как это повлияет на рынок? Бычий или медвежий сигнал? Стиль: сдержанный, профессиональный."
    ),
    "STARTUPS_VC": (
        "Ты — венчурный инвестор. Расскажи про этот стартап или новость. "
        "В чем инновация? Где деньги? Стоит ли обратить внимание? Пиши вдохновляюще."
    )
}

class AIWriter:
    def __init__(self, api_key):
        self.api_key = api_key
        self.enabled = bool(api_key)
        # Указываем модель явно
        self.model_name = "GigaChat-2-Lite" 
        
        if not self.enabled:
            logging.warning("GigaChat API Key is missing. AI features disabled.")

    async def summarize(self, text, category="DEFAULT"):
        """
        Отправляет текст в GigaChat и возвращает обработанный пост.
        """
        if not self.enabled:
            return text[:800] + "..."

        try:
            system_prompt = PROMPTS.get(category, PROMPTS["DEFAULT"])
            input_text = text[:8000] # GigaChat-2 позволяет контекст побольше

            # ВАЖНО: Передаем model=self.model_name
            with GigaChat(credentials=self.api_key, verify_ssl_certs=False, model=self.model_name) as giga:
                response = giga.chat(f"{system_prompt}\n\nТекст новости:\n{input_text}")
                return response.choices[0].message.content

        except Exception as e:
            logging.error(f"GigaChat Error: {e}")
            return text[:800] + "..."
