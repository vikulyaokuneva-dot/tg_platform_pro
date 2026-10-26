# -*- coding: utf-8 -*-
"""PETS 4.2 queue regressions: only verified factual drafts may be automatic."""
from case_pipeline import pets
from case_pipeline import config
from case_pipeline.pets_candidates import candidate_adapters_for
from case_pipeline.pets_facts import Fact
from case_pipeline.pets_generator import MockPetsGenerator
from case_pipeline.pets_storage import PetsStorage
from core.context import JobContext
from jobs.pets import job as pets_job
from tests.test_pets_31 import _RealFixtureGenerator, _image


def _candidate(url="https://pmc.ncbi.nlm.nih.gov/articles/PMC42/", key="cat-enrichment-42"):
    fact = Fact(topic="Домашняя кошка и обогащение среды", species="cat",
                claim="В исследовании владельцы наблюдали больше исследовательского поведения кошек при доступной среде.",
                source_url=url, source_name="PMC OA", source_type="primary_research",
                author_or_body="Example Author", license="CC_BY", adaptation_allowed=True,
                evidence_level="primary_research", source_section="Results", fact_kind="study_result")
    return {"source_key": "pmc:" + key, "source_id": "pmc_oa", "title": "Домашняя кошка и среда",
            "species": "cat", "category": "enrichment", "topic_key": key,
            "editorial_status": "editorially_ready", "facts": (fact,)}


def test_verified_factual_candidate_enters_database_backed_queue(tmp_path):
    st = PetsStorage(str(tmp_path / "pets42.db"))
    result = pets.replenish_verified_queue(
        st, [_candidate()], generator=_RealFixtureGenerator(), image_resolver=lambda *_: _image(tags=("cat", "home", "owner")),
        target_ready=1, replenish_below=1)
    assert result["post_ready"] == 1
    assert result["queue_after"] == 1
    queued = st.queued_materials()
    assert len(queued) == 1
    assert queued[0]["source"] == "pmc_oa"
    assert queued[0]["origin"] == "verified_factual"


def test_mock_text_never_enters_automatic_queue(tmp_path):
    st = PetsStorage(str(tmp_path / "pets42.db"))
    result = pets.replenish_verified_queue(
        st, [_candidate()], generator=MockPetsGenerator(), image_resolver=lambda *_: _image(tags=("cat", "home", "owner")),
        target_ready=1, replenish_below=1)
    assert result["review"] == 1
    assert st.queued_count() == 0


def test_unverified_candidate_is_not_sent_to_generation_or_queue(tmp_path):
    st = PetsStorage(str(tmp_path / "pets42.db"))
    candidate = _candidate()
    candidate["editorial_status"] = "needs_editorial_review"
    result = pets.replenish_verified_queue(st, [candidate], generator=_RealFixtureGenerator(), target_ready=1, replenish_below=1)
    assert result["review"] == 1
    assert st.queued_count() == 0


def test_duplicate_replenishment_does_not_create_duplicate_queue_rows(tmp_path):
    st = PetsStorage(str(tmp_path / "pets42.db"))
    first = pets.replenish_verified_queue(
        st, [_candidate()], generator=_RealFixtureGenerator(), image_resolver=lambda *_: _image(tags=("cat", "home", "owner")),
        target_ready=2, replenish_below=5)
    second = pets.replenish_verified_queue(
        st, [_candidate()], generator=_RealFixtureGenerator(), image_resolver=lambda *_: _image(tags=("cat", "home", "owner")),
        target_ready=2, replenish_below=5)
    assert first["queue_after"] == 1
    assert second["queue_after"] == 1
    assert len(st.queued_materials()) == 1


def test_legacy_curated_or_demo_row_cannot_be_enqueued(tmp_path):
    st = PetsStorage(str(tmp_path / "pets42.db"))
    mid = st.add("draft://pets/legacy-demo", "curated_original")
    st.update(mid, status="post_ready", post_text="demo")
    assert st.enqueue_verified_material(mid) is False
    assert st.queued_count() == 0


def test_unknown_or_forbidden_source_has_no_candidate_adapter():
    assert candidate_adapters_for(("purina", "cats_protection", "unknown")) == {}


def test_source_only_job_does_not_mutate_production_queue_without_opt_in(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PETS_DB_PATH", str(tmp_path / "production.db"))
    monkeypatch.setattr(config, "PETS_CANDIDATES_DB_PATH", str(tmp_path / "candidates.db"))
    monkeypatch.setattr(config, "RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setattr(config, "PETS_EXTERNAL_SOURCES", True)
    monkeypatch.setattr(config, "PETS_ALLOW_PRODUCTION_QUEUE", False)
    monkeypatch.setattr(config, "PETS_GENERATOR_MODE", "mock")
    monkeypatch.setattr(config, "PETS_PUBLISH", False)
    monkeypatch.setattr(config, "PETS_STATE_BACKEND", "cache")
    monkeypatch.setattr(pets_job, "candidate_adapters_for", lambda _: {})
    ctx = JobContext("pets", str(tmp_path / "storage.json"), dry_run=True)
    pets_job.run(ctx)
    assert ctx.storage["last_run"]["autonomous"]["blocked"] == "production_queue_opt_in_required"
    assert PetsStorage(config.PETS_DB_PATH).queued_count() == 0
