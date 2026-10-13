# -*- coding: utf-8 -*-
"""postformat: целевой макет финального поста + валидный MarkdownV2."""
import re

import requests

from case_pipeline import config, postformat as pf
from case_pipeline import telegram

TEMPLATE_POST = (
    "⚡ Slate: практический эффект\n"
    "\n"
    "🏢 Кто: Slate (zapier.com)\n"
    "❗️ Проблема: «Follow-up tasks were slowing down the pipeline.»\n"
    "🔧 Что автоматизировали: «Zapier connects Google Sheets and ChatGPT.»\n"
    "⚙️ Технологии: Zapier, Google Sheets\n"
    "📈 Результат: «Our agent has generated over 2,000 leads.»\n"
    "🔢 Цифры из источника: 2,000\n"
    "\n"
    "💡 Вывод для бизнеса: связка «данные → AI-обработка» убирает потери.\n"
    "💼 Если у вас сотрудники переносят заявки — такой процесс автоматизируется.\n"
    "\n"
    "Источник: https://zapier.com/customer-stories/laudable\n"
    "#Кейс #CRM #Продажи"
)

POLISH_POST = (
    "Автоматизация переоценки товаров: +51% к выручке и +48% к продажам 🚀\n"
    "\n"
    "BUNGLY\n"
    "\n"
    "Проблема: необходимость повысить эффективность ценообразования\n"
    "\n"
    "Что автоматизировали: процесс переоценки товаров\n"
    "\n"
    "Как это работало:\n"
    "* система накапливала данные о покупках на сайте и в приложении\n"
    "* тестировали только в каналах, приносящих 90% выручки\n"
    "\n"
    "Результат:\n"
    "* +51% к выручке\n"
    "* +48% к продажам в штуках\n"
    "* средневзвешенная скидка 20,5%\n"
    "\n"
    "Цифры:\n"
    "- тестовый период: 17 марта — 12 мая 2026 года\n"
    "\n"
    "Что может применить бизнес: позволяет оперативно реагировать на спрос.\n"
    "\n"
    "CTA: Автоматизируйте ценообразование и увеличьте продажи.\n"
    "\n"
    "Источник: https://mindbox.ru/journal/cases/bungly-pdp/\n"
    "#Кейс #Продажи #BUNGLY"
)


def test_template_target_layout():
    out = pf.format_post(TEMPLATE_POST)
    lines = out.split("\n")
    assert lines[0] == "**Slate: практический эффект**"
    assert lines[1] == ""                       # пустая строка после заголовка
    assert "**Компания:** Slate (zapier.com)" in out
    assert "**Проблема:** «Follow-up" in out
    assert "**Что автоматизировали:** «Zapier" in out
    assert "**Технологии:** Zapier, Google Sheets" in out
    assert "**Результат:** «Our agent" in out
    assert "**Цифры:** 2,000" in out
    assert "**Что может применить бизнес:**\n\nсвязка" in out
    assert "**CTA:**\n\nЕсли у вас" in out
    assert out.endswith("#Кейс #CRM #Продажи")
    assert "\n\nИсточник: https://zapier.com/customer-stories/laudable\n\n" in out
    # эмодзи-маркеры полей заменены жирными подписями, новых эмодзи нет
    for e in ("⚡", "🏢", "❗", "🔧", "⚙", "📈", "🔢", "💡", "💼"):
        assert e not in out


def test_polish_layout_with_bullets():
    out = pf.format_post(POLISH_POST)
    assert out.startswith("**Автоматизация переоценки товаров: +51% к выручке "
                          "и +48% к продажам**")
    assert "**Компания:** BUNGLY" in out
    assert "**Как это работало:**\n\n* система накапливала" in out
    assert "* тестировали только в каналах" in out
    assert "**Результат:**\n\n* +51% к выручке\n* +48% к продажам в штуках\n" \
           "* средневзвешенная скидка 20,5%" in out
    assert "**Цифры:**\n\n* тестовый период" in out          # '-' -> '*'
    assert "**Что может применить бизнес:**\n\nпозволяет" in out
    assert "**CTA:**\n\nАвтоматизируйте" in out
    assert "🚀" not in out
    # блоки разделены пустой строкой
    assert "\n\n**Проблема:**" in out and "\n\n**Цифры:**" in out


def test_blocks_separated_by_blank_lines():
    out = pf.format_post(POLISH_POST)
    for chunk in out.split("\n\n"):
        assert chunk.strip()


def test_idempotent():
    once = pf.format_post(TEMPLATE_POST)
    assert pf.format_post(once) == once
    twice = pf.format_post(POLISH_POST)
    assert pf.format_post(twice) == twice


