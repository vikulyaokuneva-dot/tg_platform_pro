# -*- coding: utf-8 -*-
"""Original-text generation for PETS, with a non-publishing mock mode."""
import re


def _clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


class MockPetsGenerator:
    """Offline fixture generator. Its output is always labelled mock/review."""
    mode = "mock"

    def generate(self, topic, facts):
        claims = [_clean(fact.claim) for fact in facts if _clean(fact.claim)]
        if not claims:
            return None
        source_lines = "\n".join("- " + fact.source_url for fact in facts)
        body = (
            "Это тестовый макет: перед выпуском его обязательно заменит отдельный реальный ответ редактора. "
            "В основу заложен проверяемый факт: %s\n\n"
            "Практический ориентир — наблюдать за питомцем спокойно, не назначать лечение самостоятельно "
            "и обращаться к ветеринарному специалисту при стойких тревожных признаках. "
            "Текст не является медицинской инструкцией и создан только для проверки конвейера.\n\n"
            "Источники фактов:\n%s" % (claims[0], source_lines))
        return {"title": topic.title, "text": body, "mode": self.mode}


class GigaChatPetsGenerator:
    """Opt-in wrapper. It never becomes available unless both gates are enabled."""
    mode = "gigachat"

    def __init__(self, provider, enabled=False):
        self.provider, self.enabled = provider, enabled

    def generate(self, topic, facts):
        if not self.enabled or not self.provider or not getattr(self.provider, "available", False):
            return None
        evidence = "\n".join("- %s (%s)" % (fact.claim, fact.source_url) for fact in facts)
        prompt = (
            "Создай оригинальный русскоязычный Telegram-пост 700–1200 символов на тему: %s. "
            "Используй только факты ниже; не копируй формулировки, не добавляй диагнозы, дозировки, "
            "лечение, числовые нормы или обещания. В конце добавь ссылки на источники.\nФакты:\n%s"
            % (topic.title, evidence))
        try:
            text = _clean(self.provider.complete([{"role": "user", "content": prompt}]))
        except Exception:
            return None
        if not 700 <= len(text) <= 1200:
            return None
        return {"title": topic.title, "text": text, "mode": self.mode}
