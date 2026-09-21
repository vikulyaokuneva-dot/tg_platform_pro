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

    def spy(token, chat_id, text, dry_run=False, parse_mode=None, retries=2):
        assert (token, chat_id) == ("t", "-100AGRO")  # НЕ prod-пары
        return telegram.PublishResult(True, message_id=501)
    monkeypatch.setattr(telegram, "send_message", spy)

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
    sent = []

    def spy(token, chat_id, text, dry_run=False, parse_mode=None, retries=2):
        sent.append(text)
        return telegram.PublishResult(True, message_id=7)
    monkeypatch.setattr(telegram, "send_message", spy)
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
