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


def _esc(s):
    """Экранирование спецсимволов MarkdownV2 — как внутри **жирного** сегмента."""
    return "".join("\\" + c if c in postformat.MDV2_SPECIALS else c for c in s)

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
    # поручения редактору из задания зафиксированы в промпте:
    # полнота материала, факты из источника, живой голос и стиль подачи
    for needle in ("ЦЕЛИКОМ", "придумывай", "вывод", "эмодзи", "900-1800",
                   "жирным", "курсивом", "последние публикации"):
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

def test_publish_short_post_single_photo_with_full_caption(st, monkeypatch):
    """Короткий ИИ-пост (весь пост, после экранирования, помещается в лимит
    подписи): публикация ОДНИМ сообщением — фото с полным текстом в подписи
    (заголовок, вступление, рекомендации, вывод, «Источник:», хэштеги);
    второе текстовое сообщение НЕ отправляется — пост не превращается во
    «второй пост». Обрывов нет, заголовок на месте."""
    _fake_network(monkeypatch, {ART_URL: _art_html()})
    _publish_traps(monkeypatch)
    events, seen = [], {}

    def spy_photo(token, chat_id, photo_url=None, photo_bytes=None,
                  caption=None, dry_run=False, retries=2, parse_mode=None):
        events.append("photo")
        seen.update(caption=caption, photo=photo_bytes, cap_mode=parse_mode)
        return telegram.PublishResult(True, message_id=901)

    def boom_msg(*a, **k):
        raise AssertionError("короткий пост должен уйти одним сообщением")
    monkeypatch.setattr(telegram, "send_photo", spy_photo)
    monkeypatch.setattr(telegram, "send_message", boom_msg)

    prov = StubProvider(AI_POST)
    r = agro.process_url(st, ART_URL, "botanichka", publish=True,
                         dry_run=False, provider=prov)
    assert r["status"] == "published" and r["telegram_message_id"] == 901, r
    assert events == ["photo"]                          # ровно одно сообщение
    assert seen["photo"] and seen["cap_mode"] == "HTML"

    cap = postformat.unescape_telegram_html(seen["caption"])
    assert len(seen["caption"]) <= telegram.CAPTION_LIMIT
    cap_blocks = [b for b in cap.split("\n\n") if b.strip()]
    # заголовок жирным в HTML, служебные Markdown-маркеры не публикуются
    assert "<b>%s</b>" % AI_POST.split("\n\n")[0] in seen["caption"]
    assert "**" not in seen["caption"]
    assert cap_blocks[0] == AI_POST.split("\n\n")[0]   # текст заголовка цел
    assert any(b.startswith("Источник: " + ART_URL) for b in cap_blocks)
    # вступление-анонс в подписи — целое предложение (не обрыв на полуслове)
    assert cap_blocks[1] == AI_POST.split("\n\n")[1]
    assert re.search(r"[.!?…]$", cap_blocks[1]), cap_blocks[1]
    # полнота: рекомендации и вывод — в подписи (пост целиком, без обрезки)
    for b in AI_POST.split("\n\n")[2:]:
        if b.startswith("Вывод:"):
            assert "🌿 Вывод:" in cap
            assert b.split(":", 1)[1].strip() in cap
        else:
            assert b in cap, b
    # короткий пост: источник указан ровно один раз — в конце единого сообщения
    assert cap.count("Источник: " + ART_URL) == 1
    assert " ".join(r["hashtags"]) in cap
    assert "…" not in cap                               # обрыва нет


def test_split_for_photo_whole_blocks_no_loss_no_dup():
    """postformat.split_for_photo (длинный пост): разрез ТОЛЬКО по границам
    смысловых блоков — подпись получает заголовок и целые абзацы, не
    влезающий абзац уходит в продолжение ЦЕЛИКОМ (не режется по
    предложению). Продолжение = ровно остаток тела без повторного
    заголовка и дублей; источник — ровно один раз, в конце последнего
    сообщения; хэштеги — там же, в подписи их нет."""
    limit = 300                      # маленький лимит — управляемый разрез
    p1 = ("Первый абзац короткий и влезает целиком. "
          "Он состоит из двух предложений.")
    p2 = "Второй абзац тоже влезет целиком. В нём ровно две мысли."
    p3 = ("Третий абзац длинный и не поместится целиком. Первая его мысль "
          "не должна занимать место в подписи. Вторая мысль уйдёт в "
          "продолжение вместе с первой. Третья мысль останется там же.")
    p4 = "Четвёртый абзац уйдёт в продолжение целиком. Он в конце статьи."
    text = ("Заголовок поста\n\n" + p1 + "\n\n" + p2 + "\n\n" + p3 +
            "\n\n" + p4 + "\n\nИсточник: " + ART_URL + "\n#Практика #Сад")
    cap, msg = postformat.split_for_photo(postformat.format_post(text),
                                          caption_limit=limit)
    cap_blocks = [b for b in cap.split("\n\n") if b.strip()]
    msg_blocks = [b for b in msg.split("\n\n") if b.strip()]
    # лимит считается по экранированному тексту (как его считает Telegram)
    assert len(postformat.to_markdownv2(cap)) <= limit
    assert cap_blocks[0] == "**Заголовок поста**"
    # подпись: два целых абзаца; длинный третий НЕ разрезан по предложению
    assert p1 in cap and p2 in cap
    assert p3 not in cap
    assert cap_blocks[-1] == p2                  # подпись кончается блоком
    # продолжение: пометка + остаток ЦЕЛИКОМ, без заголовка и дублей
    assert msg_blocks[0] == "Продолжение"
    assert "**Заголовок поста**" not in msg
    assert p1 not in msg and p2 not in msg
    assert p3 in msg and p4 in msg               # не влезшие блоки целы
    # источник — ровно один раз и только в конце продолжения
    assert "Источник: " + ART_URL not in cap
    assert msg.endswith("Источник: " + ART_URL + "\n\n#Практика #Сад")
    # ни потерь, ни дублей: каждый абзац ровно в одном сообщении
    for p in (p1, p2, p3, p4):
        assert (p in cap) != (p in msg), p[:40]
    # маркеры ** сбалансированы, обе части валидны как MarkdownV2
    for part in (cap, msg):
        assert part.count("**") % 2 == 0
        assert postformat.to_markdownv2(part)
    assert len(postformat.to_markdownv2(msg)) < telegram.MESSAGE_LIMIT


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
    assert sent == ["photo"]                            # короткий пост: 1 сообщение


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
    assert len(sends) == 1                              # фото с полным текстом один раз


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


# ---------- регрессия msg80/81 (яблоня): полнота + отсутствие дубля -------

YAB_URL = ("https://www.botanichka.ru/article/yablonya-uhodit-v-zimu-"
           "s-listyami-nuzhno-li-ih-obryvat/")
YAB_TITLE = "Яблоня уходит в зиму с листьями: нужно ли их обрывать"
# вступление — дословный фрагмент реально опубликованного (дефектного) поста
YAB_INTRO = ("Конец октября или ноябрь. Липы, берёзы и вишни давно стоят "
             "голые, а яблоня всё ещё держит листья – где-то зелёные, где-то "
             "уже бурые и сухие. Рука тянется их обобрать: кажется, что дерево "
             "«не успело» подготовиться к зиме и ему надо помочь. Как правило, "
             "делать этого не нужно. Важнее понять, почему листопад "
             "задержался и успели ли приросты текущего года закончить рост.")
# хвост статьи — те самые рекомендации, которых не хватало в msg81
YAB_TAIL = ("Полезно сравнить яблоню с другими яблонями похожего возраста: "
            "если листва задержалась сразу на многих деревьях после долгой "
            "тёплой осени, велика роль погоды. Молодые активно растущие "
            "яблони заканчивают вегетацию позже взрослых. Обрывать листья "
            "вручную не нужно: они защищают почки зимующих побегов от резких "
            "морозов, а процесс листопада остановить всё равно нельзя. Перед "
            "зимой уберите опавшую листву из приствольных кругов и "
            "замульчируйте почву слоем 5 см перепревшим компостом: так корни "
            "уйдут зимовать в защищённом слое. Весной проверьте, не "
            "подопрели ветки под снегом, и снимите снег с молодых саженцев "
            "сразу после оттепели.")
YAB_TEXT = YAB_INTRO + "\n\n" + YAB_TAIL
YAB_HTML = ARTICLE_HTML % (YAB_TITLE, YAB_TITLE, _today(), YAB_INTRO, YAB_TAIL)

