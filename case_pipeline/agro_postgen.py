# -*- coding: utf-8 -*-
"""case_pipeline.agro_postgen — редакторский генератор постов «Сад без хлопот».

НЕ копирует статью. Формирует короткий Telegram-friendly пост по §6 спецификации:
  🌿 Заголовок
  Вступление (проблема/ситуация)
  Что делать (список действий из источника)
  Важно (ограничение/предупреждение из источника)
  Когда делать (только если источник указывает срок)
  Источник: URL
  #теги

Жёсткие правила:
  - числа поста ⊆ числа источника (evidence gate);
  - НЕ придумывать дозировки, сроки, температуры, препараты;
  - НЕ использовать корпоративный CASE-формат;
  - НЕ оставлять HTML/навигацию/рекламу;
  - максимум ~1200 символов (Telegram caption комфорт).
"""
import re

MAX_POST_CHARS = 1200
MAX_LIST_ITEMS = 5
SKIP_RX = re.compile(
    r"^(фото|видео|читайте также|подписк|реклама|похожие материалы|"
    r"источник:|автор:|текст:|фото:|видео:|мы в |telegram|vk\.com|"
    r"одноклассники|facebook|instagram|яндекс\.дзен)", re.I)

# Маркеры практических блоков в источнике
ACTION_RX = re.compile(
    r"(как |что делать|советуем|рекомендуем|необходимо|нужно|"
    r"следует|важно |обратите внимание|шаг \d|этап \d|"
    r"первое|второе|третье|наконец|кроме того|также)", re.I)

WARNING_RX = re.compile(
    r"(важно!|внимание!|осторожно|не рекомендуется|запрещено|"
    r"избегайте|не стоит|ни в коем случае|помните|учтите|"
    r"противопоказан|риск|опасн)", re.I)

TIMING_RX = re.compile(
    r"(весной|летом|осенью|зимой|в марте|в апреле|в мае|в июне|"
    r"в июле|в августе|в сентябре|в октябре|в ноябре|в декабре|"
    r"до заморозков|после заморозков|ранней весной|поздней осенью|"
    r"каждые \d|раз в |еженедельно|ежемесячно|через \d)", re.I)


def _clean(text):
    """Убрать HTML-артефакты, лишние пробелы, навигационный мусор."""
    if not text:
        return ""
    t = re.sub(r"<[^>]+>", " ", text)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _extract_sentences(text, max_chars=300):
    """Первые содержательные предложения для вступления."""
    sents = re.split(r"(?<=[.!?…])\s+", _clean(text))
    out, total = [], 0
    for s in sents:
        s = s.strip()
        if len(s) < 40 or SKIP_RX.match(s):
            continue
        out.append(s)
        total += len(s)
        if total >= max_chars or len(out) >= 3:
            break
    return " ".join(out)


def _extract_actions(text, max_items=MAX_LIST_ITEMS):
    """Извлечь практические действия из текста (extractive)."""
    paragraphs = re.split(r"\n\s*\n", text or "")
    items = []
    for p in paragraphs:
        p = _clean(p)
        if len(p) < 30 or SKIP_RX.match(p):
            continue
        if ACTION_RX.search(p):
            # Берём первое предложение абзаца как действие
            first = re.split(r"(?<=[.!?…])\s+", p)[0].strip()
            if first and first not in items:
                items.append(first)
        if len(items) >= max_items:
            break
    return items


def _extract_warning(text):
    """Найти предупреждение/ограничение из источника."""
    for p in re.split(r"\n\s*\n", text or ""):
        p = _clean(p)
        if WARNING_RX.search(p):
            first = re.split(r"(?<=[.!?…])\s+", p)[0].strip()
            if first and len(first) > 20:
                return first
    return None


def _extract_timing(text):
    """Найти указание сроков/сезона из источника."""
    for p in re.split(r"\n\s*\n", text or ""):
        p = _clean(p)
        if TIMING_RX.search(p):
            first = re.split(r"(?<=[.!?…])\s+", p)[0].strip()
            if first and len(first) > 15:
                return first
    return None


def _normalize_title(title):
    """Очистить заголовок от сайта-мусора, оставить суть."""
    if not title:
        return ""
    t = re.sub(r"\s*[—|–\-]\s*(Ботаничка|Агроинвестор|Gismeteo|Своё Фермерство|"
               r"Новости|Статьи|Советы|Главная).*", "", title, flags=re.I).strip()
    t = re.sub(r"^\s*(Как|Что|Почему|Когда|Зачем)\s+", "", t).strip()
    # Если после очистки пусто — вернуть оригинал без хвоста
    if not t:
        t = title.split("—")[0].split("|")[0].split("–")[0].strip()
    return t[:120]


def build_agro_post(title, text, url, tags=None):
    """Сформировать финальный пост «Сад без хлопот».

    Возвращает строку (готовый caption/text). Все факты — extractive из text.
    """
    head = _normalize_title(title) or "Практический совет"
    emoji = "🌿"

    intro = _extract_sentences(text, max_chars=250)
    actions = _extract_actions(text)
    warning = _extract_warning(text)
    timing = _extract_timing(text)

    parts = [f"{emoji} {head}"]
    if intro:
        parts.append("")
        parts.append(intro)

    if actions:
        parts.append("")
        parts.append("Что делать:")
        for a in actions:
            parts.append(f"• {a}")

    if warning:
        parts.append("")
        parts.append(f"⚠️ Важно: {warning}")

    if timing:
        parts.append("")
        parts.append(f"📅 Когда: {timing}")

    parts.append("")
    parts.append(f"Источник: {url}")

    if tags:
        parts.append("")
        parts.append(" ".join(tags[:5]))

    post = "\n".join(parts)
    # Финальная обрезка по лимиту Telegram caption
    if len(post) > MAX_POST_CHARS:
        post = post[:MAX_POST_CHARS - 1].rsplit("\n", 1)[0] + "\n…"
        # Убедиться что источник и теги сохранены
        if f"Источник: {url}" not in post:
            post = post.rsplit("\n", 1)[0] + f"\n\nИсточник: {url}"
        if tags:
            tag_line = " ".join(tags[:5])
            if tag_line not in post:
                post = post + f"\n{tag_line}"

    return post
