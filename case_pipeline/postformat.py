# -*- coding: utf-8 -*-
"""case_pipeline.postformat — финальный вид поста для Telegram (только подача).

Хранящийся/генерируемый текст НЕ меняется: перед отправкой пост раскладывается
в целевой макет канала (жирный заголовок, слово «Вывод» и поля через **,
пустые строки между блоками, списки через '*'), затем to_markdownv2() даёт
валидный MarkdownV2: жирное — ОДИНАРНЫМИ звёздочками *текст* (в MarkdownV2
**текст** не рендерится жирным), спецсимволы экранированы, неразрешённые
одиночные ** выводятся буквально. Никакого HTML. Строку «Источник:» и
хэштеги не трогаем.
"""
import re

# спецсимволы MarkdownV2 (Telegram Bot API)
MDV2_SPECIALS = set("_*[]()~`>#+-=|{}.!\\")
_BOLDS = re.compile(r"^\s*\*\*|\*\*\s*$")
# ведущие decorative-символы строки поля (эмодзи/пиктограммы), пробелы сохраняем
_LEAD = re.compile(r"[^\w\s:*А-Яа-яЁё]+", re.UNICODE)

# норм. label -> (показываемое имя, режим)
LABELS = {
    "кто": ("Компания", "inline"),
    "компания": ("Компания", "inline"),
    "проблема": ("Проблема", "inline"),
    "что автоматизировали": ("Что автоматизировали", "inline"),
    "как это работало": ("Как это работало", "auto"),
    "технологии": ("Технологии", "inline"),
    "результат": ("Результат", "auto"),
    "цифры": ("Цифры", "auto"),
    "цифры из источника": ("Цифры", "auto"),
    "вывод для бизнеса": ("Что может применить бизнес", "para"),
    "что может применить бизнес": ("Что может применить бизнес", "para"),
    "cta": ("CTA", "para"),
}
_LABEL_ALT = "|".join(sorted((re.escape(k) for k in LABELS), key=len, reverse=True))
LABEL_LINE_RX = re.compile(
    r"^\s*(?:\*\*)?\s*([^\w\s:А-Яа-яЁё]*\s*)(%s)\s*(?:\*\*)?\s*:\s*(.*)$" % _LABEL_ALT,
    re.IGNORECASE | re.UNICODE)
BULLET_RX = re.compile(r"^\s*[-*•]\s+(.*)$")
TAGS_RX = re.compile(r"^\s*(?:#\S+\s*)+$")
SRC_RX = re.compile(r"^\s*(?:\*\*)?\s*Источник\s*(?:\*\*)?\s*:")
_EMOJI_CHARS = ("\u20d0-\u20f3\u2300-\u23ff\u2600-\u27bf\u2b00-\u2bff\ufe0f"
                "\U0001F000-\U0001FAFF")
_EMOJI_TAIL_RX = re.compile(r"\s*[%s]+\s*$" % _EMOJI_CHARS, re.UNICODE)
_EMOJI_LEAD_RX = re.compile(r"^[%s\s]+" % _EMOJI_CHARS, re.UNICODE)


def _norm_label(name):
    return _LEAD.sub("", name).strip(" :*").lower()


def _clean_headline(line):
    s = line.strip()
    s = _EMOJI_LEAD_RX.sub("", s)
    s = _BOLDS.sub("", s)
    s = _EMOJI_TAIL_RX.sub("", s)
    return s.strip()


def _join_inline(lines):
    return _BOLDS.sub("", " ".join(lines)).strip()


def _extract_tail(text):
    """Отделяем финальные строку тегов и строку 'Источник:' (не меняем их)."""
    lines = text.split("\n")
    tags = None
    src = None
    while lines and not lines[-1].strip():
        lines.pop()
    if lines and TAGS_RX.match(lines[-1]):
        tags = lines.pop().strip()
        while lines and not lines[-1].strip():
            lines.pop()
    if lines and SRC_RX.match(lines[-1]):
        src = lines.pop().strip()
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines).rstrip(), src, tags


def _paragraphs(text):
    blocks, cur = [], []
    for line in text.split("\n"):
        if line.strip():
            cur.append(line.rstrip())
        elif cur:
            blocks.append(cur)
            cur = []
    if cur:
        blocks.append(cur)
    return blocks


# пометка в начале второго сообщения длинного поста: читателю ясно, что это
# продолжение той же публикации под фото (не отдельный пост, не дубль)
CONTINUATION_HEADER = "Продолжение"


