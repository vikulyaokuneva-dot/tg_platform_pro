# -*- coding: utf-8 -*-
"""ИИ-редактура агро-канала: ПОЛНЫЙ текст статьи -> существующий
GigaChatProvider (второго ИИ-клиента нет) + двухшаговая публикация
(фото с короткой законченной подписью -> полный текст отдельным
сообщением — регрессия обрыва в msg78).

Тесты герметичны: сеть/Telegram замоканы, реальных токенов нет
(conftest дополнительно глушит GigaChatProvider)."""
import io
import re

import pytest

from case_pipeline import agro, config, postformat, telegram
from case_pipeline import storage as storage_mod
from test_agro_channel import (ART_TITLE, ART_URL, PAR1, PAR2, ARTICLE_HTML,
                               _art_html, _fake_network, _today)

# последнее предложение длинного материала — маркер «текст передан целиком»
LONG_LAST = ("После таких работ грядки спокойно уходят под зиму и весной "
             "требуют меньше труда.")
LONG2 = "".join(
    "Шаг %d: перекопайте верхний слой, добавьте перегной и разбейте комья, "
    "чтобы влага уходила вглубь, а корни получали воздух. " % i
    for i in range(1, 90)) + LONG_LAST
# маркер начала материала (для проверки, что начало тоже в промпте)
LONG_HEAD = "Осенняя заправка почвы начинается с оценки её состояния."

# эталонный ответ «модели»: заголовок, абзацы через пустую строку, эмодзи,
# вывод; без «Источник:» и хэштегов (их добавляет _finalize_post)
AI_POST = (
    "Подготовка почвы к зиме: короткий план садовода\n"
    "\n"
    "🍂 " + LONG_HEAD + " Сначала уберите растительные остатки, затем оцените "
    "структуру и влажность: от этого зависит, какие приёмы применять.\n"
    "\n"
    "• Соберите растительные остатки: на них зимуют возбудители болезней и "
    "вредители, компостируйте их отдельно от грядок.\n"
    "\n"
    "• Внесите перепревший компост — он восполняет органическое вещество и "
    "улучшает влажностный режим почвы.\n"
    "\n"
    "• Рыхлите уплотнённые участки, чтобы воздух доходил до корней.\n"
    "\n"
    "• Проверьте кислотность и дренаж: застой воды зимой опаснее мороза.\n"
    "\n"
    "• Замульчируйте грядки перепревшим компостом, чтобы сохранить влагу и "
    "защитить почвенных микроорганизмов.\n"
    "\n"
    "Вывод: потраченная осенью пара часов на структуру и органику вернётся "
    "весной дружными всходами и здоровой рассадой."
)

AGRO_CRED = {"AGRO_PUBLISH": True, "AGRO_BOT_TOKEN": "t",
             "AGRO_CHAT_ID": "-100AGRO"}


def _long_html():
    return ARTICLE_HTML % (ART_TITLE, ART_TITLE, _today(), PAR1, LONG2)


@pytest.fixture()
def st(tmp_path):
    return storage_mod.Storage(str(tmp_path / "agro.db"))


class StubProvider:
    """Провайдер с контрактом GigaChatProvider (available/complete/
    last_usage): пишет вызовы, отдаёт готовые ответы. Без ответов —
    AssertionError (ловит лишние/повторные вызовы ИИ)."""
    name = "stub"
    available = True

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []
        self.last_usage = {"total_tokens": 2200, "prompt_tokens": 1800,
                           "completion_tokens": 400}

    def complete(self, messages):
        self.calls.append(messages)
        if not self.replies:
            raise AssertionError("лишний вызов ИИ (%d-й)" % len(self.calls))
        return self.replies.pop(0)


def _user_msg(provider, i=0):
    return provider.calls[i][1]["content"]


# ---------- 1. Полный текст статьи в промпте (не только начало) ----------

