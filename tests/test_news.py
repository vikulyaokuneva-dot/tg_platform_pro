# -*- coding: utf-8 -*-
"""«Новость дня»: настраиваемый источник, извлечение, 2-3 предложения,
evidence-гейты, дедуп, изоляция ошибок, сброс счётчика."""
import json

import pytest

from case_pipeline import ai, config, httpclient, news, pipeline, storage as storage_mod

NEWS_URL = "https://news.example.com/news/2026/09/11/42/"
LISTING_HTML = """<html><body>
<a href="/news/2026/09/11/42/">Нейросеть сократила обработку заявок в банке на 60 процентов</a>
<a href="/tags/ai">тег</a>
<a href="https://other.example/x/y">чужой домен ссылка новостная</a>
</body></html>"""
ARTICLE_TEXT = ("Банк Заря внедрил нейросеть для разбора обращений клиентов. "
                "Время обработки заявки сократилось на 60 процентов, рутина "
                "исчезла из работы колл-центра. Операторы подключаются только "
                "в сложных случаях. По словам представителей банка, проект "
                "внедрялся поэтапно в течение полугода: интеграция с "
                "существующими системами, разметка исторических обращений и "
                "обучение сотрудников работе в новом интерфейсе. Теперь "
                "система сама классифицирует входящие сообщения, определяет "
                "срочность и передаёт диалог нужному специалисту, а руководители "
                "видят статистику по нагрузке в реальном времени. В банке "
                "отмечают, что второй этап затронет кредитный конвейер и "
                "подготовку отчётности для регулятора, а пилот планируют "
                "распространить на розничное подразделение до конца года.")
ARTICLE_HTML = ("<html><head><title>Нейросеть сократила обработку заявок в банке на 60 "
                "процентов</title></head><body><p>%s</p></body></html>" % ARTICLE_TEXT)


class NewsAI(ai.BaseAI):
    name = "fake-news"
    available = True

    def __init__(self, payload=None):
        self.payload = payload if payload is not None else {
            "headline_ru": "Банк ускорил разбор заявок на 60%",
            "summary_ru": "Банк «Заря» подключил нейросеть к разбору обращений. "
                          "Время обработки заявки сократилось на 60 процентов. "
                          "Операторы теперь только в сложных кейсах.",
            "company": "Банк Заря",
            "facts": ["Время обработки заявки сократилось на 60 процентов"],
        }

    def complete(self, msgs):
        return json.dumps(self.payload, ensure_ascii=False)


@pytest.fixture()
def env(tmp_path, monkeypatch):
    runs = tmp_path / "runs"
    runs.mkdir()
    monkeypatch.setattr(config, "RUNS_DIR", str(runs))
    monkeypatch.setattr(config, "NEWS_SOURCES", ["https://news.example.com/news/"])
    st = storage_mod.Storage(str(tmp_path / "n.db"))
    art = pipeline.RunArtifacts(str(runs))
    return st, art


@pytest.fixture()
def fake_news_http(monkeypatch):
    def fake_fetch(url, *a, **k):
        if url.rstrip("/").endswith("/news"):
            return 200, LISTING_HTML
        return 200, ARTICLE_HTML
    monkeypatch.setattr(httpclient, "fetch", fake_fetch)
    monkeypatch.setattr(news.httpclient, "fetch", fake_fetch)


def test_source_configurable(env, fake_news_http, monkeypatch):
    monkeypatch.setattr(config, "NEWS_SOURCES", ["https://nothing.example/news/"])

    def dead(url, *a, **k):
        raise httpclient.FetchError("down")
    monkeypatch.setattr(news.httpclient, "fetch", dead)
    st, art = env
    assert news.process_news(st, art, NewsAI()) is None  # не падает


def test_news_generated_short_russian(env, fake_news_http):
    st, art = env
    row = news.process_news(st, art, NewsAI(), publish=False)
    assert row and row["status"] == "post_ready", row
    assert row["news_id"].startswith("news-")
    m = st.get(st.seen_url(NEWS_URL)["id"])
    text = m["post_text"]
    assert "📰 НОВОСТЬ ДНЯ" in text and NEWS_URL in text
    assert "#НовостьДня" in text and "#Кейс" not in text
    assert len(text) <= news.MAX_POST_CHARS
    body = text.split("🔗")[0]
    assert 2 <= len([s for s in body.split(".") if s.strip()]) <= 8  # компактно


