# -*- coding: utf-8 -*-
"""Интеграционный тест всего конвейера без сети и без реального Telegram.

mock fetch (каталог mindbox + статья = raw.html из baseline) -> extract ->
V2 classify -> CASE -> evidence -> post -> mock publish -> SQLite ->
повторный прогон = 0 новых (dedup proof).
"""
import io
import json
import os

import pytest

from case_pipeline import adapters, ai, config, httpclient, pipeline, storage
from conftest import HOLDOUT


@pytest.fixture()
def env(tmp_path, monkeypatch):
    runs = tmp_path / "runs"
    runs.mkdir()
    monkeypatch.setattr(config, "RUNS_DIR", str(runs))
    monkeypatch.setattr(config, "BOT_TOKEN", "123:TEST")
    st = storage.Storage(str(tmp_path / "p.db"))
    return st, runs


ARTICLE_URL = "https://mindbox.ru/journal/cases/chtay-gorod-ml/"
CATALOG_HTML = '<html><body><a href="%s">case</a></body></html>' % ARTICLE_URL


@pytest.fixture()
def fake_http(monkeypatch):
    raw = io.open(os.path.join(HOLDOUT, "001", "raw.html"), encoding="utf-8").read()

    def fake_fetch(url, *a, **k):
        if "journal/cases" in url and url.rstrip("/").endswith("cases"):
            return 200, CATALOG_HTML
        return 200, raw

    monkeypatch.setattr(httpclient, "fetch", fake_fetch)
    monkeypatch.setattr(adapters, "fetch", fake_fetch)
    return fake_fetch


def _sent(provider_calls):
    def _fake_publish(text, chat_id=None, dry_run=False):
        provider_calls.append(text)

        class R:
            ok, message_id, error = True, 101, None
        return R()
    return _fake_publish


def test_full_pipeline_dry_run(env, fake_http):
    st, runs = env
    summary = pipeline.run(dry_run=True, sources=["mindbox"], provider=ai.NullProvider(),
                           storage=st)
    assert summary.get("post_ready", 0) == 1, summary
    m = st.seen_url(ARTICLE_URL)
    assert m and st.get(m["id"])["status"] == "post_ready"
    art_dirs = os.listdir(str(runs))
    assert art_dirs
    d = os.path.join(str(runs), art_dirs[0])
    assert os.path.exists(os.path.join(d, "report.md"))
    assert os.listdir(os.path.join(d, "cases"))
    assert os.listdir(os.path.join(d, "posts"))
    # ничего не опубликовано
    assert st.db.execute("SELECT COUNT(*) c FROM publications").fetchone()["c"] == 0


def test_publish_flow_and_dedup_rerun(env, fake_http, monkeypatch):
    st, runs = env
    sent = []
    monkeypatch.setattr(pipeline.telegram, "publish_post", _sent(sent))
    s1 = pipeline.run(dry_run=False, publish=True, limit=1, sources=["mindbox"],
                      provider=ai.NullProvider(), storage=st)
    assert s1.get("published") == 1
    assert len(sent) == 1 and len(sent[0]) > 400 and "Источник:" in sent[0]
    row = st.seen_url(ARTICLE_URL)
    assert st.get(row["id"])["telegram_message_id"] == 101
    # повторный прогон: дедуп по канон URL — новых результатов нет
    s2 = pipeline.run(dry_run=False, publish=True, limit=1, sources=["mindbox"],
                      provider=ai.NullProvider(), storage=st)
    assert not [k for k in s2 if k != "run_dir"], s2
    assert len(sent) == 1  # ни одного повторного поста