def _fit_sentence_prefix(s, fits):
    """Максимальный префикс s по ГРАНИЦЕ ПРЕДЛОЖЕНИЯ, для которого
    fits(prefix) истинно (внутренние переводы строк сохраняются)."""
    parts = re.split(r"(?<=[.!?…])(\s+)", s)
    cur = ""
    for i, part in enumerate(parts):
        cand = cur + part
        if i % 2 == 0 and not fits(cand):
            break
        cur = cand
    return cur.rstrip()


def split_for_photo(text, caption_limit=None):
    """Разложение поста на (подпись к фото, сообщение-ПРОДОЛЖЕНИЕ).

    Публикация вызывает её ТОЛЬКО если весь пост не поместился в лимит
    подписи (см. telegram.publish_post); тогда подпись должна быть
    МАКСИМАЛЬНО полной: в неё уходит заголовок и как можно больше тела —
    целыми абзацами, а если следующий абзац не влезает целиком — его
    префикс по границе предложения (подпись всегда заканчивается целым
    предложением). caption_limit считается по экранированному MarkdownV2
    тексту — как длину считает Telegram (Bot API: подпись ≤1024 симв.).
    Строка «Источник:» всегда в подписи, хэштегов в подписи нет.

    Продолжение (второе сообщение): остаток тела БЕЗ повторного заголовка
    и без того, что уже ушло в подписи — текст не дублируется и не
    теряется, продолжение начинается с целого предложения; первая строка —
    пометка CONTINUATION_HEADER («Продолжение»), чтобы читателю было ясно,
    что сообщение относится к фото сверху; «Источник:» + хэштеги
    (регрессия msg80/81: заголовок и вступление не должны повторяться
    во втором сообщении — читатель видит его прямо под фото).

    Вырожденный случай (нет тела или caption_limit не задан): пост целиком
    и в подписи, и в сообщении — дубль фиксируется логом publish_post."""
    body, src, tags = _extract_tail(text or "")
    blocks = [b.strip() for b in body.split("\n\n") if b.strip()]
    if len(blocks) < 2 or not caption_limit:   # тела нет — делить нечего
        return (text or "").strip(), (text or "").strip()
    head, rest = blocks[0], blocks[1:]
    if not rest:
        return (text or "").strip(), (text or "").strip()
    src_line = src or ""

    def cap_of(parts):
        return "\n\n".join(
            x for x in [head] + parts + ([src_line] if src_line else []) if x)

    def fits(parts):
        return len(to_markdownv2(cap_of(parts))) <= caption_limit

    chosen, pending = [], list(rest)
    partial = None                    # (префикс, остаток) разрезанного абзаца
    while pending:
        if fits(chosen + [pending[0]]):
            chosen.append(pending.pop(0))
            continue
        # абзац не влез целиком: втискиваем его префикс по границе
        # предложения (продолжение получает ровно остаток — без потерь)
        prefix = _fit_sentence_prefix(pending[0], lambda p: fits(chosen + [p]))
        if prefix:
            partial = (prefix, pending[0][len(prefix):].strip())
            pending.pop(0)       # разрезанный абзац целиком ушёл в подпись
        break
    cap = cap_of(chosen + ([partial[0]] if partial else []))
    msg_rest = ([partial[1]] if partial and partial[1] else []) + pending
    msg = "\n\n".join(
        x for x in [CONTINUATION_HEADER] + msg_rest
        + [y for y in (src, tags) if y] if x)
    return cap.strip(), msg.strip()


def _parse_blocks(text):
    """[ {label, mode, lines} ]; label=None — безымянный текстовый блок.

    Строки, идущие в исходном тексте сразу за строкой поля, продолжают это
    поле (тот же абзац)."""
    blocks = []

    def new(label, mode):
        blocks.append({"label": label, "mode": mode, "lines": []})
        return blocks[-1]

    for par in _paragraphs(text):
        current = None
        for line in par:
            s = line.strip()
            if not s:
                continue
            m = LABEL_LINE_RX.match(s)
            if m:
                shown, mode = LABELS[_norm_label(m.group(2))]
                current = new(shown, mode)
                rest = _BOLDS.sub("", m.group(3).strip()).strip()
                if rest:
                    current["lines"].append(rest)
            elif BULLET_RX.match(s) and blocks and blocks[-1]["mode"] == "auto":
                blocks[-1]["lines"].append(s)   # пункты к «Цифры/Результат»
                current = blocks[-1]
            elif s.startswith("💼"):
                current = new("CTA", "para")
                current["lines"].append(_EMOJI_LEAD_RX.sub("", s))
            elif current is not None:
                current["lines"].append(s)      # продолжение того же блока
            elif blocks and not blocks[-1]["lines"] and blocks[-1]["label"]:
                blocks[-1]["lines"].append(s)   # текст после label-строки поля
                current = blocks[-1]
            else:
                current = new(None, "para")
                current["lines"].append(s)
    return blocks