# «дефектный» пост: структура и длина в порядке, но это только вступление
# (как msg80/81: рекомендаций и вывода нет)
YAB_INTRO_ONLY_POST = YAB_TITLE + "\n\n" + YAB_INTRO
# полноценный пост: вступление + рекомендации статьи + вывод
YAB_POST = (
    YAB_TITLE + "\n\n"
    "🍂 " + YAB_INTRO + "\n\n"
    "• Если листва задержалась сразу на нескольких яблонях после долгой "
    "тёплой осени — виновата погода, а не дерево: молодые активно растущие "
    "яблони заканчивают вегетацию позже взрослых.\n\n"
    "• Обрывать листья вручную не нужно: они защищают почки зимующих побегов "
    "от резких морозов, а процесс листопада остановить всё равно нельзя.\n\n"
    "• Перед зимой уберите опавшую листву из приствольных кругов и "
    "замульчируйте почву слоем 5 см перепревшим компостом — корни уйдут "
    "зимовать в защищённом слое.\n\n"
    "• Весной проверьте, не подопрели ветки под снегом, и сразу после "
    "оттепели снимите снег с молодых саженцев.\n\n"
    "Вывод: листья на яблоне осенью — норма; дереву важнее успеть вызреть, а "
    "листву лучше убрать после листопада."
)


def test_regression_msg81_intro_only_ai_post_is_reviewed(st, monkeypatch):
    """Регрессия msg80/81: пост, состоящий только из вступления (длина и
    структура в порядке, а рекомендаций и вывода нет), НЕ считается
    успешной редактурой: 1 повтор, затем review с диагностикой «incomplete»,
    публикации нет."""
    _fake_network(monkeypatch, {YAB_URL: YAB_HTML})
    _publish_traps(monkeypatch)
    prov = StubProvider(YAB_INTRO_ONLY_POST, YAB_INTRO_ONLY_POST)
    r = agro.process_url(st, YAB_URL, "botanichka", publish=True,
                         dry_run=False, provider=prov)
    assert r["status"] == "review" and len(prov.calls) == 2, r
    assert r["ai"] == "failed"
    row = st.get(st.add(YAB_URL, "x"))
    assert row["status"] == "review" and not row["post_text"]
    assert "incomplete" in row["reason"], row["reason"]   # причина диагностирована
    assert st.db.execute("SELECT COUNT(*) c FROM publications").fetchone()["c"] == 0


def test_regression_msg81_full_post_photo_intro_recs_in_message(st, monkeypatch):
    """Регрессия msg80/81 (положительный сценарий, длинный пост не влезает
    в подпись): подпись к фото МАКСИМАЛЬНО полная — заголовок, вступление
    и целые абзацы тела («Источник:»); второе сообщение — продолжение:
    остаток тела БЕЗ повторного заголовка, вступления и дублей; обрыва на
    полуслове нет."""
    _fake_network(monkeypatch, {YAB_URL: YAB_HTML})
    _publish_traps(monkeypatch)
    seen = {}

    def spy_photo(token, chat_id, photo_url=None, photo_bytes=None,
                  caption=None, dry_run=False, retries=2, parse_mode=None):
        seen["caption"] = caption
        return telegram.PublishResult(True, message_id=810)

    def spy_msg(token, chat_id, text, dry_run=False, parse_mode=None, retries=2):
        seen["full"] = text
        return telegram.PublishResult(True, message_id=811)
    monkeypatch.setattr(telegram, "send_photo", spy_photo)
    monkeypatch.setattr(telegram, "send_message", spy_msg)

    prov = StubProvider(YAB_POST)
    r = agro.process_url(st, YAB_URL, "botanichka", publish=True,
                         dry_run=False, provider=prov)
    assert r["status"] == "published" and r["ai"] == "edited", r

    cap = postformat.unescape_telegram_html(seen["caption"])
    full = postformat.unescape_telegram_html(seen["full"])
    # подпись МАКСИМАЛЬНО полная: заголовок + вступление + целые абзацы тела
    cap_blocks = [b for b in cap.split("\n\n") if b.strip()]
    assert cap_blocks[0] == YAB_TITLE                  # текст заголовка цел
    # заголовок и «Вывод» жирными, содержание вывода курсивом в HTML
    assert "<b>%s</b>" % YAB_TITLE in seen["caption"]
    assert "<b>🌿 Вывод:</b> <i>" in seen["full"]
    assert "**" not in seen["caption"] and "**" not in seen["full"]
    assert "держит листья" in cap_blocks[1]             # вступление в подписи
    assert "Обрывать листья вручную не нужно" in cap   # советы уже в подписи
    # подпись заканчивается целым абзацем тела (разрез только по блокам)
    assert re.search(r"[.!?…]$", cap_blocks[-1])
    # источник — ровно один раз: в подписи ДЛИННОГО поста его нет
    assert "Источник: " + YAB_URL not in cap
    assert "Сад без хлопот" not in cap                  # название канала
    assert not re.search(r"#[А-Яа-яA-Za-z]", cap)      # хэштегов в подписи нет
    assert len(seen["caption"]) <= telegram.CAPTION_LIMIT
    assert len(seen["caption"]) > 700                  # подпись заполнена, а не «короткая»
    # продолжение: пометка + остаток тела БЕЗ заголовка и дублей из подписи
    assert full.startswith("Продолжение\n\n")  # читателю ясно: та же публикация
    assert YAB_TITLE not in full                       # заголовок не дублируется
    assert "Сад без хлопот" not in full                # и название канала
    assert ("Весной проверьте" in cap) != ("Весной проверьте" in full)
    assert "Вывод:" in full and "после листопада" in full
    assert YAB_POST.split("\n\n")[1] not in full       # вступление не дублируется
    assert "Обрывать листья вручную не нужно" not in full  # и тело из подписи
    # каждый абзац тела — ровно в одном сообщении (нет потерь и дублей)
    for b in YAB_POST.split("\n\n")[1:]:
        if b.startswith("Вывод:"):
            assert "🌿 Вывод:" in full
            assert b.split(":", 1)[1].strip() in full
        else:
            assert (b in cap) != (b in full), b
    # источник ровно один раз — в конце последнего сообщения
    assert full.count("Источник: " + YAB_URL) == 1
    assert "…" not in full and "…" not in cap
    assert len(seen["full"]) <= 4090
    # пост длиннее лимита подписи — поэтому именно два сообщения
    assert len(postformat.to_telegram_html(postformat.format_post(
        YAB_POST, keep_headline_emoji=True, agro_style=True))) > telegram.CAPTION_LIMIT


def test_completeness_gate_checks_article_sections():
    """Гейт секций статьи (H2/H3 в тексте): пост, отражающий только
    вступление (1/4 секций), неполон; пост с основными рекомендациями
    проходит обе проверки полноты."""
    secs = ("Почему листопад задержался", "Нужно ли обрывать листья",
            "Что сделать перед зимой", "Что проверить весной")
    bodies = (
        "Долгая тёплая осень держит дерево в активном состоянии, и листья "
        "держатся до заморозков.",
        "Вручную не нужно: почки под листвой защищены от морозов, а листопад "
        "не остановить.",
        "Уберите листву из приствольных кругов и замульчируйте почву "
        "перепревшим компостом слоем 5 см.",
        "После оттепели снимите снег с молодых саженцев и осмотрите ветки, "
        "подопрелые под снегом.")
    text = "\n\n".join([YAB_INTRO] +
                       ["%s: %s" % (s, b) for s, b in zip(secs, bodies)])
    html = "<html><body><article>%s</article></body></html>" % "".join(
        "<h2>%s</h2><p>%s</p>" % (s, b) for s, b in zip(secs, bodies))
    intro_only = YAB_TITLE + "\n\n" + YAB_INTRO
    errs = agro._completeness_errors(intro_only, text, html)
    assert any("sections" in e for e in errs), errs      # 1/4 секций
    assert any("words from article mid" in e for e in errs), errs
    complete = YAB_TITLE + "\n\n" + YAB_INTRO + "\n\n" + \
        "\n\n".join("%s: %s" % (s, b) for s, b in zip(secs, bodies))
    assert agro._completeness_errors(complete, text, html) == []


# ---------- регрессия msg82/83 (aif «Что посадить на даче до первого снега») --

AIF_URL = ("https://aif.ru/dacha/ogorod/chto-posadit-na-dache-"
           "do-pervogo-snega")
AIF_TITLE = "Что посадить на даче до первого снега?"
# дословное вступление реально опубликованного поста msg82/83
AIF_MODEL_INTRO = ("Осенью можно вырастить ранние овощи, которые порадуют "
                   "урожаем уже весной. Агроном Людмила Воинкова советует "
                   "обратить внимание на лук, морковь и чеснок.")