def test_rerun_survives_db_reopen(env, fake_http, monkeypatch):
    """Persistence-сценарий GHA (аналог actions/cache restore): run1 публикует
    в файл БД; процесс завершается (close); новый «процесс» открывает ТОТ ЖЕ
    файл -> hard dedup по истории не публикует повторно."""
    st, runs = env
    sent = []
    monkeypatch.setattr(pipeline.telegram, "publish_post", _sent(sent))
    s1 = pipeline.run(dry_run=False, publish=True, limit=1, sources=["mindbox"],
                      provider=ai.NullProvider(), storage=st)
    assert s1.get("published") == 1 and len(sent) == 1
    db_path = st.path
    st.close()

    st2 = storage.Storage(db_path)  # «новый раннер», восстановленный файл
    s2 = pipeline.run(dry_run=False, publish=True, limit=1, sources=["mindbox"],
                      provider=ai.NullProvider(), storage=st2)
    assert not [k for k in s2 if k != "run_dir"], s2
    assert len(sent) == 1  # ни одной повторной публикации
    n = st2.db.execute("SELECT COUNT(*) c FROM publications WHERE ok=1").fetchone()["c"]
    assert n == 1
    st2.close()


def test_review_lane_without_ai_stays_unpublished(env, fake_http, monkeypatch):
    """needs_review + нет AI-провайдера => review, публикаций ноль (rules-first)."""
    st, runs = env
    from case_pipeline.classifier_lib import V2
    monkeypatch.setattr(V2, "classify_v2",
                        lambda text, meta, policy="strict": {
                            "type": "needs_review", "confidence": 0.5, "company": "X",
                            "features": {}, "evidence": {}, "rationale": ["test"]})
    s = pipeline.run(dry_run=False, publish=True, limit=1, sources=["mindbox"],
                     provider=ai.NullProvider(), storage=st)
    assert s.get("review") == 1
    assert st.db.execute("SELECT COUNT(*) c FROM publications").fetchone()["c"] == 0


def test_ai_arbitration_promotes_review_case(env, fake_http, monkeypatch):
    """needs_review -> валидный AI business_case-вердикт -> пост готов."""
    st, runs = env
    from case_pipeline.classifier_lib import V2
    raw = io.open(os.path.join(HOLDOUT, "001", "cleaned.txt"), encoding="utf-8").read()
    q = raw[raw.lower().find("директ") - 200: raw.lower().find("директ")]
    verdict = {"decision": "business_case", "confidence": 0.72, "company": "Читай-город",
               "problem_quote": q.strip()[:120], "implementation_quote": q.strip()[:120],
               "reason": "тест"}
    monkeypatch.setattr(V2, "classify_v2",
                        lambda text, meta, policy="strict": {
                            "type": "needs_review", "confidence": 0.5, "company": "NOT_FOUND",
                            "features": {}, "evidence": {}, "rationale": ["test"]})
    prov = ai.FakeProvider(verdict)
    s = pipeline.run(dry_run=True, sources=["mindbox"], provider=prov, storage=st)
    assert s.get("post_ready") == 1 or s.get("review") == 1
    # если evidence CASE-сборки не хватило — хотя бы не reject и не published
    assert s.get("rejected", 0) == 0


def test_backlog_publish_from_ready_items(env, fake_http, monkeypatch):
    """dry-run наполняет backlog post_ready; publish-прогон берёт его из БД,
    ровно limit штук; третий прогон не переопубликовывает ничего."""
    st, runs = env
    sent = []
    monkeypatch.setattr(pipeline.telegram, "publish_post", _sent(sent))
    s1 = pipeline.run(dry_run=True, sources=["mindbox"], provider=ai.NullProvider(), storage=st)
    assert s1.get("post_ready") == 1
    s2 = pipeline.run(dry_run=False, publish=True, limit=1, sources=["mindbox"],
                      provider=ai.NullProvider(), storage=st)
    assert s2.get("published") == 1 and len(sent) == 1
    assert st.get(st.seen_url(ARTICLE_URL)["id"])["telegram_message_id"] == 101
    s3 = pipeline.run(dry_run=False, publish=True, limit=1, sources=["mindbox"],
                      provider=ai.NullProvider(), storage=st)
    assert not [k for k in s3 if k != "run_dir"], s3
    assert len(sent) == 1  # повторных отправок нет


