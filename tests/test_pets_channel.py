# -*- coding: utf-8 -*-
from datetime import datetime, timedelta, timezone

import pytest

from case_pipeline import config, pets, pets_briefs, pets_sources, pets_state, telegram
from case_pipeline.pets_storage import PetsStorage
from core.context import JobContext
from jobs.pets import job as pets_job


URL = "https://example.test/pets/cat-stress"
TEXT = ("Кошки могут испытывать стресс при резких изменениях привычной среды. "
        "Спокойное место для отдыха, предсказуемый режим и постепенное знакомство с новым животным "
        "помогают владельцу снизить нагрузку на питомца. Наблюдайте за аппетитом и поведением, "
        "а при стойких изменениях обратитесь в ветеринарную клинику. "
        "Не используйте наказание: оно усиливает тревогу и не устраняет причину. "
        "Подготовьте отдельные миски, укрытие и безопасную дистанцию для каждого животного.")


def _ext(language="ru", title="Как заметить стресс у кошки"):
    return {"text": TEXT, "title": title, "quality": "good", "language": language,
            "published_at": "2026-10-20T10:00:00Z", "suspect_captcha": False}


def _image(breed=""):
    return {"url": "https://commons.example.test/cat.jpg", "author": "Jane Doe",
            "source_url": "https://commons.example.test/file/cat", "license": "CC-BY-4.0",
            "license_url": "https://creativecommons.org/licenses/by/4.0/",
            "attribution": "Jane Doe / CC BY 4.0", "query": "domestic cat",
            "topic_match": "species+safe_shelter", "semantic_tags": ("cat", "safe_shelter"),
            "required_tags": ("cat", "safe_shelter"), "semantic_evidence": "fixture", "breed": breed}


@pytest.fixture
def st(tmp_path):
    db = PetsStorage(str(tmp_path / "pets.db"))
    yield db
    db.close()


@pytest.fixture
def prepared(monkeypatch):
    monkeypatch.setattr(pets.extraction, "extract_from_html", lambda html, url: _ext())
    return lambda url, **kw: (200, "<html>fixture</html>")


def test_pets_dry_run_prepares_but_never_sends(st, prepared, monkeypatch):
    calls = []
    monkeypatch.setattr(telegram, "publish_post", lambda *a, **kw: calls.append(a))
    result = pets.process_url(st, URL, "pdsa", dry_run=True, image_resolver=lambda *_: _image(), fetcher=prepared)
    assert result["status"] == "post_ready"
    assert not calls
    assert st.get(st.add(URL, "pdsa"))["status"] == "post_ready"


def test_unlicensed_or_missing_image_is_review(st, prepared):
    result = pets.process_url(st, URL, "pdsa", image_resolver=lambda *_: None, fetcher=prepared)
    assert result["status"] == "review" and result["reason"] == "image_rights"


def test_species_only_image_is_reviewed_not_accepted(st, prepared):
    image = _image()
    image.pop("semantic_tags")
    image.pop("required_tags")
    image.pop("semantic_evidence")
    result = pets.process_url(st, URL, "pdsa", image_resolver=lambda *_: image, fetcher=prepared)
    assert result["status"] == "review" and result["reason"] == "image_rights"


def test_non_russian_source_requires_approved_editor(st, prepared, monkeypatch):
    monkeypatch.setattr(pets.extraction, "extract_from_html", lambda html, url: _ext(language="en"))
    result = pets.process_url(st, URL, "merck_vet", image_resolver=lambda *_: _image(), fetcher=prepared)
    assert result["reason"] == "translation_requires_editor"


def test_veterinary_dosage_is_sent_to_review(st, prepared, monkeypatch):
    unsafe = _ext()
    unsafe["text"] += " Дозировка лекарства составляет 5 мг/кг."
    monkeypatch.setattr(pets.extraction, "extract_from_html", lambda html, url: unsafe)
    result = pets.process_url(st, URL, "pdsa", image_resolver=lambda *_: _image(), fetcher=prepared)
    assert result["status"] == "review" and result["reason"] == "editorial_safety"


