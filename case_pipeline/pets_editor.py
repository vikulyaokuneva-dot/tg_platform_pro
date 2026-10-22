# -*- coding: utf-8 -*-
"""Conservative Russian editor for PETS using the already configured provider."""
import re


_NUMBER = re.compile(r"\b\d+(?:[.,]\d+)?\b")


def _russian_enough(value):
    letters = re.findall(r"[A-Za-zА-Яа-яЁё]", value or "")
    if not letters:
        return False
    return sum(ch.lower() in "абвгдеёжзийклмнопрстуфхцчшщъыьэюя" for ch in letters) / len(letters) >= .65


def _numbers_supported(result, source):
    return set(_NUMBER.findall(result or "")).issubset(set(_NUMBER.findall(source or "")))


def edit(title, text, source_url, provider):
    """Create an original Russian draft or return ``None`` on any uncertainty.

    The provider is the existing GigaChat abstraction. The prompt forbids
    diagnosis, doses, unsupported facts and copying; deterministic checks then
    reject an answer with a new numeric claim or insufficient Russian text.
    """
    if not provider or not getattr(provider, "available", False) or not callable(getattr(provider, "complete", None)):
        return None
    prompt = (
        "Подготовь оригинальный русскоязычный образовательный текст для владельца питомца. "
        "Не ставь диагноз, не назначай лечение, препараты или дозировки. Не добавляй факты, числа, "
        "породы или рекомендации, которых нет в исходнике. Не переводи предложения дословно. "
        "Верни строго две части: заголовок в первой строке, затем пустая строка и 2–4 коротких абзаца. "
        "Исходный заголовок: %s\nИсточник: %s\nИсходный материал:\n%s"
        % (title or "", source_url, (text or "")[:12000])
    )
    try:
        raw = provider.complete([{"role": "user", "content": prompt}])
    except Exception:
        return None
    value = str(raw or "").strip()
    parts = re.split(r"\n\s*\n", value, maxsplit=1)
    if len(parts) != 2:
        return None
    edited_title, edited_text = parts[0].strip(), parts[1].strip()
    if len(edited_title) < 8 or len(edited_text) < 260 or not _russian_enough(value):
        return None
    if not _numbers_supported(value, (title or "") + "\n" + (text or "")):
        return None
    return {"title": edited_title[:140], "text": edited_text[:5000]}
