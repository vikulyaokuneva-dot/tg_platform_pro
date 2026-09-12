# -*- coding: utf-8 -*-
"""case_pipeline.postformat — финальный вид поста для Telegram (только подача).

Хранящийся/генерируемый текст НЕ меняется: перед отправкой пост раскладывается
в целевой макет канала (жирный заголовок и поля через **, пустые строки между
блоками, списки через '*'), затем to_markdownv2() даёт валидный MarkdownV2
(спецсимволы экранированы, неразрешённые одиночные ** выводятся буквально).
Никакого HTML. Строку «Источник:» и хэштеги не трогаем.
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
            rendered.append(" ".join(lines))
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
    Непарные ** выводятся буквально; весь прочий текст экранируется."""
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
        segs.append("**%s**" % esc if bold else esc)
    return "".join(segs)


def unescape_markdownv2(text):
    """Только для тестов: снимает экранирование спецсимволов MarkdownV2."""
    return re.sub(r"\\([_*\[\]()~`>#+\-=|{}.!\\])", r"\1", text)