def test_markdownv2_roundtrip_and_escaping():
    for sample in (TEMPLATE_POST, POLISH_POST):
        f = pf.format_post(sample)
        md = pf.to_markdownv2(f)
        # текст не теряется: восстанавливается всё, кроме маркеров жирного
        # (жирное в MarkdownV2 — одинарные *текст*)
        assert pf.unescape_markdownv2(md) == re.sub(r"\*\*", "", f)
        # между одинарными * — только жирные сегменты, всё остальное экранировано
        segs = re.split(r"(?<!\\)\*", md)
        assert len(segs) % 2 == 1
        for i, seg in enumerate(segs):
            if i % 2 == 0:
                assert not re.search(r"(?<!\\)[_*\[\]()~`>#+\-={}!|]", seg), seg[:60]
        # URL из «Источник» присутствует экранированным (точки/дефиссы с бэкслешом)
        m = re.search(r"Источник: (\S+)", f)
        assert m
        esc_url = re.sub(r"([_*\[\]()~`>#+\-={}!.\\])", r"\\\1", m.group(1))
        assert esc_url in md
        assert ("\\+51%" in md) == ("+51%" in f)   # '+' экранируется, '%' — нет


def test_unbalanced_bold_markers_literal():
    text = "текст **с незакрытым"
    md = pf.to_markdownv2(text)
    assert pf.unescape_markdownv2(md) == text      # выводим буквально, без bold


def test_bold_rendering_single_asterisk():
    """Заголовок уходит в Telegram жирным: MarkdownV2 — ОДИНАРНЫЕ *текст*
    (**текст** Telegram не рендерит жирным); маркеры ** не попадают
    в опубликованное сообщение, спецсимволы заголовка экранированы."""
    f = pf.format_post(TEMPLATE_POST)
    md = pf.to_markdownv2(f)
    assert "*Slate: практический эффект*" in md        # жирный заголовок
    assert "**" not in md                             # ** в канал не уходит
    plain = pf.unescape_markdownv2(md)
    assert plain.split("\n\n")[0] == "Slate: практический эффект"
    assert "**" not in plain and "*Slate" not in plain


def test_vyvod_word_bold_rest_plain():
    """Слово «Вывод» в начале абзаца — жирным, сам текст вывода обычный;
    «Выводная...» не затрагивается; идемпотентность format_post сохранена."""
    post = ("Итоги сезона\n\nВывод: пара советов ниже.\n\n"
            "Выводная информация: остаётся обычным текстом.\n\n"
            "Источник: https://example.com/a-b\n#Т")
    f = pf.format_post(post)
    assert "**Вывод**: пара советов ниже." in f
    assert "Выводная информация: остаётся обычным текстом." in f
    assert "**Вывод**" not in f.replace("**Вывод**: пара советов ниже.", "")
    md = pf.to_markdownv2(f)
    assert "*Вывод*: пара советов ниже\\." in md      # жирное слово, обычный текст
    assert "**" not in md
    plain = pf.unescape_markdownv2(md)
    assert "Вывод: пара советов ниже." in plain       # текст после «Вывод» цел
    assert "Выводная информация: остаётся обычным текстом." in plain
    assert "https://example\\.com/a\\-b" in md         # ссылка экранирована, цела
    assert pf.format_post(f) == f                     # идемпотентность сохранена


def test_italic_rendering_single_underscore():
    """Короткие ремарки доходят читателю курсивом: парные _..._ -> курсив
    MarkdownV2 (одинарные _); непарные _ (слово с подчёркиванием, URL) —
    литерал с экранированием; в plain-fallback маркеры курсива не остаются."""
    text = ("Заголовок\n\nРемарка _короткая_ и хвост_.\n\n"
            "Источник: https://example.com/a_b\n#Т")
    md = pf.to_markdownv2(text)
    assert "_короткая_" in md                  # курсив — одинарные подчёркивания
    assert "__" not in md
    assert "хвост\\_" in md                    # непарное _ — литерал
    assert "a\\_b" in md                       # _ внутри URL не разбирается
    plain = pf.unescape_markdownv2(md)
    assert "Ремарка короткая и хвост_." in plain   # маркеры сняты, текст цел
    assert "https://example.com/a_b" in plain      # литерал _ сохранён


def test_no_bold_italic_nesting():
    """Вложенных сущностей MarkdownV2 нет: курсив внутри **жирного** не
    разбирается — _ там всегда литерал (иначе Bot API отвергает сообщение)."""
    md = pf.to_markdownv2("Хвост **жирный _курсив_ хвост** конец.")
    assert "*жирный \\_курсив\\_ хвост*" in md


def test_headline_emoji_kept_for_agro_only():
    """agro-стиль: ведущий эмодзи заголовка — часть подачи и сохраняется
    (keep_headline_emoji=True); AI-канал по-прежнему снимает эмодзи."""
    post = ("\U0001F33F Заголовок поста\n\nАбзац текста.\n\n"
            "Источник: https://e.com/a")
    agro_fmt = pf.format_post(post, keep_headline_emoji=True)
    ai_fmt = pf.format_post(post)
    assert agro_fmt.split("\n\n")[0] == "**\U0001F33F Заголовок поста**"
    assert ai_fmt.split("\n\n")[0] == "**Заголовок поста**"
    assert pf.format_post(agro_fmt, keep_headline_emoji=True) == agro_fmt


