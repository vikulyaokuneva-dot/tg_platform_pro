import re


def clean_text(text: str) -> str:
    """
    Очищает текст от лишних пробелов и мусорных хвостов
    """
    if not text:
        return ""

    text = re.sub(r"\s+", " ", text)
    text = re.sub(
        r"(Подписывайтесь|Читайте также|Источник|Реклама).*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    return text.strip()


def shorten(text: str, limit: int = 1200) -> str:
    """
    Укорачивает текст до лимита, не обрывая предложение
    """
    if not text or len(text) <= limit:
        return text

    cut = text[:limit]
    pos = cut.rfind(".")
    if pos > 0:
        return cut[: pos + 1]

    return cut