def test_ai_receives_full_article_text_not_its_beginning(st, monkeypatch):
    """Регрессия «не только начало»: промпт получает ВЕСЬ извлечённый текст
    (заголовок+конец >6000 символов), а не срез [:6000]."""
    _fake_network(monkeypatch, {ART_URL: _long_html()})
    prov = StubProvider(AI_POST)
    r = agro.process_url(st, ART_URL, "botanichka", dry_run=True, provider=prov)
    assert r["status"] == "post_ready" and r["ai"] == "edited", r
    assert len(prov.calls) == 1, "успех должен быть с первого вызова"
    user = _user_msg(prov)
    head_marker = "Озимый чеснок сажают за 35-45 дней до устойчивых заморозков"
    assert head_marker in user and LONG_LAST in user    # начало и конец статьи
    assert user.index(head_marker) < user.index(LONG_LAST)
    assert len(user) > 6000                             # срез [:6000] отсутствует
    sys_msg = prov.calls[0][0]["content"]
    # поручения редактору из задания зафиксированы в промпте
    for needle in ("5-7", "придумывай", "вывод", "ЦЕЛИКОМ",
                  "последовательные шаги"):
        assert needle in sys_msg, needle


# ---------- 2. Существующий клиент проекта, без нового ИИ-клиента ----------

def test_ai_edit_uses_existing_provider_factory_no_new_client(st, monkeypatch):
    """Точка входа — ai.get_provider() того же модуля, что AI-канал:
    в agro нет своего клиента/URL/токена, вызов идёт через провайдер."""
    src = io.open(agro.__file__, encoding="utf-8").read()
    assert "GigaChatProvider(" not in src and "api.giga" not in src
    assert "openai" not in src.lower()
    _fake_network(monkeypatch, {ART_URL: _art_html()})
    prov = StubProvider(AI_POST)
    monkeypatch.setattr(agro.ai_mod, "get_provider", lambda *a, **k: prov)
    r = agro.process_url(st, ART_URL, "botanichka", dry_run=True)  # без provider=
    assert r["ai"] == "edited" and len(prov.calls) == 1, r
    assert prov.calls[0][0]["role"] == "system"


# ---------- 3. Формат итогового поста: заголовок/абзацы/эмодзи/вывод ------

def test_ai_post_keeps_headline_paragraphs_emoji_conclusion(st, monkeypatch):
    _fake_network(monkeypatch, {ART_URL: _art_html()})
    prov = StubProvider(AI_POST)
    r = agro.process_url(st, ART_URL, "botanichka", dry_run=True, provider=prov)
    assert r["status"] == "post_ready", r
    post = st.get(st.add(ART_URL, "botanichka"))["post_text"]
    blocks = [b for b in post.split("\n\n") if b.strip()]
    assert blocks[0] == AI_POST.split("\n\n")[0]          # заголовок первой строкой
    assert "🍂" in post and "Вывод:" in post              # эмодзи + конкретный вывод
    # все выбранные советы и вывод дошли до поста (полнота, без обрыва)
    for b in AI_POST.split("\n\n")[1:]:
        assert b in post, b
    assert post.rstrip().split("\n")[-1].split() == r["hashtags"]  # теги последней строкой
    assert "Источник: " + ART_URL in post
    assert agro.editorial_agro(post, PAR1 + "\n\n" + PAR2) == []


# ---------- 4-6. Неудача редактуры -> review, без публикации и обрывов ----

def _publish_traps(monkeypatch):
    monkeypatch.setattr(config, "AGRO_PUBLISH", True, raising=False)
    monkeypatch.setattr(config, "AGRO_BOT_TOKEN", "t", raising=False)
    monkeypatch.setattr(config, "AGRO_CHAT_ID", "-100AGRO", raising=False)
    monkeypatch.setattr(agro.httpclient, "fetch_bytes",
                        lambda url, **kw: b"\xff\xd8" + b"x" * 20000)

    def boom(*a, **k):
        raise AssertionError("неудачная редактура не должна публиковаться")
    monkeypatch.setattr(telegram, "send_photo", boom)
    monkeypatch.setattr(telegram, "send_message", boom)
    return boom