# первая половина статьи: вступление источника (для дефектного «только
# вступление» оно должно быть в первой половине текста)
AIF_INTRO = (AIF_MODEL_INTRO +
             " Ориентир — не календарь, а погода: посадка идёт только в "
             "устоявшуюся холодную почву, иначе семена уйдут в рост и "
             "погибнут от первых морозов. Ниже — сводка основных правил "
             "посадки перед первым снегом.")
# хвост статьи — ведущая часть (о пользе посадки) и те самые рекомендации,
# которых не хватало в коротком посте (во второй половине текста)
AIF_TAIL = (
    "Осенняя посадка экономит время весной: всходы появляются сразу после "
    "схода снега, и первый урожай собирают на несколько недель раньше, чем "
    "при посадке весной. Отсюда и главная польза статьи — ранний урожай "
    "овощей и экономия времени садовода.\n\n"
    "Практические рекомендации. Посадочный материал берите сухой, без "
    "следов плесени; норму высева увеличьте на 25-30% — часть семян "
    "всего равно не взойдёт. Ориентируйтесь не на дату, а на температуру "
    "почвы: сажайте, когда на глубине 5-10 см почва остынет до +2...+4°C. "
    "Грядки готовьте за 10-14 дней: земля должна осесть самостоятельно, "
    "а свежие суглинки задерживают ростки.\n\n"
    "Полив после осенней посадки запрещён: влага вымывает семена и "
    "провоцирует гниение. Укрывать посадки тоже не нужно — снег сам "
    "сделает это лучше любого укрывного материала. Зубчик сажают на "
    "глубину 5-10 см, а мелкий севок — на 3-4 см: мельче заглублять "
    "нельзя, иначе луковица не взойдёт.\n\n"
    "Весной останется проредить всходы и снять лишнюю влагу: как только "
    "почва оттает, посадки открывают, рыхлят и подкармливают по "
    "инструкции. Если всходы появились слишком густо, излишки убирают, "
    "оставляя между растениями 3-5 см.")
AIF_TEXT = AIF_INTRO + "\n\n" + AIF_TAIL
AIF_HTML = ARTICLE_HTML % (AIF_TITLE, AIF_TITLE, _today(), AIF_INTRO, AIF_TAIL)

# дефектный пост msg82/83: структура и длина в порядке, но это только
# вступление со ссылкой — рекомендаций и вывода нет
AIF_INTRO_ONLY_POST = AIF_TITLE + "\n\n" + AIF_INTRO
# как модель ответила ФАКТИЧЕСКИ в msg83: заголовок-«пункт» и список,
# склеенный одинарными переносами строки
AIF_AI_BULLET_POST = (
    "• " + AIF_TITLE + "\n\n"
    + AIF_MODEL_INTRO + "\n\n"
    "Главная польза статьи: Получить ранний урожай овощей и сэкономить "
    "время весной.\n\n"
    "Ключевые рекомендации:\n"
    "• Ориентируйтесь не на дату, а на температуру почвы: сажайте, когда на "
    "глубине 5-10 см почва остынет до +2...+4°C.\n"
    "• Увеличьте норму высева на 25-30% — часть семян зимой не взойдёт.\n"
    "• Грядки готовьте за 10-14 дней, а полив после осенней посадки "
    "запрещён: влага вымывает семена.\n\n"
    "Вывод: сажайте лук, морковь и чеснок в устоявшуюся холодную почву "
    "и не поливайте — весной останется проредить всходы."
)


def test_clean_ai_output_heals_bullet_headline_and_merged_list():
    """msg82/83 (очистка вывода): «•» в заголовке снимается, буллеты,
    разделённые одним переносом строки, становятся отдельными абзацами;
    текст советов дословно не переписывается."""
    cleaned = agro._clean_ai_output(AIF_AI_BULLET_POST)
    blocks = [b for b in cleaned.split("\n\n") if b.strip()]
    assert blocks[0] == AIF_TITLE                       # без маркера «•»
    bullets = [b for b in blocks if b.startswith("• ")]
    assert len(bullets) == 3, blocks                    # каждый совет — абзац
    assert "Ключевые рекомендации:\n• " not in cleaned  # склейка разобрана
    assert "• Ориентируйтесь не на дату" in cleaned     # текст не переписан


def test_clean_ai_output_strips_channel_brand():
    """Модель иногда «брендирует» пост: «Сад без хлопот: …». Название
    канала снимается и с заголовка, и со строки-подписи внутри поста —
    ни первый пост, ни продолжение не должны начинаться с названия
    канала (читатель решил бы, что это новая публикация)."""
    raw = ("Сад без хлопот: Что сеют под зиму\n\n"
           "Сад без хлопот:\n\n"
           "Подзимний посев экономит время весной.\n\n"
           "Сад без хлопот: Вывод: проверьте сроки посева.")
    cleaned = agro._clean_ai_output(raw)
    blocks = [b for b in cleaned.split("\n\n") if b.strip()]
    assert blocks[0] == "Что сеют под зиму"            # бренд в заголовке снят
    assert "Сад без хлопот" not in cleaned             # строк-подписей нет
    assert blocks[1] == "Подзимний посев экономит время весной."
    assert blocks[2] == "Вывод: проверьте сроки посева."
    # бренд, обёрнутый в жирные маркеры, снимается при чистке заголовка
    wrapped = agro._clean_ai_output(
        "**Сад без хлопот: Осенняя подкормка**\n\n"
        "Питательные вещества уходят в корни.")
    assert wrapped.split("\n\n")[0] == "Осенняя подкормка"


def test_regression_msg83_intro_only_ai_post_is_reviewed_not_published(
        st, monkeypatch):
    """Регрессия msg82/83: ИИ вернул только вступление со ссылкой (длина
    и структура в порядке, рекомендаций нет) — 1 повтор, затем review с диагностикой
    «incomplete», публикации нет."""
    _fake_network(monkeypatch, {AIF_URL: AIF_HTML})
    _publish_traps(monkeypatch)
    prov = StubProvider(AIF_INTRO_ONLY_POST, AIF_INTRO_ONLY_POST)
    r = agro.process_url(st, AIF_URL, "aif", publish=True,
                         dry_run=False, provider=prov)
    assert r["status"] == "review" and len(prov.calls) == 2, r
    assert r["ai"] == "failed"
    row = st.get(st.add(AIF_URL, "x"))
    assert row["status"] == "review" and not row["post_text"]
    assert "incomplete" in row["reason"], row["reason"]
    assert st.db.execute("SELECT COUNT(*) c FROM publications").fetchone()["c"] == 0


def test_regression_msg83_fallback_and_cache_cannot_bypass_completeness(
        st, monkeypatch):
    """Регрессия msg82/83: запрет публикации «только вступления» не обходится
    ни extractive-фолбэком (провайдер недоступен), ни кэшем post_text при
    повторном прогоне после сбоя."""
    _fake_network(monkeypatch, {AIF_URL: AIF_HTML})
    _publish_traps(monkeypatch)
    # (a) фолбэк: провайдер недоступен -> extractive = вступление -> review
    r1 = agro.process_url(st, AIF_URL, "aif", publish=True,
                          dry_run=False, provider=None)
    assert r1["status"] == "review" and r1["ai"] == "skipped", r1
    assert r1["reason"] == "editorial gate"
    mid = st.add(AIF_URL, "x")
    row = st.get(mid)
    assert row["status"] == "review" and "incomplete" in row["reason"]
    assert not row["post_text"]        # неполный пост НЕ закэширован вовсе
    assert st.db.execute("SELECT COUNT(*) c FROM publications").fetchone()["c"] == 0
    # (b) «отравленный» кэш (строка post_text из прогона до гейта, статус
    # failed): повторная обработка пере-проверяет кэш и НЕ публикует его
    # мимо проверки полноты
    tags_line = " ".join("#" + t for t in sorted(agro.AGRO_ALLOWED_TAGS)[:3])
    poisoned = (AIF_INTRO_ONLY_POST + "\n\nИсточник: " + AIF_URL +
                "\n" + tags_line)
    st.update(mid, status="failed", reason="image fetch: 403",
              post_text=poisoned)
    prov = StubProvider()      # любой вызов ИИ здесь = AssertionError
    r2 = agro.process_url(st, AIF_URL, "aif", publish=True,
                          dry_run=False, provider=prov)
    assert r2["status"] == "review", r2
    assert len(prov.calls) == 0            # кэш не пересобирался ИИ
    assert st.get(mid)["status"] == "review"
    assert "incomplete" in st.get(mid)["reason"]
    assert st.db.execute("SELECT COUNT(*) c FROM publications").fetchone()["c"] == 0


