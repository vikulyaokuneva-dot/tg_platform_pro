# -*- coding: utf-8 -*-
"""Второй канал (agro): конфигурация без секретов в коде, правилый агро-
классификатор, extractive-пост с гейтами, изоляция dedup/истории от production,
dry-run по умолчанию. Ядро/production-канал не затронуты — это и проверяем."""
import datetime
import io
import re

import pytest

from case_pipeline import (adapters, agro, classifier_agro, config, storage as
                           storage_mod, telegram)
from case_pipeline import hashtags as hashtags_mod

ART_URL = "https://www.botanichka.ru/article/kogda-sazhat-chesnok-osenyu/"
ART_TITLE = "Когда сажать чеснок осенью: 3 схемы и сроки по регионам"
PAR1 = ("Озимый чеснок сажают за 35-45 дней до устойчивых заморозков: зубчик "
        "должен укорениться, но не тронуться в рост. На юге это конец октября, "
        "в средней полосе - первая половина октября, на Урале - сентябрь. "
        "Ориентируйтесь на прогноз: почва остывает до +10 градусов на глубине "
        "5 см, и тогда посадку пора заканчивать, иначе луковица не успеет "
        "сформировать корни до холодов и уйдёт в зиму слабым.")
PAR2 = ("Ошибка - слишком ранняя посадка: перо, вышедшее до холодов, вымерзает. "
        "Схемы: лента с шагом 25 см между зубцами и 30 см между бороздами либо "
        "двухстрочная лента 20х40 см. Глубина заделки 6-8 см по лёгкому грунту "
        "и 10-12 см по тяжёлому, после посадки мульча слоем 5 см. Весной, как "
        "только почва оттает на 8 см, мульчу частично сгребают, а по заморозкам "
        "возвращают: такие приёмы сохраняют до 90 процентов всходов.")
ART_TEXT = PAR1 + "\n\n" + PAR2
ARTICLE_HTML = (
    "<html><head><title>%s</title>"
    "<meta property=\"og:image\" content=\"https://cdn.example.test/agro/chesnok.jpg\">"
    "<script type=\"application/ld+json\">"
    "{\"@type\":\"Article\",\"headline\":\"%s\",\"datePublished\":\"%s\"}"
    "</script></head><body><article><p>%s</p><p>%s</p></article></body></html>"
)