def test_split_for_photo_keeps_markers_balanced():
    """Разрез по границе предложения не оставляет открытый **: если префикс
    обрывает жирный сегмент — берётся более поздняя граница, а если она не
    влезает в лимит — абзац целиком уходит в продолжение (текст и маркеры
    целы, ни потерь, ни дублей)."""
    head = "Весенняя обрезка"
    fill = ("Начните с санитарной уборки участка. Уберите прошлогоднюю листву "
            "и мусор. Так вы снизите риск болезней летом и подготовите почву "
            "к новому сезону работы.")
    p2 = ("**Важно: не спешите. Подождите 2 недели.** Затем обработайте "
          "секатор раствором и замажьте садовым варом крупные срезы.")
    src = "Источник: https://example.com/obrezka"
    text = "%s\n\n%s\n\n%s\n\n%s" % (head, fill, p2, src)
    # «Источник:» всегда в подписи (контракт split_for_photo) — base учитывает его
    base = len(pf.to_markdownv2(head + "\n\n" + fill + "\n\n" + src))
    sep = len(pf.to_markdownv2("\n\n"))          # разделитель блоков в подписи

    # 1) в лимит влезает только незакрытый префикс «**Важно: не спешите.» —
    #    такой разрез запрещён, абзац уходит в продолжение целиком
    limit1 = base + sep + len(pf.to_markdownv2("**Важно: не спешите.")) + 2
    cap, cont = pf.split_for_photo(text, limit1)
    assert "Важно" not in cap and "Важно: не спешите" in cont
    assert "Подождите 2 недели." in cont and "Затем обработайте" in cont
    # 2) в лимит влезает сбалансированная граница (конец полного **сегмента)
    limit2 = base + sep + len(pf.to_markdownv2(
        "**Важно: не спешите. Подождите 2 недели.**")) + 2
    cap, cont = pf.split_for_photo(text, limit2)
    assert "**Важно: не спешите. Подождите 2 недели.**" in cap
    assert "Затем обработайте" in cont
    for part in (cap, cont):
        assert part.count("**") % 2 == 0          # маркеры сбалансированы
        assert pf.to_markdownv2(part)             # обе части валидны как MDV2


def _capturing_post(monkeypatch, responses):
    calls = []

    class Resp:
        def __init__(self, payload, status):
            self._p, self.status_code, self.content = payload, status, b"{}"

        def json(self):
            return self._p

    def fake_post(url, json=None, timeout=None, **kw):
        calls.append(json)
        payload, status = responses[min(len(calls) - 1, len(responses) - 1)]
        return Resp(payload, status)
    monkeypatch.setattr(requests, "post", fake_post)
    return calls


OK = ({"ok": True, "result": {"message_id": 123}}, 200)


def test_publish_sends_markdownv2(monkeypatch):
    monkeypatch.setattr(config, "BOT_TOKEN", "123:ABC")
    calls = _capturing_post(monkeypatch, [OK])
    res = telegram.publish_post(TEMPLATE_POST)
    assert res.ok and res.message_id == 123
    payload = calls[0]
    assert payload["parse_mode"] == "MarkdownV2"
    assert pf.unescape_markdownv2(payload["text"]) == re.sub(
        r"\*\*", "", pf.format_post(TEMPLATE_POST))


def test_publish_parse_fallback_plain(monkeypatch):
    monkeypatch.setattr(config, "BOT_TOKEN", "123:ABC")
    bad = ({"ok": False, "description": "Bad Request: can't parse entities"}, 400)
    calls = _capturing_post(monkeypatch, [bad, bad, bad, OK])  # 3 ретрая MD -> plain ok
    res = telegram.publish_post(POLISH_POST)
    assert res.ok
    assert calls[-1].get("parse_mode") is None
    assert calls[-1]["text"] == pf.unescape_markdownv2(
        pf.to_markdownv2(pf.format_post(POLISH_POST)))
    assert "**" not in calls[-1]["text"]            # markdown-символы не публикуются


def test_publish_non_parse_error_no_fallback(monkeypatch):
    monkeypatch.setattr(config, "BOT_TOKEN", "123:ABC")
    bad = ({"ok": False, "description": "Forbidden: bot was kicked"}, 403)
    calls = _capturing_post(monkeypatch, [bad])
    res = telegram.publish_post(POLISH_POST)
    assert not res.ok
    assert len(calls) == 3                      # ретраи того же payload, без plain-входа
    assert all(c["parse_mode"] == "MarkdownV2" for c in calls)


def test_dry_run_no_http(monkeypatch):
    calls = _capturing_post(monkeypatch, [OK])
    res = telegram.publish_post(TEMPLATE_POST, dry_run=True)
    assert res.ok and res.message_id == 0
    assert not calls