def test_regression_msg83_bullet_format_publish_and_no_duplicate_rerun(
        st, monkeypatch):
    """Регрессия msg82/83 (формат+дедуп): пост модели с заголовком-«пунктом»
    и склеенными буллетами публикуется ОДНИМ сообщением — фото с полным
    текстом в подписи (чистый заголовок, отдельные абзацы советов, вывод,
    источник, хэштеги); второго сообщения нет; повторный запуск не создаёт
    повторную публикацию."""
    _fake_network(monkeypatch, {AIF_URL: AIF_HTML})
    _publish_traps(monkeypatch)
    seen, sent = {}, []

    def spy_photo(token, chat_id, photo_url=None, photo_bytes=None,
                  caption=None, dry_run=False, retries=2, parse_mode=None):
        seen["caption"] = caption
        sent.append("photo")
        return telegram.PublishResult(True, message_id=820)

    def boom_msg(*a, **k):
        raise AssertionError("короткий пост должен уйти одним сообщением")
    monkeypatch.setattr(telegram, "send_photo", spy_photo)
    monkeypatch.setattr(telegram, "send_message", boom_msg)

    prov = StubProvider(AIF_AI_BULLET_POST)
    r1 = agro.process_url(st, AIF_URL, "aif", publish=True,
                          dry_run=False, provider=prov)
    assert r1["status"] == "published" and r1["ai"] == "edited", r1

    cap = postformat.unescape_telegram_html(seen["caption"])
    assert len(seen["caption"]) <= telegram.CAPTION_LIMIT
    cb = [b for b in cap.split("\n\n") if b.strip()]
    assert cb[0] == AIF_TITLE                           # заголовок без «•»
    assert "<b>%s</b>" % AIF_TITLE in seen["caption"]  # и жирным в HTML
    assert "**" not in seen["caption"]                  # маркеры не публикуются
    assert sum(1 for b in cb if b.startswith("• ")) == 3, cb  # советы по абзацам
    assert "Ключевые рекомендации:\n• " not in cap      # склейки нет
    assert "Вывод:" in cap and "проредить всходы" in cap
    assert AIF_MODEL_INTRO in cap                       # вступление в подписи
    assert "Источник: " + AIF_URL in cap
    assert " ".join(r1["hashtags"]) in cap

    # идемпотентность: повторная обработка опубликованной статьи не публикует дубль
    r2 = agro.process_url(st, AIF_URL, "aif", publish=True,
                          dry_run=False, provider=prov)
    assert r2["status"] == "skipped" and "already" in r2["reason"], r2
    assert len(prov.calls) == 1                        # редактура не повторилась
    assert sent == ["photo"]                           # ровно одна отправка
    assert st.db.execute("SELECT COUNT(*) c FROM publications").fetchone()["c"] == 1


# ---------- регрессия msg86/87 (ботаничка «Побелка стволов») ---------------

POB_URL = ("https://www.botanichka.ru/article/osennyuyu-pobelku-smylo-"
           "dozhdyom-povtoryat-sejchas-ili-zhdat-vesny/")
POB_TITLE = "Побелка стволов: когда повторять после дождя"
# вступление — дословный фрагмент реально опубликованного поста msg86/87
POB_INTRO = ("После дождей побелка стволов часто смывается, и садоводы "
             "задаются вопросом: стоит ли повторять процедуру сразу или "
             "лучше подождать до весны? Вот рекомендации, как действовать "
             "правильно. Чаще всего побелку смывают проливные дожди поздней "
             "осенью, когда работа уже сделана.")
POB_TAIL = (
    "Повторная побелка нужна не всегда: слой защищает кору от солнечных "
    "ожогов и морозобоин зимой, и если он сохранился, дерево в безопасности. "
    "Оцените состояние коры после полного высыхания ствола: светлая "
    "сохранившаяся побелка означает, что повторять процедуру сейчас не "
    "нужно, а небольшие тёмные пятна можно точечно подправить.\n\n"
    "Осмотрите ствол на предмет повреждений — южную сторону, основания "
    "ветвей, развилки и места, открытые солнцу: именно там чаще всего "
    "появляются морозобоины и ожоги. Повторяйте побелку только на сухой "
    "коре, после полного высыхания предыдущего слоя; не наносите состав на "
    "мокрую или промёрзшую кору — он не сцепится и смоется ближайшим дождём.\n\n"
    "Используйте подходящую побелку или краску, предназначенную для "
    "штамбов деревьев: в составе должны быть известь или мел с вяжущим "
    "компонентом. Не добавляйте в готовые смеси медный купорос, клей и "
    "мыло без инструкции производителя — концентрация может обжечь кору. "
    "Для молодых деревьев используйте более мягкий состав с мелом вместо "
    "извести: тонкая кора саженцев чувствительна к агрессивному составу.\n\n"
    "Если после дождей кора долго не просыхает, используйте светлую "
    "обвязку или экран, чтобы защитить ствол от солнца в морозную погоду. "
    "Побелку повторяют обычно 1-2 раза в год, а при быстром смывании — "
    "по состоянию коры, ориентируясь на погоду, а не на календарь.")
POB_TEXT = POB_INTRO + "\n\n" + POB_TAIL
POB_HTML = ARTICLE_HTML % (POB_TITLE, POB_TITLE, _today(), POB_INTRO, POB_TAIL)

# пост как в msg87: длиннее лимита подписи -> фото + продолжение
POB_POST = (
    POB_TITLE + "\n\n"
    + POB_INTRO + "\n\n"
    "• Оцените состояние коры после высыхания: если слой побелки сохранился "
    "и кора светлая, повторная побелка не требуется; небольшие тёмные пятна "
    "можно точечно подправить.\n\n"
    "• Осмотрите ствол на предмет повреждений: южную сторону, основания "
    "ветвей, развилки и места, открытые солнцу.\n\n"
    "• Повторяйте побелку только на сухой коре, после полного высыхания "
    "предыдущего слоя; не наносите состав на мокрую или промёрзшую кору.\n\n"
    "• Используйте подходящую побелку для штамбов деревьев и не добавляйте "
    "в готовые смеси медный купорос, клей и мыло без инструкции "
    "производителя.\n\n"
    "• Для молодых деревьев используйте более мягкий состав с мелом вместо "
    "извести.\n\n"
    "• Если после дождей кора не просыхает, используйте светлую обвязку "
    "или экран, чтобы защитить ствол от солнца.\n\n"
    "Вывод: не спешите с повторной побелкой после дождя — дождитесь "
    "высыхания коры и подходящей погоды, а состав выбирайте по состоянию "
    "дерева."
)


def test_regression_pobelka_long_post_is_photo_plus_continuation(st, monkeypatch):
    """Регрессия msg86/87 («Побелка стволов…» — пост длиннее лимита подписи):
    публикация остаётся парой «фото + продолжение», подпись при этом
    МАКСИМАЛЬНО полная (заголовок, вступление и целые советы), а второе
    сообщение оформлено как продолжение — БЕЗ повторного заголовка,
    вступления и дублей; все советы и вывод на месте."""
    _fake_network(monkeypatch, {POB_URL: POB_HTML})
    _publish_traps(monkeypatch)
    seen, sent = {}, []

    def spy_photo(token, chat_id, photo_url=None, photo_bytes=None,
                  caption=None, dry_run=False, retries=2, parse_mode=None):
        seen["caption"] = caption
        sent.append("photo")
        return telegram.PublishResult(True, message_id=860)

    def spy_msg(token, chat_id, text, dry_run=False, parse_mode=None, retries=2):
        seen["full"] = text
        sent.append("text")
        return telegram.PublishResult(True, message_id=861)
    monkeypatch.setattr(telegram, "send_photo", spy_photo)
    monkeypatch.setattr(telegram, "send_message", spy_msg)

    prov = StubProvider(POB_POST)
    r = agro.process_url(st, POB_URL, "botanichka", publish=True,
                         dry_run=False, provider=prov)
    assert r["status"] == "published" and r["ai"] == "edited", r
    assert sent == ["photo", "text"]                   # фото раньше продолжения

    cap = postformat.unescape_telegram_html(seen["caption"])
    full = postformat.unescape_telegram_html(seen["full"])
    cap_blocks = [b for b in cap.split("\n\n") if b.strip()]
    # подпись МАКСИМАЛЬНО полная: заголовок + вступление + целые советы
    assert cap_blocks[0] == POB_TITLE                  # текст заголовка цел
    # заголовок и «Вывод» жирными, содержание вывода курсивом в HTML
    assert "<b>%s</b>" % POB_TITLE in seen["caption"]
    assert "<b>🌿 Вывод:</b> <i>" in seen["full"]
    assert "**" not in seen["caption"] and "**" not in seen["full"]
    assert "После дождей побелка" in cap_blocks[1]      # вступление в подписи
    assert "Оцените состояние коры" in cap              # советы уже в подписи
    # подпись заканчивается целым абзацем тела (разрез только по блокам)
    assert re.search(r"[.!?…]$", cap_blocks[-1])
    # источник — ровно один раз: в подписи ДЛИННОГО поста его нет
    assert "Источник: " + POB_URL not in cap
    assert "Сад без хлопот" not in cap                  # название канала
    assert not re.search(r"#[А-Яа-яA-Za-z]", cap)      # тегов в подписи нет
    assert len(seen["caption"]) <= telegram.CAPTION_LIMIT
    assert len(seen["caption"]) > 700                  # подпись заполнена, а не «короткая»
    # продолжение: пометка + остаток советов и вывод, БЕЗ заголовка/дублей
    assert full.startswith("Продолжение\n\n")  # читателю ясно: та же публикация
    assert POB_TITLE not in full                       # заголовок не дублируется
    assert "Сад без хлопот" not in full                # и название канала
    assert "После дождей побелка" not in full
    fb = [b for b in full.split("\n\n") if b.strip()]
    assert "Вывод:" in fb[-3] and "высыхания коры" in fb[-3]
    # источник ровно один раз — в конце последнего сообщения
    assert full.count("Источник: " + POB_URL) == 1
    # каждый совет и вывод — ровно в одном сообщении (нет потерь и дублей)
    for b in POB_POST.split("\n\n")[2:]:
        if b.startswith("Вывод:"):
            assert "🌿 Вывод:" in full
            assert b.split(":", 1)[1].strip() in full
        else:
            assert (b in cap) != (b in full), b
    assert "…" not in full and "…" not in cap
    assert len(seen["full"]) <= 4090
    # пост действительно длиннее лимита подписи -> именно два сообщения
    assert len(postformat.to_markdownv2(
        postformat.format_post(POB_POST))) > telegram.CAPTION_LIMIT


