# -*- coding: utf-8 -*-
"""Original-text generation for PETS, with a non-publishing mock mode."""
import re


# A useful PETS post can be compact.  The lower bound only excludes a title
# with one slogan; it must never force GigaChat to pad a practical answer.
PETS_READER_POST_MIN_CHARS = 200
PETS_READER_POST_MAX_CHARS = 2400


def _clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def reader_post_length(title, body):
    return len(_clean("%s\n%s" % (title or "", body or "")))


_TECHNICAL_TEXT_RE = re.compile(
    r"(?:^\s*[\[{]|\"(?:title|body|status)\"\s*:|\bjson\b|\bdoi\b|"
    r"open\s+government\s+licen[cs]e|licensed\s+under|\bcc[-\s]?by\b|\bogl\b)", re.I,
)
_PRACTICAL_CUE_RE = re.compile(
    r"(?:попробуйте|проверьте|обратите внимание|начните|выберите|подготовьте|"
    r"понаблюдайте|создайте|планируйте|провер|важно|полезно|исследован|наблюден|"
    r"данн(?:ые|ым)|факт|связ(?:ь|ано)|observed|study|research|try|watch|notice)", re.I,
)
_WORD_RE = re.compile(r"[a-zа-яё]{3,}", re.I)


def validate_editorial_post(title, body):
    """Quality gate for the reader-facing part of a PETS post.

    Attribution is deliberately rendered afterwards.  This keeps licence and
    source metadata out of the useful reader text without dropping it.
    """
    title = _clean(title).lstrip("#").strip()
    body = str(body or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    reader_text = title + "\n" + body
    if not 10 <= len(title) <= 140 or len(_WORD_RE.findall(title)) < 3:
        return False, "editorial_title_not_specific"
    if _TECHNICAL_TEXT_RE.search(reader_text):
        return False, "editorial_technical_text_in_reader_body"
    paragraphs = [item.strip() for item in re.split(r"\n\s*\n", body) if item.strip()]
    if not 2 <= len(paragraphs) <= 5 or any(len(_clean(item)) > 1200 for item in paragraphs):
        return False, "editorial_paragraph_structure"
    if not _PRACTICAL_CUE_RE.search(body):
        return False, "editorial_practical_value_missing"
    token_sets = []
    for paragraph in paragraphs:
        tokens = set(_WORD_RE.findall(paragraph.lower()))
        for previous in token_sets:
            if previous and len(tokens & previous) / max(len(tokens), len(previous)) >= .82:
                return False, "editorial_semantic_repeat"
        token_sets.append(tokens)
    if len(re.findall(r"[🐾🐶🐱✨💡✅]", body)) > 4:
        return False, "editorial_excessive_emoji"
    return True, ""


def factual_brief_prompt(brief):
    """Build the only permitted prompt for a source-traceable PETS draft."""
    facts = brief.get("facts") or ()
    def claim_of(item):
        return item.get("claim", "") if isinstance(item, dict) else getattr(item, "claim", "")
    evidence = "\n".join("- %s" % _clean(claim_of(item)) for item in facts)
    audience = {"cat": "кошек", "dog": "собак", "both": "кошек и собак"}.get(
        str(brief.get("species") or "").lower(), "домашних питомцев")
    source_reference = "DOI: %s\n" % brief["doi"] if brief.get("doi") else ""
    return (
        "Создай оригинальный русскоязычный Telegram-пост для владельцев %(audience)s. "
        "Не переводи и не копируй статью. Используй только перечисленные факты. "
        "Запрещены неподтверждённые цифры, причинные выводы, медицинские рекомендации, "
        "диагнозы, лечение и обещания результата. Обязательно явно укажи, что выводы "
        "относятся к конкретному исследованию и не являются универсальным правилом.\n\n"
        "Тема: %(topic)s\n%(source_reference)sИсточник: %(source_url)s\n"
        "Ограничения: %(limitations)s\n"
        "Разрешённые выводы: %(allowed)s\n"
        "Запрещённые выводы: %(forbidden)s\n"
        "Атрибуция: %(attribution)s\n\n"
        "Проверенные факты:\n%(facts)s\n\n"
        "Формат ответа: привлекающий, но точный заголовок; пустая строка; затем 2–4 коротких абзаца. Обычно 350–900 символов: не растягивай текст ради объёма. "
        "Дай владельцу конкретную пользу: действие, небольшой чек-лист, пример или понятный факт. Не повторяй одну мысль в разных абзацах. "
        "Можно использовать 0–2 уместных эмодзи и выделить одну важную мысль Markdown-форматированием. Вопрос в конце добавляй только если он естественно вовлекает читателя. "
        "Не выводи JSON, служебные инструкции, ссылки, DOI, лицензии, англоязычные формулы лицензий и сведения о фото: система добавит источники и атрибуцию отдельным блоком."
        % {"audience": audience, "topic": brief.get("topic", ""), "source_reference": source_reference,
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
            "Создай оригинальный русскоязычный Telegram-пост для владельцев питомцев по теме: %s. "
            "Используй только факты ниже; не копируй формулировки, не добавляй диагнозы, дозировки, "
            "лечение, числовые нормы или обещания.\n\n"
            "Верни: точный привлекательный заголовок, пустую строку и 2–4 коротких абзаца. Обычно 350–900 символов: не растягивай текст ради объёма. Дай конкретную пользу: "
            "действие, пример, чек-лист или интересный факт. Не повторяй смысл между абзацами. Допустимы 0–2 умеренных эмодзи, "
            "один Markdown-акцент и уместный вопрос в конце. Не пиши JSON, ссылки, DOI, лицензионные формулы, атрибуцию фото "
            "или служебные инструкции: они будут добавлены отдельно.\n\nФакты:\n%s"
            % (topic.title, evidence))
        try:
            raw_text = str(self.provider.complete([{"role": "user", "content": prompt}]) or "").strip()
        except Exception:
            return None
        title, separator, body = raw_text.partition("\n\n")
        title, body = _clean(title), body.strip()
        if not separator or not title or not body or not PETS_READER_POST_MIN_CHARS <= reader_post_length(title, body) <= PETS_READER_POST_MAX_CHARS:
            return None
        return {"title": title, "text": body, "mode": self.mode}

    def generate_factual_brief(self, brief):
        """One opt-in generation from a structured PETS factual brief."""
        if not self.enabled or not self.provider or not getattr(self.provider, "available", False):
            return None
        try:
            raw_text = str(self.provider.complete([{"role": "user", "content": factual_brief_prompt(brief)}]) or "")
        except Exception:
            return None
        text = raw_text.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not PETS_READER_POST_MIN_CHARS <= len(_clean(text)) <= PETS_READER_POST_MAX_CHARS:
            return None
        title, _, body = text.partition("\n")
        if not title.strip() or not body.strip():
            return None
        return {"title": title.strip()[:140], "text": "%s\n%s" % (title.strip(), body.strip()), "mode": self.mode}