def test_ai_failure_goes_to_review_without_publishing(st, monkeypatch):
    """Провайдер вернул пусто/ошибку: после 1 повтора (2 вызова — максимум)
    материал уходит в review, сырой текст НЕ публикуется."""
    _fake_network(monkeypatch, {ART_URL: _art_html()})
    _publish_traps(monkeypatch)
    prov = StubProvider(None, None)
    r = agro.process_url(st, ART_URL, "botanichka", publish=True,
                         dry_run=False, provider=prov)
    assert r["status"] == "review" and r["reason"] == "ai edit failed", r
    assert r["ai"] == "failed"
    assert len(prov.calls) == 2, "ровно 1 повтор, не бесконечные ретраи"
    row = st.get(st.add(ART_URL, "x"))
    assert row["status"] == "review" and not row["post_text"]
    assert st.db.execute("SELECT COUNT(*) c FROM publications").fetchone()["c"] == 0


def test_ai_contract_violation_retries_then_review(st, monkeypatch):
    """Модель ответила мусором (нет структуры «заголовок+абзацы»): повтор,
    затем review — обрывка не публикуется как готовый пост."""
    _fake_network(monkeypatch, {ART_URL: _art_html()})
    _publish_traps(monkeypatch)
    prov = StubProvider("короткий обрыв", "тоже не пост")
    r = agro.process_url(st, ART_URL, "botanichka", publish=True,
                         dry_run=False, provider=prov)
    assert r["status"] == "review" and len(prov.calls) == 2, r
    assert "ai edit" in str(st.get(st.add(ART_URL, "x"))["reason"])


def test_ai_too_long_is_reviewed_not_truncated(st, monkeypatch):
    """Слишком длинный ответ модели НЕ усекается «по лимиту»: он идёт на
    повтор, затем review — формальное соблюдение лимита вместо полного
    текста недопустимо."""
    _fake_network(monkeypatch, {ART_URL: _art_html()})
    _publish_traps(monkeypatch)
    big = AI_POST + "\n\n" + "Заполненный текст без единой цифры. " * 110
    assert len(big) > agro.MAX_POST_CHARS
    prov = StubProvider(big, big)
    r = agro.process_url(st, ART_URL, "botanichka", publish=True,
                         dry_run=False, provider=prov)
    assert r["status"] == "review" and len(prov.calls) == 2, r
    row = st.get(st.add(ART_URL, "x"))
    assert not row["post_text"] or len(row["post_text"]) < len(big)
    # потолок снят под полный текст (полное сообщение Telegram — 4096)
    assert agro.MAX_POST_CHARS >= 3000


# ---------- 7. Без провайдера — прежний extractive-fallback ----------

def test_provider_unavailable_falls_back_to_extractive(st, monkeypatch):
    _fake_network(monkeypatch, {ART_URL: _art_html()})
    r = agro.process_url(st, ART_URL, "botanichka", dry_run=True, provider=None)
    assert r["status"] == "post_ready" and r["ai"] == "skipped", r
    post = st.get(st.add(ART_URL, "botanichka"))["post_text"]
    assert "чеснок" in post.split("\n\n")[0].lower()   # макет источника
    assert "Источник: " + ART_URL in post


# ---------- 8-10. Публикация: короткая подпись + полный текст ----------

