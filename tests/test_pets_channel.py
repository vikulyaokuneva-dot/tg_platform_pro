# -*- coding: utf-8 -*-
from datetime import datetime, timedelta, timezone

import pytest

from case_pipeline import config, pets, pets_sources, pets_state, telegram
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
            "attribution": "Jane Doe / CC BY 4.0", "breed": breed}


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


def test_pets_uses_own_credentials(monkeypatch):
    monkeypatch.setattr(config, "PETS_BOT_TOKEN", "pets-token")
    monkeypatch.setattr(config, "PETS_CHAT_ID", "-100pets")
    monkeypatch.setattr(config, "AGRO_BOT_TOKEN", "agro-token")
    assert telegram.credentials("pets") == ("pets-token", "-100pets")


def test_all_ten_sources_are_registry_candidates_not_default_enabled():
    assert len(pets_sources.SOURCE_CANDIDATES) == 10
    assert config.PETS_SOURCES == []
    assert set(pets_sources.adapters_for(["pdsa", "merck_vet"])) == {"pdsa", "merck_vet"}


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


def test_pets_job_empty_dry_run_has_no_side_effects(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PETS_DB_PATH", str(tmp_path / "state.db"))
    monkeypatch.setattr(config, "PETS_SOURCES", [])
    monkeypatch.setattr(config, "PETS_PUBLISH", False)
    ctx = JobContext("pets", str(tmp_path / "job.json"), dry_run=True)
    pets_job.run(ctx)
    assert ctx.storage["last_run"]["checked"] == 0
    assert ctx.storage["last_run"]["dry_run"] is True