# «Вывод: ...» — слово жирным, сам текст вывода обычный (регрессия визуальной
# подачи агро-статей); уже отформатированный блок **Вывод**: не трогаем
_VYVOD_RX = re.compile(r"^(Вывод)\s*:\s*(\S.*)$", re.IGNORECASE | re.UNICODE)


def _bold_vyvod(block):
    m = _VYVOD_RX.match(block)
    return "**%s**: %s" % (m.group(1), m.group(2)) if m else block


def format_post(text):
    """Обычный/старый пост -> целевой макет с **маркерами** (без экранирования).

    Идемпотентен: повторный прогон по уже отформатированному тексту не меняет
    его (кроме нормализации пустых строк)."""
    if not text or not text.strip():
        return text or ""
    body, src, tags = _extract_tail(text)
    blocks = _parse_blocks(body)
    if not blocks:
        return text.strip()
    rendered = []

    # заголовок: первая строка первого безымянного блока
    b0 = blocks[0]
    head = None
    if b0["label"] is None and b0["lines"]:
        head = _clean_headline(b0["lines"][0])
        b0["lines"] = b0["lines"][1:]
        if not b0["lines"]:
            blocks.pop(0)
    if head:
        rendered.append("**%s**" % head)

    # короткая строка компании без подписи сразу после заголовка
    if len(blocks) >= 2 and blocks[0]["label"] is None and blocks[1]["label"] in (
            "Проблема", "Что автоматизировали"):
        l0 = [x for x in blocks[0]["lines"] if x.strip()]
        if len(l0) == 1 and len(l0[0]) <= 60 and ":" not in l0[0]:
            blocks[0] = {"label": "Компания", "mode": "inline", "lines": l0}

    for b in blocks:
        lines = [x.strip() for x in b["lines"] if x.strip()]
        if not lines:
            continue
        if b["label"] is None:
            rendered.append(_bold_vyvod(" ".join(lines)))
        elif b["mode"] == "inline":
            rendered.append("**%s:** %s" % (b["label"], _join_inline(lines)))
        elif b["mode"] == "auto":
            if len(lines) == 1 and not BULLET_RX.match(lines[0]):
                rendered.append("**%s:** %s" % (b["label"], _join_inline(lines)))
            else:
                items = ["* " + BULLET_RX.sub(r"\1", x).strip() for x in lines]
                rendered.append("**%s:**\n\n%s" % (b["label"], "\n".join(items)))
        else:  # para
            rendered.append("**%s:**\n\n%s" % (b["label"], _join_inline(lines)))

    if src:
        rendered.append(src)
    if tags:
        rendered.append(tags)
    return "\n\n".join(x for x in rendered if x)


def to_markdownv2(text):
    """plain-текст с парными **сегментами -> валидный MarkdownV2.
    Жирное оформление — ОДИНАРНЫМИ звёздочками *текст* (так его понимает
    Telegram: **текст** не рендерится жирным); непарные ** выводятся
    буквально; весь прочий текст экранируется."""
    parts = text.split("**")
    segs = []
    n = len(parts)
    for i, p in enumerate(parts):
        bold = (i % 2 == 1) and (n % 2 == 1 or i <= n - 3)
        if i % 2 == 1 and not bold:
            p = "**" + p  # непарный маркер — восстанавливаем как литерал
        if i % 2 == 1 and bold and p.startswith("\\"):
            p = " " + p   #closing ** после литерального \ — без двусмысленности
        esc = "".join("\\" + c if c in MDV2_SPECIALS else c for c in p)
        segs.append("*%s*" % esc if bold else esc)
    return "".join(segs)


def unescape_markdownv2(text):
    """Снимает маркеры жирного (*текст*) и экранирование спецсимволов
    MarkdownV2 (тесты + plain-fallback подписи/сообщения, когда API отвергает
    parse_mode): на выходе чистый текст без markdown-символов."""
    text = re.sub(r"(?<!\\)\*", "", text)
    return re.sub(r"\\([_*\[\]()~`>#+\-=|{}.!\\])", r"\1", text)