def test_publish_sends_short_caption_then_full_text(st, monkeypatch):
    """Два сообщения: (1) фото с короткой законченной подписью без хэштегов,
    (2) полный текст (все советы, вывод, «Источник:», хэштеги) — тот же
    заголовок в обоих (связка в ленте), обрывов нет."""
    _fake_network(monkeypatch, {ART_URL: _art_html()})
    _publish_traps(monkeypatch)
    events, seen = [], {}

    def spy_photo(token, chat_id, photo_url=None, photo_bytes=None,
                  caption=None, dry_run=False, retries=2, parse_mode=None):
        events.append("photo")
        seen.update(caption=caption, photo=photo_bytes, cap_mode=parse_mode)
        return telegram.PublishResult(True, message_id=901)

    def spy_msg(token, chat_id, text, dry_run=False, parse_mode=None, retries=2):
        events.append("text")
        seen.update(full=text, full_mode=parse_mode)
        return telegram.PublishResult(True, message_id=902)
    monkeypatch.setattr(telegram, "send_photo", spy_photo)
    monkeypatch.setattr(telegram, "send_message", spy_msg)

    prov = StubProvider(AI_POST)
    r = agro.process_url(st, ART_URL, "botanichka", publish=True,
                         dry_run=False, provider=prov)
    assert r["status"] == "published" and r["telegram_message_id"] == 901, r
    assert events == ["photo", "text"]                 # фото раньше текста
    assert seen["photo"] and seen["cap_mode"] == "MarkdownV2"
    assert seen["full_mode"] == "MarkdownV2"

    cap = postformat.unescape_markdownv2(seen["caption"])
    assert len(seen["caption"]) <= 1024
    cap_blocks = [b for b in cap.split("\n\n") if b.strip()]
    assert cap_blocks[0] == "**%s**" % AI_POST.split("\n\n")[0]  # тот же заголовок
    assert cap_blocks[-1].startswith("Источник: " + ART_URL)
    assert not re.search(r"#[А-Яа-яA-Za-z]", cap), "хэштеги — в полном тексте"
    # лид — целое предложение (не обрыв на полуслове)
    assert re.search(r"[.!?…]$", cap_blocks[1]), cap_blocks[-1]

    full = postformat.unescape_markdownv2(seen["full"])
    assert len(seen["full"]) <= 4090                    # лимит сообщения
    assert full.split("\n\n")[0] == cap_blocks[0]       # связка сообщений
    for b in AI_POST.split("\n\n")[1:]:                 # полнота: всё в отправке
        assert b in full, b
    assert "Источник: " + ART_URL in full
    assert " ".join(r["hashtags"]) in full
    assert "…" not in full                              # обрыва нет


def test_caption_for_photo_is_short_and_sentence_bounded():
    """postformat.caption_for_photo: подпись = заголовок + лид по границе
    предложения + источник; длинное тело в подпись не попадает."""
    long_lead = ("Осенняя подготовка почвы — это не только перекопка: после "
                 "уборки урожая земле нужно вернуть структуру, питание и "
                 "влажностный режим, иначе весной всходы пойдут медленнее, а "
                 "почвенные микроорганизмы потеряют активность, что скажется "
                 "на всасывающей способности корней рассады овощей.") * 2
    text = ("Заголовок поста\n\n" + long_lead + "\n\nВторой абзац.\n\n"
            "Источник: " + ART_URL + "\n#Практика #Сад")
    cap = postformat.caption_for_photo(postformat.format_post(text))
    blocks = [b for b in cap.split("\n\n") if b.strip()]
    assert len(blocks) == 3, blocks                     # head + lead + source
    assert len(blocks[1]) <= 320 + 1
    assert re.search(r"[.!?…]$", blocks[1])             # целое предложение
    assert "Второй абзац" not in cap                     # тело — во 2-м сообщении
    assert "#Практика" not in cap
    assert blocks[-1] == "Источник: " + ART_URL
    assert len(postformat.to_markdownv2(cap)) <= 1024


def test_url_and_image_preserved_with_ai_edit(st, monkeypatch):
    """Редактура не меняет URL и изображение: строка и caption/полный текст
    ссылаются на исходный материал."""
    _fake_network(monkeypatch, {ART_URL: _art_html()})
    prov = StubProvider(AI_POST)
    r = agro.process_url(st, ART_URL, "botanichka", dry_run=True, provider=prov)
    assert r["status"] == "post_ready", r
    row = st.get(st.add(ART_URL, "botanichka"))
    assert row["url"] == ART_URL
    assert row["image_url"] == "https://cdn.example.test/agro/chesnok.jpg"
    assert "Источник: " + ART_URL in row["post_text"]


# ---------- 11-12. Кэш и дедуп: без лишних вызовов ИИ и повторных отправок -

