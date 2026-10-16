# -*- coding: utf-8 -*-
"""case_pipeline.postformat — финальный вид поста для Telegram (только подача).

Хранящийся/генерируемый текст НЕ меняется: перед отправкой пост раскладывается
в целевой макет канала (жирный заголовок, слово «Вывод» и поля через **,
курсив-ремарки через _, пустые строки между блоками, списки через '*'),
затем to_markdownv2() даёт валидный MarkdownV2: жирное — ОДИНАРНЫМИ
звёздочками *текст* (в MarkdownV2 **текст** не рендерится жирным), курсив —
_текст_, спецсимволы экранированы, неразрешённые одиночные ** и _ выводятся
буквально. Никакого HTML. Строку «Источник:» и хэштеги не трогаем.
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


def _clean_headline(line, keep_emoji=False):
    s = line.strip()
    if not keep_emoji:                 # agro-стиль: ведущий эмодзи — часть
        s = _EMOJI_LEAD_RX.sub("", s)  # заголовка, он НЕ удаляется
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


def split_for_photo(text, caption_limit=None, message_limit=None):
    """Разложение поста на (подпись к фото, сообщение-ПРОДОЛЖЕНИЕ).

    Публикация вызывает её ТОЛЬКО если весь пост не поместился в лимит
    подписи (см. telegram.publish_post). Разрез — ТОЛЬКО по границам
    абзацев/смысловых блоков: абзац (список, пункт, инструкция), не
    помещающийся целиком, уходит в продолжение ЦЕЛИКОМ — предложение или
    пункт списка посередине не рвутся, подпись всегда заканчивается целым
    блоком. caption_limit считается по экранированному MarkdownV2 тексту —
    как длину считает Telegram (Bot API: подпись ≤1024 симв.).

    Источник («Источник:» + URL) указывается РОВНО ОДИН РАЗ — в конце
    последнего сообщения: в подписи длинного поста его нет, в продолжении
    он идёт после тела перед хэштегами (короткий пост publish_post шлёт
    одним сообщением — источник там в конце единой подписи).

    Продолжение (второе сообщение): остаток тела целиком БЕЗ повторного
    заголовка и без того, что уже ушло в подписи — текст не дублируется и
    не теряется; первая строка — пометка CONTINUATION_HEADER («Продолжение»),
    чтобы читателю было ясно, что сообщение относится к фото сверху
    (регрессии msg80/81: название канала, заголовок и вступление не должны
    повторяться во втором сообщении — читатель видит его прямо под фото).

    Возвращает (None, None), если корректное деление без потерь
    невозможно: в подпись не помещается НИ ОДИН абзац тела, либо
    продолжение вместе с пометкой, разметкой и источником не укладывается
    в message_limit (лимит текстового сообщения). Такой пост НЕ режется:
    publish_post честно отказывает ДО отправки — материал уходит на
    ручную проверку (review), а не публикуется обрезанным.

    Вырожденный случай (caption_limit не задан): пост целиком и в подписи,
    и в сообщении — дубль фиксируется логом publish_post."""
    body, src, tags = _extract_tail(text or "")
    blocks = [b.strip() for b in body.split("\n\n") if b.strip()]
    if not caption_limit:            # лимит не задан — делить нечего
        return (text or "").strip(), (text or "").strip()
    if len(blocks) < 2:              # тела нет: цельный блок не делится
        return None, None            # без разреза — честный отказ
    head, rest = blocks[0], blocks[1:]

    def cap_of(parts):
        # «Источник:» в подписи НЕТ (источник — один раз, в конце последнего
        # сообщения), поэтому весь бюджет подписи отдан телу статьи
        return "\n\n".join(x for x in [head] + parts if x)

    def fits(parts):
        return len(to_markdownv2(cap_of(parts))) <= caption_limit

    chosen, pending = [], list(rest)
    # наполняем подпись целыми абзацами; первый не влезший блок и все
    # последующие уходят в продолжение целиком (порядок текста сохраняется)
    while pending and fits(chosen + [pending[0]]):
        chosen.append(pending.pop(0))
    if not chosen:
        # ни один абзац тела не влез под заголовок — полноценного основного
        # сообщения не получается: делить без потерь нечем
        return None, None
    cap = cap_of(chosen)
    msg = "\n\n".join(
        x for x in [CONTINUATION_HEADER] + pending
        + [y for y in (src, tags) if y] if x)
    if message_limit and len(to_markdownv2(msg)) > message_limit:
        return None, None           # продолжение не влезает — не режем
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


# «Вывод: ...» в AGRO получает свой компактный визуальный акцент. Общий
# formatter сохраняет прежний нейтральный вид, поэтому AI Automation не
# затрагивается.
_VYVOD_RX = re.compile(r"^(Вывод)\s*:\s*(\S.*)$", re.IGNORECASE | re.UNICODE)
_AGRO_VYVOD_RX = re.compile(
    r"^\s*(?:\*\*)?(?:🌿\s*)?(Вывод)(?:\*\*)?\s*:\s*(?:\*\*)?\s*(\S[\s\S]*)$",
    re.IGNORECASE | re.UNICODE)
_AGRO_SUBHEAD_RX = re.compile(r"^\s*\*\*([^*\n]+?)\*\*\s*$", re.UNICODE)
_EMOJI_ANY_RX = re.compile(r"[%s]" % _EMOJI_CHARS, re.UNICODE)
_AGRO_SUBHEAD_EMOJIS = (
    (re.compile(r"предупрежд|опасн|не\s+делайт|ошибк|важно", re.I), "⚠️"),
    (re.compile(r"болезн|вредител|защит|гнил|плесен|пятн", re.I), "🛡️"),
    (re.compile(r"обрез|срез|секатор|плет", re.I), "✂️"),
    (re.compile(r"полив|влажн|увлажн|сырост", re.I), "💧"),
    (re.compile(r"проветр|просуш|сушк|вентиляц", re.I), "🌬️"),
    (re.compile(r"подкорм|удобрен|питани", re.I), "🌿"),
    (re.compile(r"осенн|зим|листв|укрыт", re.I), "🍂"),
    (re.compile(r"посад|пересад|выращ|рассад|укорен", re.I), "🌱"),
    (re.compile(r"осмотр|диагност|проверь|разберите", re.I), "🔍"),
)


def _bold_vyvod(block):
    m = _VYVOD_RX.match(block)
    return "**%s**: %s" % (m.group(1), m.group(2)) if m else block


def _agro_vyvod(block):
    """Возвращает оформленный вывод или None, если блок не является выводом.

    Каждая непустая строка содержания получает курсив отдельно: MarkdownV2
    остаётся валидным и при многострочном выводе, а переносы не теряются.
    """
    m = _AGRO_VYVOD_RX.match(block)
    if not m:
        return None
    content = m.group(2).strip()
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not lines:
        return None
    italic = "\n".join(line if line.startswith("_") and line.endswith("_")
                       else "_%s_" % line for line in lines)
    return "**🌿 %s:** %s" % (m.group(1), italic)


def _agro_subheading(block, used):
    """Добавляет один тематический emoji только к явному жирному подзаголовку."""
    if used >= 4:
        return block, False
    m = _AGRO_SUBHEAD_RX.match(block)
    if not m:
        return block, False
    heading = m.group(1).strip()
    if _EMOJI_ANY_RX.search(heading):
        return block, False
    for rx, emoji in _AGRO_SUBHEAD_EMOJIS:
        if rx.search(heading):
            return "**%s %s**" % (emoji, heading), True
    return block, False


def format_post(text, keep_headline_emoji=False, agro_style=False):
    """Обычный/старый пост -> целевой макет с **маркерами** (без экранирования).

    keep_headline_emoji=True (agro-канал): ведущий эмодзи первого абзаца —
    часть заголовка и сохраняется (стилевая подача «заголовок с эмодзи»);
    в AI-канале эмодзи по-прежнему снимается.
    agro_style=True добавляет только к AGRO: тематические emoji к уже жирным
    практическим подзаголовкам и курсивное содержание существующего вывода.
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
        head = _clean_headline(b0["lines"][0], keep_emoji=keep_headline_emoji)
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

    agro_subheads = 0
    for b in blocks:
        lines = [x.strip() for x in b["lines"] if x.strip()]
        if not lines:
            continue
        if b["label"] is None:
            raw = "\n".join(lines)
            agro_vyvod = _agro_vyvod(raw) if agro_style else None
            if agro_vyvod:
                rendered.append(agro_vyvod)
                continue
            block = _bold_vyvod(" ".join(lines))
            if agro_style:
                block, added = _agro_subheading(block, agro_subheads)
                agro_subheads += int(added)
            rendered.append(block)
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


