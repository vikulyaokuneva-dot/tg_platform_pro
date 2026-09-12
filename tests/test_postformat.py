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
        assert pf.unescape_markdownv2(md) == f     # nothing lost
        # между **маркерами** — только жирные сегменты, всё остальное экранировано
        segs = re.split(r"(?<!\\)\*\*", md)
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
    assert pf.unescape_markdownv2(payload["text"]) == pf.format_post(TEMPLATE_POST)


def test_publish_parse_fallback_plain(monkeypatch):
    monkeypatch.setattr(config, "BOT_TOKEN", "123:ABC")
    bad = ({"ok": False, "description": "Bad Request: can't parse entities"}, 400)
    calls = _capturing_post(monkeypatch, [bad, bad, bad, OK])  # 3 ретрая MD -> plain ok
    res = telegram.publish_post(POLISH_POST)
    assert res.ok
    assert calls[-1].get("parse_mode") is None
    assert calls[-1]["text"] == pf.format_post(POLISH_POST)


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