def test_semantic_duplicate_is_rejected(st, prepared):
    one = pets.process_url(st, URL, "pdsa", image_resolver=lambda *_: _image(), fetcher=prepared)
    two = pets.process_url(st, URL + "-second", "pdsa", image_resolver=lambda *_: _image(), fetcher=prepared)
    assert one["status"] == "post_ready"
    assert two["status"] == "rejected" and two["reason"] == "duplicate_topic"


def test_real_publish_is_blocked_without_durable_state(st, prepared, monkeypatch):
    monkeypatch.setattr(config, "PETS_REQUIRE_DURABLE_STATE", True)
    monkeypatch.setattr(config, "PETS_STATE_BACKEND", "cache")
    monkeypatch.setattr(config, "PETS_PUBLISH", True)
    monkeypatch.setattr(telegram, "publish_post", lambda *a, **kw: pytest.fail("must not send"))
    result = pets.process_url(st, URL, "pdsa", publish=True, dry_run=False,
                              image_resolver=lambda *_: _image(), fetcher=prepared)
    assert result["reason"] == "durable_state_required"


def test_telegram_error_is_uncertain_review_not_retry(st, prepared, monkeypatch):
    monkeypatch.setattr(config, "PETS_REQUIRE_DURABLE_STATE", False)
    monkeypatch.setattr(config, "PETS_STATE_BACKEND", "durable")
    monkeypatch.setattr(config, "PETS_PUBLISH", True)
    monkeypatch.setattr(pets.httpclient, "fetch_bytes", lambda url: b"x" * 20000)
    monkeypatch.setattr(telegram, "publish_post", lambda *a, **kw: telegram.PublishResult(False, error="timeout"))
    result = pets.process_url(st, URL, "pdsa", publish=True, dry_run=False,
                              image_resolver=lambda *_: _image(), fetcher=prepared)
    assert result["reason"] == "telegram_delivery_uncertain"
    assert st.get(st.add(URL, "pdsa"))["status"] == "review"


def test_pets_reuses_shared_bot_with_own_chat(monkeypatch):
    monkeypatch.setattr(config, "BOT_TOKEN", "shared-token")
    monkeypatch.setattr(config, "PETS_CHAT_ID", "-100pets")
    monkeypatch.setattr(config, "AGRO_BOT_TOKEN", "shared-token")
    monkeypatch.setattr(config, "AGRO_CHAT_ID", "-100agro")
    assert telegram.credentials("pets") == ("shared-token", "-100pets")
    assert telegram.credentials("agro") == ("shared-token", "-100agro")


def test_pets_preflight_requires_an_administrator_without_exposing_credentials(monkeypatch):
    monkeypatch.setattr(config, "BOT_TOKEN", "shared-token")
    monkeypatch.setattr(config, "PETS_CHAT_ID", "-100pets")

    class Response:
        content = b"{}"
        status_code = 200
        def __init__(self, payload):
            self.payload = payload
        def json(self):
            return self.payload

    responses = iter((
        {"ok": True, "result": {"id": 77, "username": "manager_bot"}},
        {"ok": True, "result": {"type": "channel"}},
        {"ok": True, "result": {"status": "administrator"}},
    ))
    monkeypatch.setattr(telegram.requests, "get", lambda *args, **kwargs: Response(next(responses)))
    result = telegram.pets_channel_preflight()
    assert result == {"ok": True, "credentials_configured": True,
                      "bot_username": "manager_bot", "chat_type": "channel",
                      "membership": "administrator"}
    assert "shared-token" not in repr(result)
    assert "-100pets" not in repr(result)