def _esc_md(s):
    """Экранирование спецсимволов MarkdownV2 (как внутри **жирного**)."""
    return "".join("\\%s" % c if c in MDV2_SPECIALS else c for c in s)


# курсивная ремарка: парные _..._ в границах слова/строки, до 80 символов;
# открывающий _ не приклеен к слову, закрывающий — не внутри слова. Поэтому
# непарные _ (URL «a_b», «файл_имя») разметкой НЕ считаются — литерал
_ITALIC_RX = re.compile(
    r"(?<![\w\\])_([^_\n\s](?:[^_\n]{0,78}[^_\n\s])?)_(?![\w])")


def _md_plain(s):
    """Не-жирный сегмент: парные _ремарки_ -> курсив MarkdownV2; непарные _
    и прочие спецсимволы экранированы литерально. Вложенных сущностей не
    создаём (MarkdownV2 их не поддерживает): курсив внутри жирного не
    разбирается — _ внутри **...** всегда литерал."""
    out = []
    pos = 0
    for m in _ITALIC_RX.finditer(s):
        out.append(_esc_md(s[pos:m.start()]))
        out.append("_%s_" % _esc_md(m.group(1)))
        pos = m.end()
    out.append(_esc_md(s[pos:]))
    return "".join(out)


def to_markdownv2(text):
    """plain-текст с парами **жирное** и _курсив_ -> валидный MarkdownV2.
    Жирное — ОДИНАРНЫМИ звёздочками *текст*, курсив — _текст_ (так их
    понимает Telegram: **текст** не рендерится жирным); непарные ** и _
    выводятся буквально; весь прочий текст экранируется."""
    parts = text.split("**")
    segs = []
    n = len(parts)
    for i, p in enumerate(parts):
        bold = (i % 2 == 1) and (n % 2 == 1 or i <= n - 3)
        if i % 2 == 1 and not bold:
            p = "**" + p  # непарный маркер — восстанавливаем как литерал
        if bold:
            segs.append("*%s*" % _esc_md(p))
        else:
            segs.append(_md_plain(p))
    return "".join(segs)


def unescape_markdownv2(text):
    """Снимает маркеры жирного (*текст*) и курсива (_текст_) и экранирование
    спецсимволов MarkdownV2 (тесты + plain-fallback подписи/сообщения, когда
    API отвергает parse_mode): на выходе чистый текст без markdown-символов.
    Непарные *_ в исходном тексте не страдают: они экранированы (\\* / \\_)
    и снимаются как литералы уже вторым шагом."""
    text = re.sub(r"(?<!\\)[*_]", "", text)
    return re.sub(r"\\([_*\[\]()~`>#+\-=|{}.!\\])", r"\1", text)