def test_failed_image_fetch_then_rerun_uses_cache_without_reedit(st, monkeypatch):
    """post_text кэшируется: после сбоя скачивания фото повторный прогон
    НЕ вызывает ИИ заново и публикует тот же пост."""
    _fake_network(monkeypatch, {ART_URL: _art_html()})
    monkeypatch.setattr(config, "AGRO_PUBLISH", True, raising=False)
    monkeypatch.setattr(config, "AGRO_BOT_TOKEN", "t", raising=False)
    monkeypatch.setattr(config, "AGRO_CHAT_ID", "-100AGRO", raising=False)
    prov = StubProvider(AI_POST)
    monkeypatch.setattr(agro.httpclient, "fetch_bytes",
                        lambda url, **kw: (_ for _ in ()).throw(RuntimeError("403")))
    r1 = agro.process_url(st, ART_URL, "botanichka", publish=True,
                          dry_run=False, provider=prov)
    assert r1["status"] == "failed" and len(prov.calls) == 1, r1
    cached_post = st.get(st.add(ART_URL, "x"))["post_text"]
    assert cached_post

    sent = []
    monkeypatch.setattr(agro.httpclient, "fetch_bytes",
                        lambda url, **kw: b"\xff\xd8" + b"x" * 20000)
    monkeypatch.setattr(telegram, "send_photo",
                        lambda *a, **k: (sent.append("photo"),
                                         telegram.PublishResult(True, 701))[1])
    monkeypatch.setattr(telegram, "send_message",
                        lambda *a, **k: (sent.append("text"),
                                         telegram.PublishResult(True, 702))[1])
    r2 = agro.process_url(st, ART_URL, "botanichka", publish=True,
                          dry_run=False, provider=prov)
    assert r2["status"] == "published", r2
    assert r2["ai"] == "cached"                         # кэш, не повторный ИИ
    assert len(prov.calls) == 1                         # лишних вызовов не было
    assert st.get(st.add(ART_URL, "x"))["post_text"] == cached_post
    assert sent == ["photo", "text"]


def test_rerun_after_publish_no_reedit_no_repost(st, monkeypatch):
    _fake_network(monkeypatch, {ART_URL: _art_html()})
    monkeypatch.setattr(config, "AGRO_PUBLISH", True, raising=False)
    monkeypatch.setattr(config, "AGRO_BOT_TOKEN", "t", raising=False)
    monkeypatch.setattr(config, "AGRO_CHAT_ID", "-100AGRO", raising=False)
    monkeypatch.setattr(agro.httpclient, "fetch_bytes",
                        lambda url, **kw: b"\xff\xd8" + b"x" * 20000)
    prov = StubProvider(AI_POST)
    sends = []

    def sp(*a, **k):
        sends.append(1)
        return telegram.PublishResult(True, 1)
    monkeypatch.setattr(telegram, "send_photo", sp)
    monkeypatch.setattr(telegram, "send_message", sp)

    r1 = agro.process_url(st, ART_URL, "botanichka", publish=True,
                          dry_run=False, provider=prov)
    assert r1["status"] == "published", r1
    r2 = agro.process_url(st, ART_URL, "botanichka", publish=True,
                          dry_run=False, provider=prov)
    assert r2["status"] == "skipped" and "already" in r2["reason"], r2
    assert len(prov.calls) == 1                         # редактура не повторилась
    assert len(sends) == 2                              # photo+text один раз


# ---------- диагностика summary (счётчики ИИ) ----------

def test_run_summary_counts_ai_states(st, monkeypatch):
    _fake_network(monkeypatch, {ART_URL: _art_html()})
    monkeypatch.setattr(agro.adapters.ADAPTERS["botanichka"], "discover",
                        lambda: [ART_URL])
    prov = StubProvider(AI_POST)
    s = agro.run(dry_run=True, publish=False, sources=["botanichka"], st=st,
                 provider=prov)
    assert s["post_ready"] == 1 and s["ai_edited"] == 1, s
    for k in ("ai_failed", "ai_cached", "ai_skipped"):
        assert k in s and s[k] == 0, (k, s)
