# -*- coding: utf-8 -*-
"""Original-text generation for PETS, with a non-publishing mock mode."""
import re


def _clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def factual_brief_prompt(brief):
    """Build the only permitted prompt for a source-traceable PETS draft."""
    facts = brief.get("facts") or ()
    def claim_of(item):
        return item.get("claim", "") if isinstance(item, dict) else getattr(item, "claim", "")
    evidence = "\n".join("- %s" % _clean(claim_of(item)) for item in facts)
    audience = {"cat": "кошек", "dog": "собак", "both": "кошек и собак"}.get(
        str(brief.get("species") or "").lower(), "домашних питомцев")
    return (
        "Создай оригинальный русскоязычный Telegram-пост для владельцев %(audience)s. "
        "Не переводи и не копируй статью. Используй только перечисленные факты. "
        "Запрещены неподтверждённые цифры, причинные выводы, медицинские рекомендации, "
        "диагнозы, лечение и обещания результата. Обязательно явно укажи, что выводы "
        "относятся к конкретному исследованию и не являются универсальным правилом.\n\n"
        "Тема: %(topic)s\nDOI: %(doi)s\nИсточник: %(source_url)s\n"
        "Ограничения: %(limitations)s\n"
        "Разрешённые выводы: %(allowed)s\n"
        "Запрещённые выводы: %(forbidden)s\n"
        "Атрибуция: %(attribution)s\n\n"
        "Проверенные факты:\n%(facts)s\n\n"
        "Верни заголовок, пустую строку и 2–4 коротких абзаца. В конце добавь DOI и ссылку на источник."
        % {"audience": audience, "topic": brief.get("topic", ""), "doi": brief.get("doi", ""),
           "source_url": brief.get("source_url", ""),
           "limitations": "; ".join(brief.get("limitations") or ()),
           "allowed": "; ".join(brief.get("allowed_conclusions") or ()),
           "forbidden": "; ".join(brief.get("forbidden_conclusions") or ()),
           "attribution": brief.get("attribution_requirements", ""), "facts": evidence}
    )


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

    def generate_factual_brief(self, brief):
        """One opt-in generation from a structured PETS factual brief."""
        if not self.enabled or not self.provider or not getattr(self.provider, "available", False):
            return None
        try:
            text = _clean(self.provider.complete([{"role": "user", "content": factual_brief_prompt(brief)}]))
        except Exception:
            return None
        if not 700 <= len(text) <= 1600:
            return None
        title, _, body = text.partition("\n")
        if not title.strip() or not body.strip():
            return None
        return {"title": title.strip()[:140], "text": text, "mode": self.mode}