def test_text_send_failure_after_photo_goes_to_review_without_repost(
        st, monkeypatch):
    """Ошибка отправки второго шага (фото ушло, текст не отправился):
    publish_post возвращает отказ -> review без авто-повтора (фото не
    задублируется), публикация не записывается; повторный запуск не
    создаёт новых сообщений и не вызывает ИИ заново."""
    _fake_network(monkeypatch, {YAB_URL: YAB_HTML})
    monkeypatch.setattr(config, "AGRO_PUBLISH", True, raising=False)
    monkeypatch.setattr(config, "AGRO_BOT_TOKEN", "t", raising=False)
    monkeypatch.setattr(config, "AGRO_CHAT_ID", "-100AGRO", raising=False)
    monkeypatch.setattr(agro.httpclient, "fetch_bytes",
                        lambda url, **kw: b"\xff\xd8" + b"x" * 20000)
    sent = []

    def spy_photo(token, chat_id, photo_url=None, photo_bytes=None,
                  caption=None, dry_run=False, retries=2, parse_mode=None):
        sent.append("photo")
        return telegram.PublishResult(True, message_id=830)
    monkeypatch.setattr(telegram, "send_photo", spy_photo)

    def fail_msg(*a, **k):
        sent.append("text")
        return telegram.PublishResult(False, error="400 Bad Request: "
                                                   "message is too long")
    monkeypatch.setattr(telegram, "send_message", fail_msg)

    prov = StubProvider(YAB_POST)
    r1 = agro.process_url(st, YAB_URL, "botanichka", publish=True,
                          dry_run=False, provider=prov)
    assert r1["status"] == "review" and "publish failed" in r1["reason"], r1
    assert sent == ["photo", "text"]                   # по одной попытке на шаг
    assert st.db.execute("SELECT COUNT(*) c FROM publications").fetchone()["c"] == 0
    # повторный запуск: review — терминальный статус, новых отправок нет
    r2 = agro.process_url(st, YAB_URL, "botanichka", publish=True,
                          dry_run=False, provider=prov)
    assert r2["status"] == "skipped" and "already" in r2["reason"], r2
    assert len(prov.calls) == 1                        # ИИ не перезапускался
    assert sent == ["photo", "text"]                   # дублей нет


def test_unsplittable_post_goes_to_review_without_sending(st, monkeypatch):
    """Пост, который нельзя разделить без потерь (ни один абзац тела не
    влезает в подпись к фото): publish_post честно отказывает ДО отправки —
    send_photo/send_message не вызываются, фото не дублируется, статья не
    обрезается; материал уходит в review, повторный запуск ничего не
    отправляет заново."""
    _fake_network(monkeypatch, {YAB_URL: YAB_HTML})
    _publish_traps(monkeypatch)
    sent = []

    def spy_photo(*a, **k):
        sent.append("photo")
        return telegram.PublishResult(True, message_id=950)

    def spy_msg(*a, **k):
        sent.append("text")
        return telegram.PublishResult(True, message_id=951)
    monkeypatch.setattr(telegram, "send_photo", spy_photo)
    monkeypatch.setattr(telegram, "send_message", spy_msg)

    # вступление раздуто так, что один абзац тела уже не влезает в подпись
    intro = YAB_POST.split("\n\n")[1]
    huge_intro = intro + " " + "Подробности осеннего ухода за садом. " * 25
    prov = StubProvider(YAB_POST.replace(intro, huge_intro))
    r = agro.process_url(st, YAB_URL, "botanichka", publish=True,
                         dry_run=False, provider=prov)
    assert r["status"] == "review" and "publish failed" in r["reason"], r
    assert "cannot be split" in r["reason"]             # причина диагностирована
    assert sent == []                    # фото и текст НЕ отправлялись
    assert st.db.execute("SELECT COUNT(*) c FROM publications").fetchone()["c"] == 0
    # повторный запуск: review — терминальный статус, новых отправок нет
    r2 = agro.process_url(st, YAB_URL, "botanichka", publish=True,
                          dry_run=False, provider=prov)
    assert r2["status"] == "skipped" and "already" in r2["reason"], r2
    assert sent == []                                       # дублей нет


# ---------- регрессия msg92/93 (ботаничка «Эпипремнум», run 38175958881) ----

EP_URL = ("https://www.botanichka.ru/article/epipremnum-vytyanulsya-"
          "i-melchaet-obrezat-li-ego-osenyu/")
EP_TITLE = "Эпипремнум вытянулся и мельчает: как спасти растение осенью"
# вступление — дословно из подписи msg92
EP_INTRO = ("Эпипремнум (золотой потос) часто теряет пышность и "
            "привлекательность осенью. Чтобы понять, как помочь растению, "
            "важно разобраться в причинах вытягивания и мельчания листьев.")
# тело — дословно из сообщения msg93 (советы, разделители-вопросы, вывод)
EP_BODY = """• Осмотрите плеть целиком: сравните длину междоузлий и размер листьев на разных участках.

• Проверьте, хватает ли растению света: даже в светлой комнате листья могут получать недостаточно света.

• Подкармливать вытянувшийся эпипремнум не нужно, пока не исправите условия освещения.

• Если стебель оголился, обрезка не поможет: новые побеги появятся только при достаточном освещении.

• При нехватке света новые листья становятся мелкими и зеленеют, теряя пестроту.

Если растение вытянулось, но продолжает расти:

• Укороченные побеги можно укоротить сейчас, но обязательно переставьте горшок ближе к свету или добавьте досветку.

• Для пышности у основания можно подсадить укоренённые черенки.

Если рост почти остановился:

• Переставьте горшок в более светлое место и поливайте реже.

• Если растение стоит у холодного окна или в прохладе, причина может быть в температуре.

Если листья массово желтеют, стебли вялые, грунт долго остаётся мокрым:

• Проверьте корни на наличие гнили и, при необходимости, укорените верхушки как черенки.

Как правильно обрезать плеть:

• Срезайте стебель над узлом, оставляя несколько здоровых листьев.

• Черенки укореняйте в воде или влажном грунте, не торопите корни.

Оценивайте результат по новым листьям, появившимся после изменения условий. Если рост не восстановился, проверьте полив и состояние корней."""
EP_POST = (EP_TITLE + "\n\n" + EP_INTRO + "\n\n" + EP_BODY + "\n\n"
           "Источник: " + EP_URL + "\n#Практика #Растения #Погода #Ботаничка")