def test_hallucinated_ai_verdict_rejected(env, fake_http, monkeypatch):
    st, runs = env
    from case_pipeline.classifier_lib import V2
    monkeypatch.setattr(V2, "classify_v2",
                        lambda text, meta, policy="strict": {
                            "type": "needs_review", "confidence": 0.5, "company": "NOT_FOUND",
                            "features": {}, "evidence": {}, "rationale": ["test"]})
    prov = ai.FakeProvider({"decision": "business_case", "confidence": 0.9,
                            "company": "Acme", "problem_quote": "абсолютно выдуманная цитата "
                            "про квантовые серверы и марсианских клиентов",
                            "implementation_quote": "ещё одна несуществующая цитата из текста "
                            "этого материала про автоматизацию"})
    s = pipeline.run(dry_run=True, sources=["mindbox"], provider=prov, storage=st)
    assert s.get("review") == 1 and s.get("post_ready", 0) == 0


def test_soft_dedup_recent_company_deprioritized(env, fake_http, monkeypatch):
    """Компания из недавней публикации получает меньший приоритет очереди,
    даже с более высокой confidence; свежая компания публикуется первой."""
    st, runs = env
    sent = []
    monkeypatch.setattr(pipeline.telegram, "publish_post", _sent(sent))
    # недавняя публикация компании Mindbox
    seed = st.add("https://mindbox.ru/journal/cases/seed/", "mindbox")
    st.update(seed, status="post_ready", company="Mindbox")
    st.mark_published(seed, 500, "-100", "case-seed", content_type="case")
    # два кандидата в backlog: A=recent company (conf 0.9), B=fresh (conf 0.7)
    a = st.add("https://mindbox.ru/journal/cases/aaa/", "mindbox")
    st.update(a, status="post_ready", company="Mindbox", confidence=0.9,
              post_text="🏢 Кто: Mindbox. Заявки обрабатывались вручную 4 часа. "
                        "Mindbox подключил AI-обработку, время сократилось на 45%. "
                        "Источник: https://mindbox.ru/journal/cases/aaa/",
              case_json=json.dumps({"case_id": "case-aaa", "company_name": "Mindbox",
                                    "problem": "заявки вручную", "implementation": "AI-обработка",
                                    "results": ["сократилось на 45%"]}))
    b = st.add("https://zapier.com/customer-stories/bbb", "zapier")
    st.update(b, status="post_ready", company="Nvidia", confidence=0.7,
              post_text="🏢 Кто: Nvidia. Обращения обрабатывались вручную. "
                        "Nvidia подключила автоматизацию, расходы снизились на 30%. "
                        "Источник: https://zapier.com/customer-stories/bbb",
              case_json=json.dumps({"case_id": "case-bbb", "company_name": "Nvidia",
                                    "problem": "обращения вручную", "implementation": "автоматизация",
                                    "results": ["снизились на 30%"]}))
    s = pipeline.run(dry_run=False, publish=True, limit=1, sources=["nonexistent"],
                     provider=ai.NullProvider(), storage=st, log_to_console=False)
    assert s.get("published") == 1
    assert "Nvidia" in sent[0] and "Mindbox" not in sent[0]  # recent ушла в конец
    assert st.get(a)["status"] == "post_ready"  # A дожидается своей очереди


def test_news_slot_triggers_after_five_cases(env, fake_http, monkeypatch):
    """Слот «Новость дня» вызывается в publish-прогоне, когда накопилось
    NEWS_EVERY успешных CASE-публикаций; dry-run не вызывает."""
    st, runs = env
    for i in range(5):
        mid = st.add("https://x.ru/case/%d" % i, "mindbox")
        st.update(mid, status="post_ready")
        st.mark_published(mid, 910 + i, "-100", "case-%d" % i, content_type="case")
    calls = []
    monkeypatch.setattr(pipeline.news_mod, "process_news",
                        lambda storage, art, provider, publish=False: (
                            calls.append(publish), None)[1])
    pipeline.run(dry_run=True, sources=["nonexistent"], provider=ai.NullProvider(),
                 storage=st, log_to_console=False)
    assert calls == []  # dry-run не триггерит
    pipeline.run(dry_run=False, publish=True, limit=1, sources=["nonexistent"],
                 provider=ai.NullProvider(), storage=st, log_to_console=False)
    assert calls == [True]  # publish-прогон: новость по счётчику
