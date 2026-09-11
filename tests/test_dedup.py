# -*- coding: utf-8 -*-
"""Дедуп: канон URL (utm/#/slash/www), content hash, статусы."""
from case_pipeline.storage import Storage
from case_pipeline.utils import content_hash, norm_url


def test_norm_url_variants():
    base = norm_url("https://zapier.com/customer-stories/acme")
    for v in ("https://www.zapier.com/customer-stories/acme/",
              "https://zapier.com/customer-stories/acme/?utm_source=x",
              "https://Zapier.com/customer-stories/acme#section",
              "https://zapier.com/customer-stories/acme?"):
        assert norm_url(v) == base, v


def test_content_hash_whitespace_insensitive():
    assert content_hash("A  B\n\nC") == content_hash("a b c")
    assert content_hash("A B") != content_hash("A C")


def test_dedup_urls_single_row(tmp_path):
    st = Storage(str(tmp_path / "d.db"))
    i1 = st.add("https://mindbox.ru/journal/cases/acme/?utm_source=tg", "mindbox")
    i2 = st.add("https://www.mindbox.ru/journal/cases/acme/", "mindbox")
    assert i1 == i2


def test_content_duplicated(tmp_path):
    st = Storage(str(tmp_path / "d.db"))
    mid = st.add("https://x.test/a", "src")
    st.update(mid, content_hash=content_hash("hello world"), status="extracted")
    assert st.content_duplicated("Hello   World", exclude_id=mid + 99)
    assert not st.content_duplicated("Hello World", exclude_id=mid)
    assert not st.content_duplicated("other text", exclude_id=mid)


def test_status_lifecycle(tmp_path):
    st = Storage(str(tmp_path / "d.db"))
    mid = st.add("https://x.test/b", "src")
    st.update(mid, status="classified", classification="business_case", confidence=0.85)
    assert st.get(mid)["status"] == "classified"
    st.update(mid, status="review", reason="needs arbitration")
    assert st.by_status("review")[0]["id"] == mid


def test_publish_bookkeeping(tmp_path):
    st = Storage(str(tmp_path / "d.db"))
    mid = st.add("https://x.test/c", "src")
    st.mark_published(mid, 555, "-100", "case-abc")
    row = st.get(mid)
    assert row["status"] == "published" and row["telegram_message_id"] == 555
    pub = st.db.execute("SELECT * FROM publications").fetchall()
    assert len(pub) == 1 and pub[0]["ok"] == 1