def test_regression_msg92_93_epipremnum_long_post_format():
    """Регрессия msg92/93 («Эпипремнум…», публикация run 38175958881 на
    f239d6f): пост экранированно длиннее лимита подписи — пара сообщений
    обязательна по Bot API. Формат: подпись заполняется целыми блоками
    (заголовок, вступление, первые советы); второе сообщение начинается
    с пометки «Продолжение» — читателю ясно, что это та же публикация;
    без повторного заголовка и вступления, без потерь и дублей; источник
    — ровно один раз, в конце продолжения."""
    formatted = postformat.format_post(EP_POST)
    md = postformat.to_markdownv2(formatted)
    assert len(md) > telegram.CAPTION_LIMIT   # в подпись не влезает — пара
    assert len(md) <= 4090                    # в текстовое сообщение влезает
    cap, msg = postformat.split_for_photo(
        formatted, caption_limit=telegram.CAPTION_LIMIT,
        message_limit=telegram.MESSAGE_SAFE_LIMIT)
    cap_esc = postformat.to_markdownv2(cap)
    assert len(cap_esc) <= telegram.CAPTION_LIMIT
    assert len(cap_esc) > 800                 # подпись заполнена целыми блоками
    assert "…" not in cap                     # обрезка — по границам, не словом
    # подпись: заголовок, вступление, первые советы — БЕЗ источника и тегов
    cb = [b for b in cap.split("\n\n") if b.strip()]
    assert cb[0] == "**%s**" % EP_TITLE
    assert EP_INTRO in cap
    assert "Осмотрите плеть целиком" in cap
    assert "Источник: " + EP_URL not in cap   # источник — один раз, в конце
    assert "#Практика" not in cap
    # продолжение: пометка + остаток тела, без заголовка и вступления
    assert msg.startswith("Продолжение\n\n")
    mb = [b for b in msg.split("\n\n") if b.strip()]
    assert mb[0] == "Продолжение"
    assert "**%s**" % EP_TITLE not in msg
    assert EP_INTRO not in msg
    assert "Как правильно обрезать плеть:" in msg   # поздние разделы
    assert "Черенки укореняйте" in msg              # последний совет
    assert msg.count("Источник: " + EP_URL) == 1    # ровно один раз, в конце
    assert msg.endswith("Источник: " + EP_URL + "\n\n#Практика #Растения "
                       "#Погода #Ботаничка")
    assert "#Практика" in msg
    assert len(postformat.to_markdownv2(
        msg)) <= telegram.MESSAGE_SAFE_LIMIT        # продолжение в лимите
    # текст не теряется и не дублируется: каждый блок тела — ровно в одном
    # месте; разрезов посередине блока нет вообще
    partial = 0
    for b in formatted.split("\n\n")[1:]:
        if b.startswith("Источник:") or b.startswith("#"):
            continue
        in_cap, in_msg = b in cap, b in msg
        assert not (in_cap and in_msg), "дубль блока: %s" % b[:60]
        if not in_cap and not in_msg:
            partial += 1
    assert partial == 0                       # только целые блоки, без разрезов


# ---------- Стиль: акценты, курсив, эмодзи-буллеты, анти-повтор ----------

# эталон стилевого ответа «модели»: цепляющий заголовок с эмодзи, короткие
# абзацы, эмодзи-буллеты, **акцент**, _курсивная_ ремарка, вывод, один призыв
STYLE_POST = (
    "\U0001F33F Озимый чеснок: главные ошибки посадки\n"
    "\n"
    "Осенью спешат все. Разберёмся, **когда сажать чеснок**, чтобы луковицы "
    "не вымерзли и не выпрели.\n"
    "\n"
    "\U0001F342 Посадите за 35-45 дней до устойчивых заморозков — за это "
    "время корни успевают отрасти, а стрелка нет.\n"
    "\n"
    "\U0001F331 Заглубляйте зубок на 10-12 см (без мульчи): _на песчаной "
    "почве_ глубину уменьшайте.\n"
    "\n"
    "Вывод: проверьте сроки своего региона и не жалейте перегной.\n"
    "\n"
    "Какой чеснок сажаете вы — озимый или яровой? Напишите в комментариях!"
)


def test_style_post_accents_and_italic_reach_telegram(st, monkeypatch):
    """Стиль канала: **акценты** и _курсивные_ ремарки модели доходят до
    Telegram жирным/курсивом (MarkdownV2 — одинарные * и _); служебные **/__
    в опубликованном тексте не появляются, текст вокруг акцентов цел."""
    _fake_network(monkeypatch, {ART_URL: _art_html()})
    prov = StubProvider(STYLE_POST)
    r = agro.process_url(st, ART_URL, "botanichka", dry_run=True, provider=prov)
    assert r["status"] == "post_ready" and r["ai"] == "edited", r
    body = st.get(st.add(ART_URL, "botanichka"))["post_text"]
    assert "**когда сажать чеснок**" in body       # промежуточный формат
    assert "_на песчаной почве_" in body
    md = postformat.to_markdownv2(postformat.format_post(
        body, keep_headline_emoji=True))
    assert "*когда сажать чеснок*" in md           # жирное — одинарные *
    assert "_на песчаной почве_" in md             # курсив — одинарные _
    assert "**" not in md and "__" not in md
    plain = postformat.unescape_markdownv2(md)
    assert "Разберёмся, когда сажать чеснок, чтобы луковицы" in plain
    assert "10-12 см (без мульчи): на песчаной почве глубину" in plain


def test_publish_style_post_single_photo_accurate(st, monkeypatch):
    """Публикация стилевого поста одним сообщением: подпись HTML с
    жирным эмодзи-заголовком, акцентом и курсивом; без **/__; источник и
    теги целы; второе сообщение не отправляется."""
    _fake_network(monkeypatch, {ART_URL: _art_html()})
    _publish_traps(monkeypatch)
    seen = {}

    def spy_photo(token, chat_id, photo_url=None, photo_bytes=None,
                  caption=None, dry_run=False, retries=2, parse_mode=None):
        seen.update(caption=caption, photo=photo_bytes, cap_mode=parse_mode)
        return telegram.PublishResult(True, message_id=555)

    def boom_msg(*a, **k):
        raise AssertionError("пост в пределах подписи — одно сообщение")
    monkeypatch.setattr(telegram, "send_photo", spy_photo)
    monkeypatch.setattr(telegram, "send_message", boom_msg)

    prov = StubProvider(STYLE_POST)
    r = agro.process_url(st, ART_URL, "botanichka", publish=True,
                         dry_run=False, provider=prov)
    assert r["status"] == "published" and r["telegram_message_id"] == 555, r
    html = seen["caption"]
    assert seen["cap_mode"] == "HTML"
    assert len(html) <= telegram.CAPTION_LIMIT
    # заголовок жирным, ведущий эмодзи — часть заголовка (agro-стиль)
    assert "<b>\U0001F33F Озимый чеснок: главные ошибки посадки</b>" in html
    assert "<b>когда сажать чеснок</b>" in html
    assert "<i>на песчаной почве</i>" in html
    assert "**" not in html and "__" not in html     # служебных маркеров нет
    plain = postformat.unescape_telegram_html(html)
    assert plain.split("\n\n")[0] == "\U0001F33F Озимый чеснок: главные " \
                                      "ошибки посадки"
    assert "Источник: " + ART_URL in plain
    assert "ПОСЛЕДНИЕ ПУБЛИКАЦИИ" not in html      # метаданные не публикуются


def test_style_history_rotation_prompt_and_no_metadata_in_post(st, monkeypatch):
    """Анти-повтор: тип хука/заголовок/эмодзи последних публикаций берутся из
    СУЩЕСТВУЮЩЕГО post_text БД канала и уходят ТОЛЬКО в промпт (инструкция
    ротации + перечень); в опубликованный текст история и служебные
    метаданные не попадают."""
    _fake_network(monkeypatch, {ART_URL: _art_html()})
    mid = st.add(ART_URL + "/prev", "botanichka")
    st.update(mid, status="published",
              post_text="❓ Почему желтеют листья у огурцов \U0001F33F\n\n"
                        "Текст прошлого поста.\n\n"
                        "Источник: https://example.com/prev\n#Практика")
    prov = StubProvider(AI_POST)
    r = agro.process_url(st, ART_URL, "botanichka", dry_run=True, provider=prov)
    assert r["status"] == "post_ready" and r["ai"] == "edited", r
    hist = agro._style_history(st)
    assert hist and hist[0]["hook"] == "вопрос"     # ❓ Почему… -> «вопрос»
    assert hist[0]["emoji"]                         # ключевые эмодзи извлечены
    user = _user_msg(prov)
    assert "ПОСЛЕДНИЕ ПУБЛИКАЦИИ" in user
    assert "Почему желтеют листья у огурцов" in user
    assert "[вопрос]" in user
    assert "должен отличаться от предыдущего" in user
    sys_msg = prov.calls[0][0]["content"]
    assert "не начинай пост тем же типом" in sys_msg
    # служебные метаданные и история — не в публикацию
    post = st.get(st.add(ART_URL, "botanichka"))["post_text"]
    assert "ПОСЛЕДНИЕ ПУБЛИКАЦИИ" not in post
    assert "[вопрос]" not in post
    assert "Почему желтеют" not in post