def test_evergreen_publish_records_one_delivery_and_never_retries_after_checkpoint_failure(st, monkeypatch):
    brief = pets_briefs.EVERGREEN_BRIEFS[0]
    monkeypatch.setattr(config, "PETS_REQUIRE_DURABLE_STATE", True)
    monkeypatch.setattr(config, "PETS_STATE_BACKEND", "github")
    monkeypatch.setattr(config, "PETS_PUBLISH", True)
    monkeypatch.setattr(pets.httpclient, "fetch_bytes", lambda _url: b"image")
    sent = []
    monkeypatch.setattr(telegram, "publish_post", lambda *args, **kwargs: sent.append(1) or telegram.PublishResult(True, message_id=501))
    phases = []
    def checkpoint(phase):
        phases.append(phase)
        if phase == "published":
            raise RuntimeError("state unavailable after send")
    first = pets.process_evergreen_brief(st, brief, publish=True, dry_run=False, checkpoint=checkpoint)
    assert first["status"] == "published"
    assert first["telegram_message_id"] == 501
    assert first["durable_state"] == "checkpoint_failed_after_send"
    assert sent == [1]
    assert st.seen_url("draft://pets/" + brief["id"])["status"] == "published"
    second = pets.process_evergreen_brief(st, brief, publish=True, dry_run=False, checkpoint=checkpoint)
    assert second["status"] == "skipped"
    assert sent == [1]


def test_all_ten_sources_are_registry_candidates_not_default_enabled():
    assert len(pets_sources.SOURCE_CANDIDATES) == 10
    assert config.PETS_SOURCES == []
    assert pets_sources.adapters_for(["pdsa", "merck_vet"]) == {}
    assert pets_sources.policy_for("merck_vet")["mode"] == "fact_check_only"
    assert config.pets_source_ids("0") == []
    assert config.pets_source_ids("false, none, pdsa") == ["pdsa"]


def test_news_mode_rejects_stale_article(st, prepared, monkeypatch):
    stale = _ext()
    stale["published_at"] = "2020-01-01T00:00:00Z"
    monkeypatch.setattr(pets.extraction, "extract_from_html", lambda html, url: stale)
    monkeypatch.setattr(config, "PETS_CONTENT_MODE", "news")
    result = pets.process_url(st, URL, "pdsa", image_resolver=lambda *_: _image(), fetcher=prepared)
    assert result["status"] == "rejected" and result["reason"] == "stale_news"


def test_stale_publishing_claim_is_quarantined(st):
    mid = st.add(URL, "pdsa")
    st.update(mid, status="post_ready")
    assert st.claim_for_publish(mid)
    old = (datetime.now(timezone.utc) - timedelta(minutes=90)).strftime("%Y-%m-%dT%H:%M:%SZ")
    st.db.execute("UPDATE materials SET updated_at=? WHERE id=?", (old, mid))
    st.db.commit()
    assert st.quarantine_stale_claims(minutes=60) == 1
    assert st.get(mid)["status"] == "review"


def test_sqlite_state_survives_reopen_and_corruption_is_detected(tmp_path):
    path = tmp_path / "pets.db"
    first = PetsStorage(str(path))
    mid = first.add(URL, "pdsa")
    assert first.reserve_topic(mid, "cat stress", "behavior", "cat")
    first.close()
    second = PetsStorage(str(path))
    assert second.topic_seen("cat stress") is not None
    second.close()
    assert pets_state.inspect(str(path))["status"] == "ready"
    bad = tmp_path / "bad.db"
    bad.write_bytes(b"not sqlite")
    assert pets_state.inspect(str(bad))["status"] == "corrupt"


def test_original_briefs_are_manual_review_drafts_with_open_images(st):
    results = [pets.process_original_brief(st, brief) for brief in pets_briefs.DEFAULT_BRIEFS]
    assert [result["status"] for result in results] == ["demo_ready"] * 3
    for result in results:
        row = st.get(st.add(result["url"], "curated_original"))
        rights = st.db.execute("SELECT license,license_url,author FROM pets_image_rights WHERE material_id=?",
                               (row["id"],)).fetchone()
        assert row["status"] == "demo_ready"
        assert "Проверка фактов:" in row["post_text"]
        assert rights["license"] in {"CC-BY-4.0", "CC-BY-SA-4.0", "CC0-1.0", "Public-Domain"}
        assert rights["license_url"] and rights["author"]