def test_news_publish_and_counter_reset(env, fake_news_http, monkeypatch):
    st, art = env
    mid = st.add("https://x.ru/case/1", "mindbox")
    st.update(mid, status="post_ready")
    st.mark_published(mid, 900, "-100", "case-1", content_type="case")
    assert st.count_cases_since_last_news() == 1

    sent = []

    class R:
        ok, message_id, error, http_status = True, 901, None, 200

    def fake_pub(text, chat_id=None, dry_run=False):
        sent.append(text)
        return R()
    monkeypatch.setattr(news.telegram, "publish_post", fake_pub)
    row = news.process_news(st, art, NewsAI(), publish=True)
    assert row["status"] == "published" and row["telegram_message_id"] == 901
    p = st.db.execute("SELECT * FROM publications WHERE content_type='news'").fetchone()
    assert p and "#НовостьДня" in p["hashtags"]
    assert st.count_cases_since_last_news() == 0


def test_news_duplicate_not_republished(env, fake_news_http, monkeypatch):
    st, art = env
    r1 = news.process_news(st, art, NewsAI(), publish=False)
    assert r1["status"] == "post_ready"
    sent = []

    class R:
        ok, message_id, error, http_status = True, 950, None, 200

    def fake_pub(text, chat_id=None, dry_run=False):
        sent.append(text)
        return R()
    monkeypatch.setattr(news.telegram, "publish_post", fake_pub)
    # publish-прогон: отправляет ровно одну подготовленную новость из БД
    r2 = news.process_news(st, art, NewsAI(), publish=True)
    assert r2["status"] == "published" and len(sent) == 1
    # третий прогон: публиковать нечего, повторного отправки нет
    r3 = news.process_news(st, art, NewsAI(), publish=True)
    assert r3 is None and len(sent) == 1
    assert st.db.execute("SELECT COUNT(*) c FROM publications WHERE content_type='news'") \
               .fetchone()["c"] == 1


def test_invented_number_rejected(env, fake_news_http):
    st, art = env
    bad = NewsAI()
    bad.payload = dict(bad.payload, summary_ru="Банк сократил расходы на 973 процента. "
                       "Это подтвердил отчёт. Итог превзошёл ожидания.")
    row = news.process_news(st, art, bad, publish=False)
    assert row["status"] == "review" and "numbers" in row["reason"]


def test_irrelevant_news_rejected(env, fake_news_http, monkeypatch):
    art_html = "<html><head><title>Рецепт пиццы маргарита дома</title></head><body><p>%s</p></body></html>" % (
        "Рецепт пиццы маргарита дома. " * 40)

    def fake_fetch(url, *a, **k):
        if url.rstrip("/").endswith("/news"):
            return 200, LISTING_HTML
        return 200, art_html
    monkeypatch.setattr(news.httpclient, "fetch", fake_fetch)
    st, art = env
    row = news.process_news(st, art, NewsAI(), publish=False)
    assert row and row["status"] == "rejected" and "not AI" in row["reason"]


def test_news_failure_does_not_break_cases(env, fake_news_http, monkeypatch):
    """NEWS-источник недоступен — обычный case-контур публикуется."""
    st, art = env
    monkeypatch.setattr(config, "BOT_TOKEN", "123:TEST")

    def dead(url, *a, **k):
        raise httpclient.FetchError("news source down")
    monkeypatch.setattr(news.httpclient, "fetch", dead)
    # 5 case-публикаций => news due, но источник мёртв
    for i in range(5):
        mid = st.add("https://x.ru/case/%d" % i, "mindbox")
        st.update(mid, status="post_ready")
        st.mark_published(mid, 910 + i, "-100", "case-%d" % i, content_type="case")
    # пустой backlog/candidates: run не должен упасть
    monkeypatch.setattr(config, "SOURCES", [])
    s = pipeline.run(dry_run=False, publish=True, limit=1, provider=ai.NullProvider(),
                     storage=st, log_to_console=False)
    assert "run_dir" in s  # живой pipeline, несмотря на мёртвый news-источник
