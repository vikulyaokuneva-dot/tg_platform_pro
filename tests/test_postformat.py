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


def test_agro_vyvod_is_bold_label_with_italic_multiline_content():
    post = ("Осенняя подготовка грядки\n\n"
            "Обычный абзац остаётся без визуальных изменений.\n\n"
            "Вывод: Проверьте pH 5.5 (без спешки)!\n"
            "Не вносите удобрение в сухую почву.\n\n"
            "Источник: https://example.com/a-b\n#Практика")
    f = pf.format_post(post, keep_headline_emoji=True, agro_style=True)
    assert "Обычный абзац остаётся без визуальных изменений." in f
    assert ("**🌿 Вывод:** _Проверьте pH 5.5 (без спешки)!_\n"
            "_Не вносите удобрение в сухую почву._") in f
    md = pf.to_markdownv2(f)
    assert r"*🌿 Вывод:* _Проверьте pH 5\.5 \(без спешки\)\!_" in md
    assert r"_Не вносите удобрение в сухую почву\._" in md
    assert pf.format_post(f, keep_headline_emoji=True, agro_style=True) == f


def test_agro_subheadings_get_thematic_emoji_without_duplicates():
    post = ("Как подготовить луковицы\n\n"
            "Обычный вводный абзац.\n\n"
            "**Разберите и осмотрите каждую луковицу**\n\n"
            "Обычный текст рекомендации.\n\n"
            "**Полив перед посадкой**\n\n"
            "Обычный текст о влажности.\n\n"
            "**✂️ Обрезка повреждённых корней**\n\n"
            "Обычный текст об обрезке.\n\n"
            "**Подкормка после пересадки**\n\n"
            "Обычный текст о подкормке.\n\n"
            "**Осенние работы перед морозами**\n\n"
            "Обычный финальный абзац.\n\n"
            "**Посадка на подготовленную грядку**\n\n"
            "Обычный заключительный абзац.")
    f = pf.format_post(post, keep_headline_emoji=True, agro_style=True)
    assert "**🔍 Разберите и осмотрите каждую луковицу**" in f
    assert "**💧 Полив перед посадкой**" in f
    assert "**✂️ Обрезка повреждённых корней**" in f
    assert "**🌿 Подкормка после пересадки**" in f
    assert "**🍂 Осенние работы перед морозами**" in f
    # Лимит 2–4: следующий подзаголовок не перегружается дополнительным emoji.
    assert "**Посадка на подготовленную грядку**" in f
    assert f.count("✂️") == 1
    assert "Обычный текст рекомендации." in f


def test_agro_style_is_opt_in_and_post_without_vyvod_is_safe():
    post = ("Заголовок\n\n**Посадка луковиц**\n\n"
            "Обычный абзац без вывода.\n\nИсточник: https://example.com/a")
    ai_f = pf.format_post(post)
    agro_f = pf.format_post(post, keep_headline_emoji=True, agro_style=True)
    assert "**🌱 Посадка луковиц**" not in ai_f
    assert "**🌱 Посадка луковиц**" in agro_f
    assert "Вывод" not in agro_f


def test_telegram_enables_visual_style_for_agro_only(monkeypatch):
    post = ("Подготовка грядки\n\n**Посадка луковиц**\n\n"
            "Совет из источника.\n\nВывод: Действуйте по погоде.")
    monkeypatch.setattr(config, "BOT_TOKEN", "ai-token")
    monkeypatch.setattr(config, "CHAT_ID", "-100AI")
    monkeypatch.setattr(config, "AGRO_BOT_TOKEN", "agro-token")
    monkeypatch.setattr(config, "AGRO_CHAT_ID", "-100AGRO")
    calls = _capturing_post(monkeypatch, [OK, OK])
    assert telegram.publish_post(post).ok
    assert telegram.publish_post(post, channel="agro").ok
    assert "🌱" not in calls[0]["text"] and "🌿 Вывод" not in calls[0]["text"]
    assert "*🌱 Посадка луковиц*" in calls[1]["text"]
    assert r"*🌿 Вывод:* _Действуйте по погоде\." in calls[1]["text"]


