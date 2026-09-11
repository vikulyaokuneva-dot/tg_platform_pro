# -*- coding: utf-8 -*-
"""Publication history: hard dedup (url/hash/case_id), soft dedup, счётчик
«Новость дня», race-safe claim, восстановление зависших захватов."""
import pytest

from case_pipeline import storage as storage_mod


@pytest.fixture()
def st(tmp_path):
    return storage_mod.Storage(str(tmp_path / "hist.db"))


def _mat(st, url, company=None, status="published", conf=0.8):
    mid = st.add(url, "mindbox")
    st.update(mid, status="post_ready", company=company, confidence=conf,
              content_hash="h-" + url[-5:], post_text="текст поста " + url)
    return mid


def test_publication_record_fields(st):
    mid = _mat(st, "https://x.ru/case/one/", company="Mindbox")
    st.mark_published(mid, 501, "-100", "case-one",
                      hashtags="#Кейс #CRM #Mindbox", content_type="case")
    p = st.db.execute("SELECT * FROM publications WHERE ok=1").fetchone()
    assert p["telegram_message_id"] == 501 and p["case_id"] == "case-one"
    assert p["hashtags"] == "#Кейс #CRM #Mindbox"
    assert p["content_type"] == "case" and p["company"] == "Mindbox"
    assert p["canonical_url"] == "https://x.ru/case/one"
    assert p["published_at"] and p["status"] == "ok" and p["id"]  # publication_id


def test_hard_dedup_case_id(st):
    mid = _mat(st, "https://x.ru/case/two/", company="IBM")
    st.mark_published(mid, 502, "-100", "case-two")
    assert st.case_published("case-two")
    assert not st.case_published("case-never")
    assert "case-two" in st.published_case_ids()


def test_counter_only_successful_cases(st):
    for i in range(4):
        mid = _mat(st, "https://x.ru/case/%d" % i, company="C%d" % i)
        st.mark_published(mid, 600 + i, "-100", "case-%d" % i, content_type="case")
    assert st.count_cases_since_last_news() == 4
    # news-публикация сбрасывает счётчик
    mid = _mat(st, "https://x.ru/news/z", company="N")
    st.mark_published(mid, 700, "-100", "news-z", content_type="news")
    assert st.count_cases_since_last_news() == 0
    # неуспешные (ok=0) не считаются
    st.db.execute("INSERT INTO publications(material_id,case_id,source_url,published_at,"
                  "ok,content_type) VALUES(99,'c-x','https://x.ru','2026-01-01T00:00:00Z',0,'case')")
    st.db.commit()
    assert st.count_cases_since_last_news() == 0


def test_recent_companies_window(st):
    mid = _mat(st, "https://x.ru/case/m/", company="Microsoft")
    st.mark_published(mid, 800, "-100", "case-m")
    assert "microsoft" in st.recent_companies(days=7)
    assert "microsoft" not in st.recent_companies(days=-1)  # окно в прошлом => пусто
    # старая публикация из окна выпадает
    st.db.execute("UPDATE publications SET published_at='2020-01-01T00:00:00Z'")
    st.db.commit()
    assert "microsoft" not in st.recent_companies(days=7)


def test_claim_race_safety(st, tmp_path):
    mid = _mat(st, "https://x.ru/case/race/", company="R")
    st2 = storage_mod.Storage(st.path)  # второй «процесс»
    assert st.claim_for_publish(mid) is True
    assert st2.claim_for_publish(mid) is False  # параллельный не получит
    st2.close()


def test_release_and_stale_recovery(st):
    mid = _mat(st, "https://x.ru/case/stale/", company="S")
    assert st.claim_for_publish(mid)
    st.release_claim(mid, "review", "telegram error")
    assert st.get(mid)["status"] == "review"
    # зависший publishing -> post_ready
    st.update(mid, status="post_ready")
    assert st.claim_for_publish(mid)
    st.db.execute("UPDATE materials SET updated_at='2020-01-01T00:00:00Z' WHERE id=?", (mid,))
    st.db.commit()
    assert st.recover_stale_claims(minutes=60) == 1
    assert st.get(mid)["status"] == "post_ready"