def test_style_history_unavailable_pipeline_still_works(st, monkeypatch):
    """История анти-повтора недоступна (ошибка хранилища) -> []: редактор
    продолжает работать без истории, промпт — без блока публикаций,
    процесс не падает."""
    _fake_network(monkeypatch, {ART_URL: _art_html()})

    class BoomDB:
        def execute(self, *a, **k):
            raise RuntimeError("db gone")

    class BoomSt:
        db = BoomDB()
    assert agro._style_history(BoomSt()) == []   # ошибка хранилища гасится
    prov = StubProvider(AI_POST)
    r = agro.process_url(st, ART_URL, "botanichka", dry_run=True, provider=prov)
    assert r["status"] == "post_ready" and r["ai"] == "edited", r
    assert "ПОСЛЕДНИЕ ПУБЛИКАЦИИ" not in _user_msg(prov)


def test_emoji_bullets_glued_with_single_newline_split_into_paragraphs():
    """Дефект msg83 в новом стиле: пункты с эмодзи-буллетами, склеенные
    одним переносом строки, разбиваются на отдельные абзацы (в подписи —
    пустые строки между пунктами, а не стена текста)."""
    raw = ("Заголовок поста\n\nВступление сезона.\n"
           "\U0001F33F Первый совет: уберите остатки.\n"
           "\U0001F331 Второй совет: внесите компост.\n"
           "\U0001F342 Третий совет: замульчируйте грядки.\n\n"
           "Вывод: делайте всё вовремя.")
    out = agro._clean_ai_output(raw)
    blocks = [b for b in out.split("\n\n") if b.strip()]
    assert len(blocks) == 6
    assert blocks[2] == "\U0001F33F Первый совет: уберите остатки."
    assert blocks[3] == "\U0001F331 Второй совет: внесите компост."
    assert blocks[4] == "\U0001F342 Третий совет: замульчируйте грядки."
    assert blocks[5] == "Вывод: делайте всё вовремя."


def test_style_history_hook_types_rotate_labels():
    """Метаданные ротации: тип хука определяется по заголовку (включая
    ведущие эмодзи/знаки); достаточно развести типы между публикациями."""
    cases = {
        "Почему желтеют листья у огурцов?": "вопрос",
        "\U0001F6A8 5 ошибок посадки чеснока": "ошибка/миф",
        "\U0001F33F 3 схемы посадки лука": "список/числа",
        "Как сохранить урожай яблок до весны": "вопрос",
        "Чеснок под зиму: сроки в сентябре": "сезон",
        "Оказывается, зола не всем культурам помогает": "факт",
        "Нейтральный заголовок про грядки": "польза",
    }
    for head, want in cases.items():
        assert agro._hook_type(head) == want, head


# ---------- регрессия отказов ИИ-редактуры 13.10.2026 (supersadovnik) ------
# Фактический запуск 17:03 UTC: checked=53, post_ready=0, ai_edited=1,
# ai_failed=2; отказы «covers 3/7», «covers 2/6» (обе попытки), «covers 1/4»,
# «enumerated items instead of paragraphs». Реальные материалы: «Коза в ЛПХ»
# (6 секций), «Обзор 14 сортов тюльпанов» (секции-имена на латинице),
# «Пиявки дома» (однословные секции). Ниже — их структура и репрезентативные
# ответы модели (нумерация-перечень, потеря разделов).

KOZA_URL = ("https://www.supersadovnik.ru/text/koza-v-lph-kak-pravilno-"
            "soderzhat-i-s-chego-nachat-novichku-1014747")
KOZA_TITLE = "Коза в ЛПХ: как правильно содержать и с чего начать новичку"
KOZA_INTRO = ("Коза — неприхотливое животное, но и к ней нужны грамотный уход "
              "и продуманная организация хозяйства. Прежде чем заводить "
              "козочку, решите, ради чего она нужна: молоко, мясо или пух — "
              "от ответа зависит выбор породы.")
KOZA_SECS = ("Козоводство", "Состояние в России", "Молочные породы коз",
             "Мясные породы коз", "Отечественные породы пуховых коз",
             "Что выгоднее для ЛПХ?")
KOZA_BODIES = (
    "Козоводство в личном подсобном хозяйстве выгодно тем, что коза быстро "
    "привыкает к человеку и неприхотлива к кормам. Помещение нужно сухое, с "
    "подстилкой и вентиляцией.",
    "Состояние отрасли в России оценивают как стабильное: поголовье в "
    "личных хозяйствах держится на уровне последних лет, а спрос на козье "
    "молоко растёт.",
    "Молочные породы коз — зааненская, чешская бурая, русская — дают до "
    "6-8 литров молока в сутки в период лактации и нуждаются в доении "
    "дважды в день.",
    "Мясные породы коз — бурская, камарунская — набирают убойный вес за "
    "сезон на хороших пастбищах, но кормов требуют больше молочных.",
    "Отечественные породы пуховых коз дают пух и шерсть для пряжи и зимуют "
    "в условиях средней полосы без утеплённых капителей.",
    "Что выгоднее для ЛПХ? Молочное направление: спрос на молоко стабильный "
    "круглый год, а цена козьего молока выше коровьего.",
)
KOZA_TEXT = KOZA_INTRO + "\n\n" + "\n\n".join(
    "%s: %s" % (s, b) for s, b in zip(KOZA_SECS, KOZA_BODIES))
KOZA_HTML = (
    "<html><head><title>%s</title>"
    "<meta property=\"og:image\" content=\"https://cdn.example.test/agro/koza.jpg\">"
    "<script type=\"application/ld+json\">"
    "{\"@type\":\"Article\",\"headline\":\"%s\",\"datePublished\":\"%s\"}"
    "</script></head><body><article><p>%s</p>%s</article></body></html>"
) % (KOZA_TITLE, KOZA_TITLE, _today(), KOZA_INTRO,
     "".join("<h2>%s</h2><p>%s</p>" % (s, b)
             for s, b in zip(KOZA_SECS, KOZA_BODIES)))

# дефектный ответ модели (реальная форма): нумерованные пункты и markdown-списки
KOZA_NUMBERED_POST = (
    KOZA_TITLE + "\n\n"
    "Если вы задумались о разведении коз, это отличный выбор для личного "
    "подсобного хозяйства. Разберёмся, с чего начать.\n\n"
    "Какие направления козоводства выбрать?\n\n"
    "1. Молочное направление: стабильный спрос на молоко.\n"
    "2. Мясное направление: быстрый рост молодняка на пастбище.\n"
    "3. Пуховое направление: узкий рынок сбыта волокна.\n\n"
    "Какие породы выбрать?\n\n"
    "- Русская белая: неприхотлива и морозостойка.\n"
    "- Зааненская: рекордные надои, но чувствительна к сырости.\n"
    "- Бурская: быстрорастущие мясные козы.\n\n"
    "Вывод: начните с молочного направления и выберите породу под свои "
    "условия."
)

# полноценный краткий пересказ: плоские абзацы, 5 из 6 разделов
KOZA_GOOD_POST = (
    KOZA_TITLE + "\n\n"
    "\U0001F410 Коза в подсобном хозяйстве — это и молоко, и пух, и мясо: "
    "козоводство начинают с выбора направления.\n\n"
    "\U0001F95B К молочным породам относят зааненскую и чешскую бурую: от "
    "них получают стабильные надои каждый день.\n\n"
    "\U0001F356 Мясные породы быстро набирают вес за сезон и дают мясо, но "
    "кормов требуют больше.\n\n"
    "\U0001F9F6 Отечественные породы пуховых коз зимуют в условиях средней "
    "полосы и дают пух для пряжи.\n\n"
    "\U0001F4A1 Вывод: новичку выгоднее начать с молочного направления — "
    "спрос на молоко стабильный, а уход простой."
)

# пост, потерявший 4 раздела из 6 (отпечаток «covers 2/6» запуска 13.10)
KOZA_PARTIAL_POST = (
    KOZA_TITLE + "\n\n"
    "\U0001F410 Козы в подсобном хозяйстве дают молоко и пух: спрос на "
    "продукты держится круглый год.\n\n"
    "\U0001F95B Молочные породы коз — зааненская и чешская бурая — дают "
    "обильные надои и стабильное молоко.\n\n"
    "\U0001F356 Мясные породы коз — бурская и камарунская — набирают вес "
    "за сезон на хороших пастбищах.\n\n"
    "\U0001F4A1 Вывод: выбирайте породу под задачу и не гонитесь за "
    "количеством."
)

# реальный обзор сортов тюльпанов: секции = имена сортов (латиница)
TULIP_URL = ("https://www.supersadovnik.ru/text/obzor-14-luchshih-novyh-"
             "sortov-tjulpanov-na-vesnu-2027-darvinovy-i-drugie-novinki-1014750")