def test_agro_style_survives_photo_split_with_valid_markdown():
    long = "Практическая рекомендация с подробным пояснением. " * 18
    post = ("Осенняя защита сада\n\nВводный абзац о подготовке сада.\n\n"
            "**Осмотрите растения на болезни**\n\n" + long + "\n\n"
            "**Проветривание и просушка укрытий**\n\n" + long + "\n\n"
            "Вывод: Действуйте в сухую погоду и не спешите с укрытием.\n\n"
            "Источник: https://example.com/autumn\n#Практика #Сад")
    f = pf.format_post(post, keep_headline_emoji=True, agro_style=True)
    cap, cont = pf.split_for_photo(f, caption_limit=1024, message_limit=4090)
    assert cap and cont
    assert "**🛡️ Осмотрите растения на болезни**" in f
    assert "**🌬️ Проветривание и просушка укрытий**" in f
    assert "**🌿 Вывод:** _Действуйте в сухую погоду и не спешите с укрытием._" in cont
    for part in (cap, cont):
        assert part.count("**") % 2 == 0
        assert pf.to_markdownv2(part)


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


def test_split_for_photo_moves_whole_blocks_only():
    """Разрез только по границам абзацев: абзац, не помещающийся целиком,
    уходит в продолжение ЦЕЛИКОМ (не режется по предложению) — ни потерь,
    ни дублей, маркеры ** остаются сбалансированными; источник (ровно один
    раз) — в конце продолжения, в подписи длинного поста его нет."""
    head = "Весенняя обрезка"
    fill = ("Начните с санитарной уборки участка. Уберите прошлогоднюю листву "
            "и мусор. Так вы снизите риск болезней летом и подготовите почву "
            "к новому сезону работы.")
    p2 = ("**Важно: не спешите. Подождите 2 недели.** Затем обработайте "
          "секатор раствором и замажьте садовым варом крупные срезы.")
    src = "Источник: https://example.com/obrezka"
    text = "%s\n\n%s\n\n%s\n\n%s" % (head, fill, p2, src)
    base = len(pf.to_markdownv2(head + "\n\n" + fill))
    sep = len(pf.to_markdownv2("\n\n"))

    # 1) лимит влезает ровно в конец первого абзаца: p2 не помещается
    #    целиком -> уходит в продолжение ЦЕЛИКОМ, а не по предложению
    cap, cont = pf.split_for_photo(text, base + 2)
    assert len(pf.to_markdownv2(cap)) <= base + 2
    assert cap == head + "\n\n" + fill          # подпись кончается блоком
    assert "Важно" not in cap                   # абзац не разрезан посередине
    assert cont.startswith("Продолжение\n\n")   # понятная пометка читателю
    assert p2 in cont and p2 not in cap         # не влезший блок цел
    # источник — ровно один раз и только в последнем сообщении
    assert src in cont and src not in cap
    for part in (cap, cont):                    # маркеры целы, MDV2 валиден
        assert part.count("**") % 2 == 0
        assert pf.to_markdownv2(part)

    # 2) лимит вмещает оба абзаца -> подпись целиком, продолжение = только
    #    пометка + источник (пустой «второй пост» из одного источника)
    full_body = head + "\n\n" + fill + "\n\n" + p2
    cap2, cont2 = pf.split_for_photo(
        text, len(pf.to_markdownv2(full_body)) + sep)
    assert cap2 == full_body
    assert cont2 == "Продолжение\n\n" + src


def test_split_for_photo_returns_none_when_unsplittable():
    """(None, None): корректное деление без потерь невозможно — ни один
    абзац тела не влезает в подпись, либо продолжение с пометкой,
    разметкой и источником не укладывается в лимит текстового сообщения.
    publish_post в этом случае обязан честно отказать ДО отправки (фото
    не уходит, статья не режется) — материал уходит в review."""
    head = "Заголовок"
    huge = "Очень длинный абзац про сад и огород. " * 40   # ~1500 символов
    # 1) единственный абзац тела не влезает под заголовок в подпись
    text1 = "%s\n\n%s\n\nИсточник: https://e.com/a" % (head, huge)
    assert pf.split_for_photo(text1, caption_limit=300) == (None, None)
    # 2) первая часть влезает, но продолжение с пометкой и источником
    #    не укладывается в лимит сообщения
    text2 = ("%s\n\nКороткий абзац помещается.\n\n%s\n\n"
             "Источник: https://e.com/a" % (head, huge))
    assert pf.split_for_photo(text2, caption_limit=100,
                              message_limit=200) == (None, None)
    # без caption_limit — прежний вырожденный контракт: пост целиком
    cap, cont = pf.split_for_photo(text1)
    assert cap == text1 == cont


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