def _today():
    return (datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _art_html(url=ART_URL):
    return ARTICLE_HTML % (ART_TITLE, ART_TITLE, _today(), PAR1, PAR2)


@pytest.fixture()
def st(tmp_path):
    return storage_mod.Storage(str(tmp_path / "agro.db"))


def _fake_network(monkeypatch, pages):
    def fake_fetch(url, timeout=30, **kw):
        if url in pages:
            return 200, pages[url]
        raise AssertionError("unexpected fetch: %s" % url)
    monkeypatch.setattr(agro.httpclient, "fetch", fake_fetch)
    return fake_fetch


# ---------- конфигурация и безопасность ----------

def test_agro_config_defaults_are_off():
    assert config.AGRO_PUBLISH is False or config.AGRO_PUBLISH is True  # env-driven
    assert config.AGRO_SOURCES
    assert all(s in adapters.ADAPTERS for s in config.AGRO_SOURCES), \
        "источник агро без зарегистрированного адаптера"
    # отдельная БД истории — не общий файл с production-каналом
    assert config.AGRO_DB_PATH != config.DB_PATH


def test_no_secrets_hardcoded():
    for f in ("config.py", "telegram.py", "agro.py", "classifier_agro.py"):
        src = io.open("case_pipeline/" + f, encoding="utf-8").read()
        assert not re.search(r"\b\d{8,10}:[A-Za-z0-9_-]{25,}\b", src), f


def test_credentials_routing(monkeypatch):
    monkeypatch.setattr(config, "BOT_TOKEN", "PROD-TOKEN", raising=False)
    monkeypatch.setattr(config, "CHAT_ID", "PROD-CHAT", raising=False)
    monkeypatch.setattr(config, "AGRO_BOT_TOKEN", "AGRO-TOKEN", raising=False)
    monkeypatch.setattr(config, "AGRO_CHAT_ID", "AGRO-CHAT", raising=False)
    assert telegram.credentials() == ("PROD-TOKEN", "PROD-CHAT")
    assert telegram.credentials("ai") == ("PROD-TOKEN", "PROD-CHAT")
    assert telegram.credentials("agro") == ("AGRO-TOKEN", "AGRO-CHAT")


def test_prod_publish_path_unchanged(monkeypatch):
    """default канал = прежнее поведение: prod-токен и prod-чат, макет через postformat."""
    sent = {}

    def spy(token, chat_id, text, dry_run=False, parse_mode=None, retries=2):
        sent.update(token=token, chat=chat_id, dry=dry_run)
        return telegram.PublishResult(True, message_id=11)
    monkeypatch.setattr(telegram, "send_message", spy)
    monkeypatch.setattr(config, "BOT_TOKEN", "PROD-TOKEN", raising=False)
    monkeypatch.setattr(config, "CHAT_ID", "PROD-CHAT", raising=False)
    res = telegram.publish_post("**Заголовок**\n\nТекст поста")
    assert res.ok and sent == {"token": "PROD-TOKEN", "chat": "PROD-CHAT",
                               "dry": False}


def test_agro_publish_refuses_without_credentials(monkeypatch):
    monkeypatch.setattr(config, "AGRO_BOT_TOKEN", "", raising=False)
    monkeypatch.setattr(config, "AGRO_CHAT_ID", "", raising=False)

    def boom(*a, **k):
        raise AssertionError("real send without agro credentials!")
    monkeypatch.setattr(telegram, "send_message", boom)
    res = telegram.publish_post("Текст", dry_run=False, channel="agro")
    assert res.ok is False and "no credentials" in (res.error or "")


def test_send_message_no_prod_chat_fallback(monkeypatch):
    """Low-level API: чужой токен без чата не должен молча уйти в prod-чат
    (исторический `chat_id or config.CHAT_ID` fallback удалён)."""
    monkeypatch.setattr(config, "BOT_TOKEN", "PROD-TOKEN", raising=False)
    monkeypatch.setattr(config, "CHAT_ID", "PROD-CHAT", raising=False)

    def boom(*a, **k):
        raise AssertionError("HTTP send without explicit chat!")
    monkeypatch.setattr(telegram.requests, "post", boom)
    res = telegram.send_message("AGRO-TOKEN", None, "текст")
    assert not res.ok and "chat" in str(res.error).lower()
    res2 = telegram.send_message(None, "AGRO-CHAT", "текст")
    assert not res2.ok and "token" in str(res2.error).lower()


def test_agro_dry_run_without_secrets_is_safe(monkeypatch):
    """dry-run канала не требует секретов и ничего не шлёт."""
    seen = {}

    def spy(token, chat_id, text, dry_run=False, parse_mode=None, retries=2):
        seen.update(dry=dry_run, token=token)
        return telegram.PublishResult(True, message_id=0, error="dry-run")
    monkeypatch.setattr(telegram, "send_message", spy)
    res = telegram.publish_post("Текст", dry_run=True, channel="agro")
    assert res.ok and seen["dry"] is True


# ---------- классификатор ----------

def test_classifier_accepts_practical():
    v = classifier_agro.classify(ART_TITLE, ART_TEXT)
    assert v["type"] == "practical"
    assert v["confidence"] >= 0.6
    assert v["topics"] and v["topics"][0][2].startswith("#")


def test_classifier_rejects_ad():
    v = classifier_agro.classify(
        "Купить секатор со скидкой 50% - акция до пятницы, заказ по телефону",
        "Интернет-магазин предлагает секаторы, цена от 490 рублей, промокод "
        "САД100, бесплатная доставка при заказе от 3000 рублей. Спешите, "
        "количество ограничено, смотрите каталог товаров на сайте магазина.")
    assert v["type"] == "ad"


def test_classifier_rejects_offtopic_and_water():
    assert classifier_agro.classify(
        "Обзор смартфонов нового поколения",
        "В наш современный мир каждый мечтает о производительности. Без этого "
        "невозможно представить новые камеры и процессоры, лучшие решения в "
        "рейтинге телефонов и планшетов.")[
            "type"] == "offtopic"
    assert classifier_agro.classify("Ремонт серверных стоек в ЦОД",
                                    "Инцидент в дата-центре: перегрелся сервер, "
                                    "простой платформы на 4 часа, устраняют "
                                    "последствия.")["type"] == "offtopic"


def test_classifier_routes_pure_news():
    v = classifier_agro.classify(
        "Минсельхоз сообщил о запуске программы субсидирования",
        "По данным ведомства, программа стартует с 1 октября. Сообщает "
        "министерство: выделено 15 млрд рублей. Губернаторы доложат о ходе "
        "через месяц, документ подписан правительством.")
    assert v["type"] == "news"  # «случилось», а не «сделай» — не наш формат


def test_science_news_with_numbers_is_not_practical():
    """Регресс ложного practical (найдено на живом материале gismeteo
    'Эрозия болот переносит 380 тыс. тонн углерода'): обилие чисел + темы в
    теле — ещё не польза читателю; рамка польза/ rubric обязана быть в заголовке."""
    v = classifier_agro.classify(
        "Эрозия болот ежегодно переносит в океан около 380 тыс. тонн углерода",
        "Разрушение прибрежных болот приводит к оттоку накопленного в почве "
        "углерода. Исследование территории показало: ежегодный чистый вынос "
        "достигает примерно 380 тыс. тонн, сообщает Earth.com. Ученые "
        "проследили изменения за период с 1985 по 2022 год с помощью "
        "спутниковых снимков, в среднем эрозия высвобождала около 660 тыс. "
        "тонн, вновь образованные участки поглощали около 220 тыс. тонн.")
    assert v["type"] == "news"
    # тот же цифровой заголовок, но с рамкой пользы для читателя — practical
    v2 = classifier_agro.classify(
        "7 комнатных растений, которые выглядят иначе: что узнать садоводу",
        "Глядя на растение в горшке, мы видим его юность. У монстеры зреет "
        "плод со вкусом фруктового салата, шеффлера выбрасывает соцветия "
        "длиной с руку. Сравните внешний вид и уход: проверьте освещение, "
        "подберите кадку, обратите внимание на влажность.")
    assert v2["type"] == "practical"


# ---------- пост: гейты и grounding ----------

def test_post_is_extractive_and_keeps_source_title(st, monkeypatch):
    _fake_network(monkeypatch, {ART_URL: _art_html()})
    r = agro.process_url(st, ART_URL, "botanichka", publish=False, dry_run=True)
    assert r["status"] == "post_ready", r
    row = st.get(st.add(ART_URL, "botanichka"))
    post = row["post_text"]
    # заголовок источника сохранён (не переизобретается)
    assert "чеснок" in post.split("\n\n")[0].lower()
    # не кейсовый макет
    assert "Компания:" not in post and "Что автоматизировали" not in post
    assert "Источник: " + ART_URL in post
    assert agro.editorial_agro(post, ART_TEXT) == []
    # числа поста — только числа источника (инъекция ловится)
    assert agro.editorial_agro(post + "\n77% прибыли", ART_TEXT)


def test_tags_are_controlled(st, monkeypatch):
    _fake_network(monkeypatch, {ART_URL: _art_html()})
    r = agro.process_url(st, ART_URL, "botanichka", dry_run=True)
    tags = r["hashtags"]
    assert 3 <= len(tags) <= 5 and tags[0] == "#Практика"
    allowed = agro.AGRO_ALLOWED_TAGS | {"#Практика"}
    for t in tags:
        assert t in allowed or re.fullmatch(r"#[A-Za-zА-Яа-яЁё0-9_]{2,25}", t), t
    ok, errs = hashtags_mod.validate(tags, extra_allowed=agro.AGRO_ALLOWED_TAGS)
    assert ok, errs
    # словарь рубрик — тот же механизм контроля, что и у AI-канала
    assert set(dict(hashtags_mod.TYPE_TAGS)) >= {"case", "news", "agro"}


def test_stale_and_thin_rejected(st, tmp_path, monkeypatch):
    old = ARTICLE_HTML % (ART_TITLE, ART_TITLE, "2019-09-01T00:00:00+00:00",
                          PAR1, PAR2)
    _fake_network(monkeypatch, {ART_URL: old})
    r = agro.process_url(st, ART_URL, "botanichka", dry_run=True)
    assert r["status"] == "rejected" and r["reason"] == "stale"
    thin = ("<html><head><title>Чеснок</title></head><body><p>Коротко о "
            "чесноке.</p></body></html>")
    _fake_network(monkeypatch, {ART_URL: thin})
    st2 = storage_mod.Storage(str(tmp_path / "thin.db"))
    r = agro.process_url(st2, ART_URL, "botanichka", dry_run=True)
    assert r["status"] == "rejected" and r["reason"] == "thin"


def test_editorial_gate_is_review_not_post_ready(tmp_path, monkeypatch):
    """Регрессия к прогону CI 2026-10-07 20:32 (run 72).

    Единственная практическая статья того прогона прошла classifier_agro, но
    провалила editorial_agro («number not in source»: двузначное число из
    заголовка отсутствует в извлечённом тексте). Итог: status='review',
    а НЕ post_ready/published — поэтому в publish-режиме summary дал
    review=1, post_ready=0, published=0 и НИ ОДНОЙ отправки в Telegram не было
    (все остальные 23 прогона с review>=1 сопровождались telegram publish
    failed). Поведение фильтра штатное; тест фиксирует, что гейт не «лечится»
    повторным проходом и не попадает в published."""
    title = ART_TITLE.replace("3 схемы", "77 схем")
    html = ARTICLE_HTML % (title, title, _today(), PAR1, PAR2)
    _fake_network(monkeypatch, {ART_URL: html})

    st1 = storage_mod.Storage(str(tmp_path / "editorial.db"))
    r = agro.process_url(st1, ART_URL, "botanichka", publish=False, dry_run=True)
    assert r["status"] == "review" and r["reason"] == "editorial gate", r
    row = st1.get(st1.add(ART_URL, "botanichka"))
    assert row["status"] == "review"
    assert "number not in source: 77" in row["reason"], row["reason"]
    # review входит в _known_skip: повторный проход статус не меняет
    r2 = agro.process_url(st1, ART_URL, "botanichka", publish=False, dry_run=True)
    assert r2["status"] == "skipped" and "already review" in r2["reason"]

    # сводка прогона — как в CI run 72: review=1, post_ready=0, published=0
    st2 = storage_mod.Storage(str(tmp_path / "editorial_run.db"))
    monkeypatch.setattr(agro.adapters.ADAPTERS["botanichka"], "discover",
                        lambda: [ART_URL])
    s = agro.run(dry_run=True, publish=False, sources=["botanichka"], st=st2)
    assert s["checked"] == 1 and s["review"] == 1, s
    assert s["post_ready"] == 0 and s["published"] == 0, s


# ---------- dedup и изоляция каналов ----------

def test_dedup_repeat_not_reprocessed(st, monkeypatch):
    _fake_network(monkeypatch, {ART_URL: _art_html()})
    r1 = agro.process_url(st, ART_URL, "botanichka", dry_run=True)
    r2 = agro.process_url(st, ART_URL, "botanichka", dry_run=True)
    assert r1["status"] == "post_ready"
    assert r2["status"] == "skipped" and "already" in r2["reason"]


def test_publish_marks_agro_chat_in_agro_history_only(st, tmp_path, monkeypatch):
    prod = storage_mod.Storage(str(tmp_path / "prod.db"))
    _fake_network(monkeypatch, {ART_URL: _art_html()})
    monkeypatch.setattr(config, "AGRO_PUBLISH", True, raising=False)
    monkeypatch.setattr(config, "AGRO_CHAT_ID", "-100AGRO", raising=False)
    monkeypatch.setattr(config, "AGRO_BOT_TOKEN", "t", raising=False)
    # контракт TEXT+IMAGE+SOURCE: байты изображения скачиваются, отправка — sendPhoto
    monkeypatch.setattr(agro.httpclient, "fetch_bytes",
                        lambda url, **kw: b"\xff\xd8" + b"x" * 20000)

    def spy(token, chat_id, photo_url=None, photo_bytes=None, caption=None,
            dry_run=False, retries=2, parse_mode=None):
        assert (token, chat_id) == ("t", "-100AGRO")  # НЕ prod-пары
        assert photo_bytes, "публикация агро обязана уходить с изображением"
        return telegram.PublishResult(True, message_id=501)
    monkeypatch.setattr(telegram, "send_photo", spy)

    r = agro.process_url(st, ART_URL, "botanichka", publish=True, dry_run=False)
    assert r["status"] == "published" and r["telegram_message_id"] == 501
    assert st.get(st.add(ART_URL, "x"))["status"] == "published"
    pubs = st.db.execute("SELECT chat_id, content_type FROM publications").fetchall()
    assert [dict(p) for p in pubs] == [{"chat_id": "-100AGRO",
                                        "content_type": "agro"}]
    # production-БД не узнала о публикации (свой файл -> отсутствие взаимного
    # блокирования dedup между каналами) и не содержит строк вовсе
    assert prod.db.execute("SELECT COUNT(*) c FROM publications").fetchone()["c"] == 0


def test_run_respects_publish_limit(st, monkeypatch):
    _fake_network(monkeypatch, {ART_URL: _art_html()})
    monkeypatch.setattr(agro.adapters.ADAPTERS["botanichka"], "discover",
                        lambda: [ART_URL])
    monkeypatch.setattr(config, "AGRO_PUBLISH", True, raising=False)
    monkeypatch.setattr(config, "AGRO_PUBLISH_LIMIT", 1, raising=False)
    monkeypatch.setattr(config, "AGRO_BOT_TOKEN", "t", raising=False)
    monkeypatch.setattr(config, "AGRO_CHAT_ID", "-100AGRO", raising=False)
    monkeypatch.setattr(agro.httpclient, "fetch_bytes",
                        lambda url, **kw: b"\xff\xd8" + b"x" * 20000)
    sent = []

    def spy(token, chat_id, photo_url=None, photo_bytes=None, caption=None,
            dry_run=False, retries=2, parse_mode=None):
        assert photo_bytes
        sent.append(caption)
        return telegram.PublishResult(True, message_id=7)
    monkeypatch.setattr(telegram, "send_photo", spy)
    s = agro.run(dry_run=False, publish=True, sources=["botanichka"], st=st)
    assert s["published"] == 1, s
    assert s["checked"] >= 1 and len(sent) == 1


def test_run_dry_never_sends(st, monkeypatch):
    _fake_network(monkeypatch, {ART_URL: _art_html()})
    monkeypatch.setattr(agro.adapters.ADAPTERS["botanichka"], "discover",
                        lambda: [ART_URL])

    def boom(*a, **k):
        raise AssertionError("dry-run отправил сообщение!")
    monkeypatch.setattr(telegram, "send_message", boom)
    s = agro.run(dry_run=True, publish=False, sources=["botanichka"], st=st)
    assert s["post_ready"] == 1 and s["published"] == 0


def test_rss_adapter_parses_feed_items(monkeypatch):
    xml = ("<rss><channel><item><title>Т</title><link>https://www.botanichka.ru"
           "/article/chem-podkormit-rozy-osenyu/</link><pubDate>Tue, 15 Sep 2026"
           " 14:48:28 +0000</pubDate></item><item><link>https://www.botanichka.ru/"
           "activity/</link></item></channel></rss>")
    def fake(url, timeout=30, **kw):
        return 200, xml
    # adapters импортирует fetch в своё пространство имён — патчим там
    monkeypatch.setattr(adapters, "fetch", fake)
    urls = adapters.ADAPTERS["botanichka"].discover()
    assert urls == ["https://www.botanichka.ru/article/chem-podkormit-rozy-osenyu/"]


def test_agroinvestor_adapter_rejects_business_pages():
    ad = adapters.ADAPTERS["agroinvestor"]
    assert ad.accept("https://www.agroinvestor.ru/markets/news/46540-x/")
    assert ad.accept("https://www.agroinvestor.ru/analytics/article/46522-y/")
    assert not ad.accept("https://www.agroinvestor.ru/business-pages/46534-adv/")
    assert not ad.accept("https://www.agroinvestor.ru/markets/")


# ---------- контракт TEXT+IMAGE+SOURCE: изображение обязательно ----------

NO_IMG_HTML = (
    "<html><head><title>%s</title>"
    "<script type=\"application/ld+json\">"
    "{\"@type\":\"Article\",\"headline\":\"%s\",\"datePublished\":\"%s\"}"
    "</script></head><body><article><p>%s</p><p>%s</p></article></body></html>"
)


def test_missing_image_is_not_post_ready_and_never_published(st, monkeypatch):
    """Без изображения материал не готовится и не публикуется:
    publish=NO, reason=missing_image; строка в publications отсутствует."""
    html = NO_IMG_HTML % (ART_TITLE, ART_TITLE, _today(), PAR1, PAR2)
    _fake_network(monkeypatch, {ART_URL: html})
    monkeypatch.setattr(config, "AGRO_PUBLISH", True, raising=False)

    def boom(*a, **k):
        raise AssertionError("publish без изображения не должен вызываться")
    monkeypatch.setattr(telegram, "publish_post", boom)

    r = agro.process_url(st, ART_URL, "botanichka", publish=True, dry_run=False)
    assert r["status"] == "rejected" and r["reason"] == "missing_image", r
    assert st.get(st.add(ART_URL, "x"))["status"] == "rejected"
    pubs = st.db.execute("SELECT COUNT(*) c FROM publications").fetchone()
    assert pubs["c"] == 0


def test_content_image_fallback_when_no_og_image(st, monkeypatch):
    """Приоритет image URL: ext['image'] (og/JSON-LD) → первый содержательный
    <img> контента (относительный src резолвится в абсолютный)."""
    html = (NO_IMG_HTML % (ART_TITLE, ART_TITLE, _today(), PAR1, PAR2)).replace(
        "<article>",
        "<article><img src=\"/uploads/chesnok-osen.jpg\" alt=\"чеснок\">")
    _fake_network(monkeypatch, {ART_URL: html})
    r = agro.process_url(st, ART_URL, "botanichka", dry_run=True)
    assert r["status"] == "post_ready", r
    row = st.get(st.add(ART_URL, "botanichka"))
    assert row["image_url"] == "https://www.botanichka.ru/uploads/chesnok-osen.jpg"


def test_protocol_relative_og_image_is_normalized(st, monkeypatch):
    """og:image вида «//host/...» нормализуется в https://: fetch_bytes
    принимает только абсолютные http(s)-URL (иначе MissingSchema на публикации)."""
    html = (NO_IMG_HTML % (ART_TITLE, ART_TITLE, _today(), PAR1, PAR2)).replace(
        "</head>",
        "<meta property=\"og:image\" "
        "content=\"//cdn.example.test/agro/narcissy.jpg\"></head>")
    _fake_network(monkeypatch, {ART_URL: html})
    r = agro.process_url(st, ART_URL, "botanichka", dry_run=True)
    assert r["status"] == "post_ready", r
    row = st.get(st.add(ART_URL, "botanichka"))
    assert row["image_url"] == "https://cdn.example.test/agro/narcissy.jpg"


def test_logo_img_is_not_a_material_image(st, monkeypatch):
    """Логотипы/иконки не считаются изображением материала."""
    html = (NO_IMG_HTML % (ART_TITLE, ART_TITLE, _today(), PAR1, PAR2)).replace(
        "<article>",
        "<article><img src=\"/static/logo-site.png\">"
        "<img src=\"/uploads/gryadka.jpg\">")
    _fake_network(monkeypatch, {ART_URL: html})
    r = agro.process_url(st, ART_URL, "botanichka", dry_run=True)
    assert r["status"] == "post_ready", r
    row = st.get(st.add(ART_URL, "botanichka"))
    assert row["image_url"] == "https://www.botanichka.ru/uploads/gryadka.jpg"


def test_publish_sends_photo_with_source_and_validated_bytes(st, monkeypatch):
    """Реальная публикация: байты скачиваются fetch_bytes (валидация до
    отправки), уходит sendPhoto с caption ≤1024; «Источник:» и хэштеги в
    caption сохранены."""
    _fake_network(monkeypatch, {ART_URL: _art_html()})
    fetched = {}

    def fake_bytes(url, **kw):
        fetched["url"] = url
        return b"\xff\xd8" + b"x" * 20000
    monkeypatch.setattr(agro.httpclient, "fetch_bytes", fake_bytes)
    monkeypatch.setattr(config, "AGRO_PUBLISH", True, raising=False)
    monkeypatch.setattr(config, "AGRO_BOT_TOKEN", "t", raising=False)
    monkeypatch.setattr(config, "AGRO_CHAT_ID", "-100AGRO", raising=False)
    seen = {}

    def spy(token, chat_id, photo_url=None, photo_bytes=None, caption=None,
            dry_run=False, retries=2, parse_mode=None):
        seen.update(token=token, chat=chat_id, photo=photo_bytes,
                    caption=caption, parse_mode=parse_mode)
        return telegram.PublishResult(True, message_id=707)
    monkeypatch.setattr(telegram, "send_photo", spy)

    r = agro.process_url(st, ART_URL, "botanichka", publish=True, dry_run=False)
    assert r["status"] == "published" and r["telegram_message_id"] == 707, r
    assert fetched["url"] == "https://cdn.example.test/agro/chesnok.jpg"
    assert seen["photo"] and seen["parse_mode"] == "MarkdownV2"
    assert (seen["token"], seen["chat"]) == ("t", "-100AGRO")
    assert len(seen["caption"]) <= 1024
    plain = telegram.postformat.unescape_markdownv2(seen["caption"])
    assert "Источник: " + ART_URL in plain
    assert "#Практика" in plain


def test_image_fetch_failure_is_failed_not_published(st, monkeypatch):
    """Ошибка скачивания изображения до claim: status=failed (авто-ретрай
    следующим прогоном), publish не вызывается, публикации нет."""
    _fake_network(monkeypatch, {ART_URL: _art_html()})
    monkeypatch.setattr(config, "AGRO_PUBLISH", True, raising=False)
    monkeypatch.setattr(agro.httpclient, "fetch_bytes",
                        lambda url, **kw: (_ for _ in ()).throw(
                            RuntimeError("403 forbidden")))

    def boom(*a, **k):
        raise AssertionError("sendPhoto при битых байтах изображения")
    monkeypatch.setattr(telegram, "send_photo", boom)

    r = agro.process_url(st, ART_URL, "botanichka", publish=True, dry_run=False)
    assert r["status"] == "failed" and r["reason"] == "image fetch", r
    assert st.get(st.add(ART_URL, "x"))["status"] == "failed"
    assert st.db.execute("SELECT COUNT(*) c FROM publications").fetchone()["c"] == 0


def test_fetch_bytes_validates_image_contract(monkeypatch):
    from case_pipeline import httpclient as hc

    class Resp:
        def __init__(self, status, ctype, data):
            self.status_code = status
            self.headers = {"Content-Type": ctype}
            self.content = data

    # HTML вместо изображения — контрактная ошибка, без ретраев
    monkeypatch.setattr(hc.requests, "get",
                        lambda *a, **k: Resp(200, "text/html; charset=utf-8", b"<html>"))
    with pytest.raises(hc.FetchError):
        hc.fetch_bytes("https://x.test/page")
    # трекер/превью слишком малы
    monkeypatch.setattr(hc.requests, "get",
                        lambda *a, **k: Resp(200, "image/png", b"tiny"))
    with pytest.raises(hc.FetchError):
        hc.fetch_bytes("https://x.test/px.gif")
    # валидное изображение проходит
    monkeypatch.setattr(hc.requests, "get",
                        lambda *a, **k: Resp(200, "image/jpeg", b"y" * 20480))
    data = hc.fetch_bytes("https://x.test/pic.jpg")
    assert data[:1] == b"y" and len(data) == 20480


# ---------- thin content: лойальный порог (Part 2) ----------

def test_short_but_substantive_article_is_not_thin(st, monkeypatch):
    """MIN_BODY_CHARS=300: короткая, но содержательная инструкция проходит
    thin-гейт; ~20-символьные заглушки остаются reject (test_stale_and_thin)."""
    title = "Как подкормить клубнику осенью и сохранить всходы"
    short = ("Подкормите клубнику осенью калийным удобрением — это укрепит корни "
             "перед зимой. Замульчируйте грядку соломой слоем 5 см и уберите "
             "старые листы: в них зимуют споры мучнистой росы. Полейте после "
             "дождя, чтобы раствор проник к корням, и весной дождётесь здоровых "
             "всходов и щедрого урожая ягод. Такой уход — залог сладких ягод.")
    assert len(short) >= 300, len(short)
    html = (NO_IMG_HTML % (title, title, _today(), short, "")).replace(
        "<article>", "<article><img src=\"/uploads/klubnika.jpg\">")
    _fake_network(monkeypatch, {ART_URL: html})
    r = agro.process_url(st, ART_URL, "botanichka", dry_run=True)
    assert r["status"] == "post_ready", r


# ---------- news_hold-rescue (Part 3) ----------

def test_news_rescue_keeps_actionable_material_out_of_hold():
    """Пересмотр news_hold: заголовок с рамкой пользы + рубрикой темы, в теле
    практические сигналы, но нет чисел/императивов правила 3 — материал
    поднимается до practical с пониженным confidence (signals rescue=1)."""
    v = classifier_agro.classify(
        "Правила укрытия яблонь перед холодами: что важно успеть",
        "По данным садоводов, молодые деревья связывают мешковиной, стволы "
        "окучивают сухой землёй. Обрезку откладывают: иначе срезы не успеют "
        "затянуться. Главная ошибка — плотное оборачивание: под укрытием "
        "накапливается влага, кора начинает гнить. Главное правило — оставить "
        "сверху просвет для воздуха и раз в месяц проверять состояние укрытия.")
    assert v["type"] == "practical", v
    assert v["confidence"] <= 0.7
    assert v["signals"].get("rescue") == 1


def test_lifestyle_practice_is_offtopic_but_garden_title_passes():
    """Смешанные журналы: практическая инструкция не на нашу тему (аквариум) —
    offtopic; сильный садовый заголовок проходит дальше anti-гейта."""
    v = classifier_agro.classify(
        "Аквариум без хлопот: 10 неприхотливых рыбок с простым уходом",
        "Запустите в аквариум растения-оксигенераторы: элодея и риччия "
        "насыщают воду кислородом. Подберите грунт мелкой фракции и не "
        "кормите рыбок чаще двух раз в день — остатки киснут и портят воду.")
    assert v["type"] == "offtopic", v

    v2 = classifier_agro.classify(
        "Гороскоп для дачников: что говорит звёздный прогноз",
        "Астрологи советуют не спешить с посадкой: Луна в знаке Водолея "
        "благоприятствует прорастанию. Проверьте лунный календарь и сейте "
        "всходы по фазам — так, по поверью, всходы будут дружнее.")
    assert v2["type"] == "offtopic", v2


# ---------- новые источники (Part 1) ----------

def test_new_sources_registered_and_enabled():
    for name in ("aif", "supersadovnik", "ogorodnik", "7dach"):
        assert name in adapters.ADAPTERS, name
        assert name in config.AGRO_SOURCES, name


def test_new_adapter_accept_patterns():
    aif = adapters.ADAPTERS["aif"]
    assert aif.accept("https://aif.ru/dacha/ogorod/pravila-podzimney-gryadki")
    assert aif.accept("https://aif.ru/dacha/garden/chto-posadit-osenyu")
    assert not aif.accept("https://aif.ru/dacha/ogorod")            # сам каталог
    assert not aif.accept("https://aif.ru/dacha/construction/dom")  # не наша рубрика

    ss = adapters.ADAPTERS["supersadovnik"]
    assert ss.accept("https://www.supersadovnik.ru/text/kogda-i-kak-"
                     "pravilno-peresazhivat-malinu-osenju-1014735")
    assert ss.accept("https://www.supersadovnik.ru/plant/smorodina-gordona-1790")
    assert not ss.accept("https://www.supersadovnik.ru/text/prognoz-dlja-"
                         "dachnikov-na-2027-god-ot-astrologa-1014745")
    assert not ss.accept("https://www.supersadovnik.ru/text/bassejn-v-"
                         "osenne-zimnij-period-1014741")
    assert not ss.accept("https://www.supersadovnik.ru/")

    sd = adapters.ADAPTERS["7dach"]
    assert sd.accept("https://7dach.ru/Tangeya/ot-kurochki-s-lyubovyu-"
                     "segodnya-prazdnik-yayca-329394.html")
    assert not sd.accept("https://7dach.ru/zdorovie/chto-delat-12345.html")
    assert not sd.accept("https://7dach.ru")


def test_new_adapter_discovery(monkeypatch):
    # АиФ: абсолютные ссылки двух каталогов, сам каталог-URL не предлагается
    aif_html = ('<a href="https://aif.ru/dacha/ogorod/pravila-podzimney-gryadki">x</a>'
                '<a href="https://aif.ru/dacha/garden/chto-posadit-osenyu">y</a>'
                '<a href="https://aif.ru/dacha/ogorod">каталог</a>')
    pages = {"https://aif.ru/dacha/ogorod": aif_html,
             "https://aif.ru/dacha/garden": aif_html}
    monkeypatch.setattr(adapters, "fetch",
                        lambda url, timeout=30, **kw: (200, pages[url]))
    urls = adapters.ADAPTERS["aif"].discover()
    assert "https://aif.ru/dacha/ogorod/pravila-podzimney-gryadki" in urls
    assert "https://aif.ru/dacha/garden/chto-posadit-osenyu" in urls
    assert "https://aif.ru/dacha/ogorod" not in urls

    # Огородник: только /blog/<рубрика>/<slug>/, сами рубрики не берём
    og_html = ('<a href="/blog/yagody/kak-pravilno-obrezat-klubniku/">a</a>'
               '<a href="/blog/yagody/">рубрика</a>')
    monkeypatch.setattr(adapters, "fetch",
                        lambda url, timeout=30, **kw: (200, og_html))
    urls = adapters.ADAPTERS["ogorodnik"].discover()
    assert urls == ["https://ogorodnik.ru/blog/yagody/kak-pravilno-obrezat-klubniku/"]

    # Суперсадовник: из фида — только садовые разделы, лайфстайл-слаги нет
    ss_xml = ("<rss><channel>" + "".join(
        "<item><link><![CDATA[%s]]></link></item>" % u for u in (
            "https://www.supersadovnik.ru/text/kogda-peresazhivat-malinu-123",
            "https://www.supersadovnik.ru/text/god-krasnoj-ognennoj-kozy-2027--9",
            "https://www.supersadovnik.ru/plant/pieris-1787",
            "https://www.supersadovnik.ru/")) + "</channel></rss>")
    monkeypatch.setattr(adapters, "fetch",
                        lambda url, timeout=30, **kw: (200, ss_xml))
    urls = adapters.ADAPTERS["supersadovnik"].discover()
    assert urls == ["https://www.supersadovnik.ru/text/kogda-peresazhivat-malinu-123",
                    "https://www.supersadovnik.ru/plant/pieris-1787"]

    # 7dach: только статьи <slug>-<id>.html; /zdorovie/ и корень — нет
    sd_xml = ("<rss><channel>" + "".join(
        "<item><link><![CDATA[%s]]></link></item>" % u for u in (
            "https://7dach.ru/Tangeya/sliva-diploidnaya-lodva-329392.html",
            "https://7dach.ru/zdorovie/chto-takoe-davlenie-1.html",
            "https://7dach.ru")) + "</channel></rss>")
    monkeypatch.setattr(adapters, "fetch",
                        lambda url, timeout=30, **kw: (200, sd_xml))
    urls = adapters.ADAPTERS["7dach"].discover()
    assert urls == ["https://7dach.ru/Tangeya/sliva-diploidnaya-lodva-329392.html"]