TULIP_TITLE = "Обзор 14 лучших новых сортов тюльпанов на весну 2027"
TULIP_INTRO = ("Весна близко, и садовники уже планируют посадки: в этом "
               "сезоне особенно интересны новые сорта тюльпанов.")
TULIP_SECS = ("Топ-14 новых интересных сортов тюльпанов",
              "2 Beauty of Leo (новинка, предположительно 2025-2026, Нидерланды)",
              "Pride mix", "12 Menton Oranje (новинка)")
TULIP_BODIES = (
    "Дарвиновы гибриды, простые поздние и сорта группы Грейга собраны в "
    "подборку: каждый сорт описан по цвету и срокам цветения.",
    "Beauty of Leo — новинка с рассечёнными лепестками и необычной "
    "окраской; селекционеры предполагают сроки цветения конца апреля.",
    "Pride mix — смесь оттенков для непрерывного цветения: в коллекции "
    "присутствуют розовые и жёлтые формы.",
    "Menton Oranje — новинка с глубоким оранжево-терракотовым цветом; "
    "луковицы сажают в защищённом уголке сада.",
)
TULIP_TEXT = TULIP_INTRO + "\n\n" + "\n\n".join(
    "%s: %s" % (s, b) for s, b in zip(TULIP_SECS, TULIP_BODIES))
TULIP_HTML = (
    "<html><head><title>%s</title>"
    "<meta property=\"og:image\" content=\"https://cdn.example.test/agro/tulip.jpg\">"
    "<script type=\"application/ld+json\">"
    "{\"@type\":\"Article\",\"headline\":\"%s\",\"datePublished\":\"%s\"}"
    "</script></head><body><article><p>%s</p>%s</article></body></html>"
) % (TULIP_TITLE, TULIP_TITLE, _today(), TULIP_INTRO,
     "".join("<h2>%s</h2><p>%s</p>" % (s, b)
             for s, b in zip(TULIP_SECS, TULIP_BODIES)))

TULIP_GOOD_POST = (
    TULIP_TITLE + "\n\n"
    "\U0001F338 Весна близко — пора планировать посадки новых тюльпанов.\n\n"
    "\U0001F337 Топ-14 новых интересных сортов тюльпанов сезона собрано в "
    "подборке от Дарвиновых до Грейга.\n\n"
    "\U0001F33A Beauty of Leo — новинка с рассечёнными лепестками и "
    "яркой окраской.\n\n"
    "\U0001F33B Menton Oranje — новинка с глубоким оранжево-терракотовым "
    "цветом для клумбы.\n\n"
    "\U0001F4A1 Вывод: выбирайте сорта под свой сад и сочетайте сроки "
    "цветения."
)


def test_real_koza_full_retelling_passes_completeness():
    """Полноценный краткий пересказ «Козы в ЛПХ» (5 из 6 разделов;
    однословные секции покрываются ВСЕМ их ключом) НЕ отклоняется как
    неполный — регрессия ложного «covers N/M» на реальном материале."""
    hit, verifiable, _ = agro._section_cover(KOZA_GOOD_POST, KOZA_TEXT,
                                             KOZA_HTML)
    assert (hit, verifiable) == (5, 6), (hit, verifiable)
    assert agro._completeness_errors(KOZA_GOOD_POST, KOZA_TEXT, KOZA_HTML) == []


def test_real_tulip_latin_section_names_are_fairly_checked():
    """Реальный обзор тюльпанов («covers 1/4» и «covers 0/4» на запуске
    13.10): секции-имена сверяются по латинским ключам (модель пишет сорта
    той же латиницей), заголовок без единого ключа («Leo 2026 mix») в
    проверку не входит; полноценный пересказ проходит, вступительный — нет."""
    hit, verifiable, missed = agro._section_cover(TULIP_GOOD_POST, TULIP_TEXT,
                                                  TULIP_HTML)
    assert (hit, verifiable) == (3, 4) and missed == ["Pride mix"], \
        (hit, verifiable, missed)
    intro_only = TULIP_TITLE + "\n\nВесна близко — скоро цветы."
    errs = agro._completeness_errors(intro_only, TULIP_TEXT, TULIP_HTML)
    assert any("covers 0/4" in e for e in errs), errs


def test_section_cover_one_key_headings_need_one_match():
    """Однословные секции («Гирудотерапия», «Содержание дома» — отпечаток
    «covers 3/7» запуска 13.10): требование «≥2 совпадений» для них
    невыполнимо в принципе, поэтому такая секция проверяется по всему
    своему ключу (одно совпадение); двух-ключевой заголовок по-прежнему
    требует два."""
    secs = ["Гирудотерапия", "Содержание дома", "Раздельное содержание"]
    text = ("Пиявки продают в аптеках.\n\n"
            + "\n\n".join("%s: пиявок держат дома до применения." % s
                          for s in secs))
    html = "<article>%s</article>" % "".join(
        "<h2>%s</h2><p>пиявок держат дома до применения.</p>" % s for s in secs)
    post = ("Заголовок про пиявок\n\n"
            "Гирудотерапия дома популярна у дачников.\n\n"
            "Содержание пиявок требует чистой воды и прохлады.\n\n"
            "Вывод: соблюдайте чистоту при уходе.")
    hit, verifiable, missed = agro._section_cover(post, text, html)
    assert (hit, verifiable) == (2, 3), (hit, verifiable)
    assert missed == ["Раздельное содержание"], missed


def test_real_koza_listicle_rejected_then_fixed_by_targeted_retry(st,
                                                                 monkeypatch):
    """Реальный дефект 13.10: ответ-перечень с нумерацией «1.» отклонён
    контрактом; ПОВТОР получает адресную инструкцию (бан нумерации + те же
    факты) — исправленный плоский пост проходит и готовится к публикации.
    Повтор чинит НАЙДЕННОЕ нарушение, а не «случайность сэмплинга»."""
    _fake_network(monkeypatch, {KOZA_URL: KOZA_HTML})
    prov = StubProvider(KOZA_NUMBERED_POST, KOZA_GOOD_POST)
    r = agro.process_url(st, KOZA_URL, "supersadovnik", dry_run=True,
                         provider=prov)
    assert r["status"] == "post_ready" and r["ai"] == "edited", r
    assert len(prov.calls) == 2
    retry = _user_msg(prov, 1)
    assert "ПРЕДЫДУЩАЯ ПОПЫТКА ОТКЛОНЕНА: enumerated items" in retry
    assert "нумерация пунктов" in retry and "эмодзи-буллета" in retry
    post = st.get(st.add(KOZA_URL, "supersadovnik"))["post_text"]
    assert "зааненскую и чешскую бурую" in post          # факты сохранены
    assert not re.search(r"(?<![\d.,])\d{1,2}[.)]\s", post)


def test_real_koza_lost_sections_go_to_review_with_reason(st, monkeypatch):
    """«covers 2/6» (реальный отказ 13.10, обе попытки): пост, потерявший
    4 раздела из 6, НЕ публикуется; повтор адресный — перечисляет
    пропущенные разделы по имени; после неудачного повтора — review с
    конкретной причиной в row.reason (не молчаливая обрезка и не
    публикация «что осталось»)."""
    _fake_network(monkeypatch, {KOZA_URL: KOZA_HTML})
    prov = StubProvider(KOZA_PARTIAL_POST, KOZA_PARTIAL_POST)
    r = agro.process_url(st, KOZA_URL, "supersadovnik", dry_run=True,
                         provider=prov)
    assert r["status"] == "review" and r["ai"] == "failed", r
    assert len(prov.calls) == 2
    hints = _user_msg(prov, 1).split("ЧТО ИСПРАВИТЬ:")[1]
    assert "не отражены разделы исходника" in hints
    assert "Что выгоднее для ЛПХ?" in hints       # пропущенный раздел назван
    assert "Молочные породы коз" not in hints     # покрытый — не назван
    row = st.get(st.add(KOZA_URL, "supersadovnik"))
    assert row["status"] == "review" and not row["post_text"]
    assert "covers 2/6" in row["reason"], row["reason"]
    assert st.db.execute("SELECT COUNT(*) c FROM publications").fetchone()["c"] == 0


def test_prompt_requires_section_coverage_and_no_numbering():
    """Инструкции модели конкретны: отражать разделы исходника и не
    нумеровать пункты — ровно то, чего не хватало в промпте на отказах
    13.10 («covers N/M» и «enumerated items»)."""
    assert "РАЗДЕЛЫ:" in agro.AI_EDIT_SYSTEM
    assert "не выбрасывай целые разделы" in agro.AI_EDIT_SYSTEM
    assert "НИКАКОЙ нумерации" in agro.AI_EDIT_SYSTEM