def test_original_briefs_never_send_even_when_publish_is_requested(st, monkeypatch):
    monkeypatch.setattr(config, "PETS_PUBLISH", True)
    monkeypatch.setattr(telegram, "publish_post", lambda *a, **kw: pytest.fail("original drafts must not send"))
    summary = pets.run(dry_run=False, publish=True, st=st, sources=[], adapters={},
                       briefs=pets_briefs.DEFAULT_BRIEFS)
    assert summary["demo_ready"] == 3
    assert summary["published"] == 0


def test_evergreen_queue_excludes_all_demo_briefs():
    demo_ids = {brief["id"] for brief in pets_briefs.DEFAULT_BRIEFS}
    evergreen_ids = {brief["id"] for brief in pets_briefs.EVERGREEN_BRIEFS}
    assert evergreen_ids
    assert demo_ids.isdisjoint(evergreen_ids)


def test_existing_state_quarantines_only_curated_rows_outside_evergreen_allowlist(st):
    demo_url = "draft://pets/" + pets_briefs.DEFAULT_BRIEFS[1]["id"]
    allowed_url = "draft://pets/" + pets_briefs.EVERGREEN_BRIEFS[0]["id"]
    published_url = "draft://pets/" + pets_briefs.DEFAULT_BRIEFS[0]["id"]
    demo_id = st.add(demo_url, "curated_original")
    allowed_id = st.add(allowed_url, "curated_original")
    published_id = st.add(published_url, "curated_original")
    st.update(demo_id, status="post_ready")
    st.update(allowed_id, status="post_ready")
    st.update(published_id, status="published")
    assert st.migrate_demo_materials((allowed_url,)) == 1
    assert st.get(demo_id)["status"] == "demo_ready"
    assert st.get(allowed_id)["status"] == "post_ready"
    assert st.get(published_id)["status"] == "published"


def test_demo_brief_is_rejected_by_automatic_evergreen_path(st, monkeypatch):
    monkeypatch.setattr(telegram, "publish_post", lambda *a, **kw: pytest.fail("demo must not send"))
    result = pets.process_evergreen_brief(st, pets_briefs.DEFAULT_BRIEFS[0], publish=True, dry_run=False)
    assert result == {"source": "curated_original", "status": "rejected",
                      "reason": "evergreen_not_allowlisted"}


def test_existing_demo_rows_are_migrated_out_of_automatic_ready(st):
    mid = st.add("draft://pets/old-demo", "curated_original")
    st.update(mid, status="post_ready")
    assert st.migrate_demo_materials() == 1
    assert st.get(mid)["status"] == "demo_ready"


def test_pets_publication_ledger_omits_chat_id(st):
    mid = st.add("draft://pets/ledger-test", "curated_original")
    st.update(mid, content_hash="safe", status="post_ready")
    st.mark_pets_published(mid, 42, "pets-ledger-test")
    row = st.db.execute("SELECT chat_id, content_type FROM publications WHERE material_id=?", (mid,)).fetchone()
    assert row["chat_id"] is None
    assert row["content_type"] == "pets"


def test_pets_job_dry_run_creates_review_drafts_without_sending(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PETS_DB_PATH", str(tmp_path / "state.db"))
    monkeypatch.setattr(config, "PETS_SOURCES", [])
    monkeypatch.setattr(config, "PETS_PUBLISH", False)
    monkeypatch.setattr(config, "PETS_DEMO_BRIEFS", True)
    monkeypatch.setattr(pets_job, "_download_preview_images", lambda *args, **kwargs: [])
    monkeypatch.setattr(pets_job, "_write_preview", lambda *args, **kwargs: None)
    ctx = JobContext("pets", str(tmp_path / "job.json"), dry_run=True)
    pets_job.run(ctx)
    assert ctx.storage["last_run"]["checked"] == 3
    assert ctx.storage["last_run"]["post_ready"] == 0
    assert ctx.storage["last_run"]["demo_ready"] == 3
    assert ctx.storage["last_run"]["published"] == 0
    assert ctx.storage["last_run"]["dry_run"] is True
