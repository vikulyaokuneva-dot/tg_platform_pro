# -*- coding: utf-8 -*-
"""Offline PETS 3.1 safety and source-contract regression tests."""
import xml.etree.ElementTree as ET
from case_pipeline import pets, pets_sources
from case_pipeline import config
from case_pipeline.pets_facts import Fact
from case_pipeline.pets_facts import license_terms, normalize_license
from case_pipeline.pets_generator import MockPetsGenerator
from case_pipeline.pets_planner import Topic, choose_topics
from case_pipeline.pets_candidates import FdaCvmSafetyAdapter, FrontiersVeterinaryPmcAdapter, collect_source_candidates
from case_pipeline.pets_sources import FdaCvmAdapter
from case_pipeline.pets_storage import PetsStorage
from core.context import JobContext
from jobs.pets import job as pets_job


def _fact(url="https://www.fda.gov/animal-veterinary/example", license="PUBLIC_DOMAIN", claim="Официальное предупреждение помогает владельцу проверить безопасность корма."):
    return Fact(topic="Безопасность корма", species="cat", claim=claim, source_url=url,
                source_name="FDA Center for Veterinary Medicine", source_type="government",
                author_or_body="U.S. Food and Drug Administration", license=license,
                adaptation_allowed=license == "PUBLIC_DOMAIN", evidence_level="regulatory")


def _topic(key="cat-food-safety"):
    return Topic(key, "Безопасность кошачьего корма", "nutrition", "cat", ("cat", "food", "owner"))


def _image(*, tags=("cat", "food", "owner")):
    return {"url": "https://upload.wikimedia.org/example.jpg", "author": "Example Author",
            "source_url": "https://commons.wikimedia.org/wiki/File:example.jpg", "license": "CC-BY-4.0",
            "license_url": "https://creativecommons.org/licenses/by/4.0/", "attribution": "Example Author / CC BY 4.0",
            "query": "cat food owner", "topic_match": "cat+food+owner", "semantic_tags": tags,
            "required_tags": tags, "semantic_evidence": "fixture description"}


class _RealFixtureGenerator:
    mode = "gigachat"

    def __init__(self, text=None):
        self.text = text

    def generate(self, topic, facts):
        source = facts[0].source_url
        text = self.text or (
            "🐾 Проверяем безопасность корма\n\n" +
            ("Этот оригинальный тестовый текст опирается только на переданный проверяемый факт. " * 9) +
            "\n\nИсточник: " + source)
        return {"title": topic.title, "text": text, "mode": self.mode}


def _storage(tmp_path):
    return PetsStorage(str(tmp_path / "pets31.db"))


def test_official_adapter_returns_structured_public_domain_fact():
    adapter = FdaCvmAdapter(lambda endpoint: {"items": [{"topic": "Безопасность корма", "species": "cat",
                                                 "claim": "FDA публикует официальные предупреждения о безопасности кормов.",
                                                 "url": "https://www.fda.gov/example"}]})
    batches = adapter.collect()
    assert len(batches) == 1
    assert batches[0][0].license == "PUBLIC_DOMAIN"
    assert batches[0][0].adaptation_allowed is True


def test_unknown_license_requires_review(tmp_path):
    st = _storage(tmp_path)
    result = pets.process_fact_material(st, _topic(), [_fact(license="UNKNOWN")], "fda_cvm",
                                        generator=_RealFixtureGenerator(), image_resolver=lambda *_: _image())
    assert result["status"] == "review"
    assert result["reason"] == "source_rights_require_review"


def test_mock_generation_never_becomes_post_ready(tmp_path):
    st = _storage(tmp_path)
    result = pets.process_fact_material(st, _topic(), [_fact()], "fda_cvm", generator=MockPetsGenerator(),
                                        image_resolver=lambda *_: _image())
    assert result == {"source": "fda_cvm", "topic": "cat-food-safety", "status": "review",
                      "reason": "mock_generation_requires_real_ai_opt_in"}
    assert st.get(st.add(_fact().source_url, "fda_cvm"))["status"] == "review"


def test_unsupported_ai_number_is_review(tmp_path):
    st = _storage(tmp_path)
    bad = ("🐾 Безопасность\n\n" + ("Проверьте предупреждение и не назначайте лечение самостоятельно. " * 14) +
           "Через 5 дней станет лучше.\n\nИсточник: " + _fact().source_url)
    result = pets.process_fact_material(st, _topic(), [_fact()], "fda_cvm", generator=_RealFixtureGenerator(bad),
                                        image_resolver=lambda *_: _image())
    assert result["reason"] == "generated_text_has_unsupported_number"


def test_mismatched_or_missing_photo_requires_review(tmp_path):
    st = _storage(tmp_path)
    result = pets.process_fact_material(st, _topic(), [_fact()], "fda_cvm", generator=_RealFixtureGenerator(),
                                        image_resolver=lambda *_: _image(tags=("dog", "training")))
    assert result["reason"].startswith("image_review:")
    st.close()
    st = _storage(tmp_path)
    result = pets.process_fact_material(st, _topic("cat-food-safety-two"), [_fact("https://www.fda.gov/other")],
                                        "fda_cvm", generator=_RealFixtureGenerator(), image_resolver=lambda *_: None)
    assert result["reason"].startswith("image_review:")


def test_duplicate_topic_is_rejected_and_facts_persist(tmp_path):
    st = _storage(tmp_path)
    first = pets.process_fact_material(st, _topic(), [_fact()], "fda_cvm", generator=_RealFixtureGenerator(),
                                       image_resolver=lambda *_: _image())
    assert first["status"] == "post_ready"
    second = pets.process_fact_material(st, _topic(), [_fact("https://www.fda.gov/other")], "fda_cvm",
                                        generator=_RealFixtureGenerator(), image_resolver=lambda *_: _image())
    assert second["reason"] == "duplicate_topic"
    assert st.facts_for(first["material_id"])[0]["license"] == "PUBLIC_DOMAIN"


def test_source_failure_does_not_stop_other_source_and_never_publishes(tmp_path):
    st = _storage(tmp_path)

    class Broken:
        def collect(self):
            raise TimeoutError("offline fixture")

    class Good:
        def collect(self):
            return [[_fact()]]

    result = pets.run_autonomous_dry_run(st, {"broken": Broken(), "fda_cvm": Good()}, generator=MockPetsGenerator(), limit=2)
    assert result["source_errors"] == {"broken": "TimeoutError"}
    assert result["checked"] == 1
    assert result["review"] == 1
    assert result["published"] == 0


def test_planner_is_history_aware_and_alternates_species(tmp_path):
    st = _storage(tmp_path)
    topics = choose_topics(st, limit=6)
    assert len(topics) == 6
    assert all(a.species != b.species for a, b in zip(topics, topics[1:]))
    assert len({topic.key for topic in topics}) == len(topics)


def test_live_gigachat_without_explicit_cap_is_blocked_before_source_or_ai_calls(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PETS_DB_PATH", str(tmp_path / "pets.db"))
    monkeypatch.setattr(config, "RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setattr(config, "PETS_EXTERNAL_SOURCES", True)
    monkeypatch.setattr(config, "PETS_GENERATOR_MODE", "gigachat")
    monkeypatch.setattr(config, "PETS_MAX_GIGACHAT_GENERATIONS", 0)
    monkeypatch.setattr(config, "PETS_PUBLISH", False)
    monkeypatch.setattr(pets_sources, "official_adapters_for", lambda *_: pytest.fail("sources must not start"))
    ctx = JobContext("pets", str(tmp_path / "storage.json"), dry_run=True)
    pets_job.run(ctx)
    assert ctx.storage["last_run"]["autonomous"]["reason"] == "gigachat_generation_limit_must_be_1"
    assert ctx.storage["last_run"]["published"] == 0


def test_gigachat_daily_reservation_is_one_per_moscow_day(tmp_path):
    from datetime import datetime, timezone
    st = _storage(tmp_path)
    now = datetime(2026, 10, 27, 8, 0, tzinfo=timezone.utc)  # 11:00 Moscow
    assert st.reserve_gigachat_generation(now) is True
    assert st.reserve_gigachat_generation(now) is False
    next_day = datetime(2026, 10, 27, 22, 0, tzinfo=timezone.utc)  # 01:00 Moscow
    assert st.reserve_gigachat_generation(next_day) is True


def test_cc_by_sa_is_preserved_with_share_alike_obligation():
    assert normalize_license("CC BY-SA 4.0") == "CC_BY_SA"
    assert license_terms("CC BY-SA 4.0") == (
        "CC_BY_SA", True, "credit author, source and licence; share adaptations under the same licence")


class _Response:
    def __init__(self, payload=None, content=b"", status=200):
        self._payload, self.content, self.status_code = payload or {}, content, status

    def json(self):
        return self._payload


class _PmcSession:
    def get(self, url, params=None, **kwargs):
        if url.endswith("esearch.fcgi"):
            return _Response({"esearchresult": {"idlist": ["123"]}})
        xml = b'''<pmc-articleset><article><front><article-meta>
        <article-id pub-id-type="pmcid">PMC123</article-id><article-id pub-id-type="doi">10.1/example</article-id>
        <title-group><article-title>Dog welfare and enrichment</article-title></title-group>
        <contrib-group><contrib contrib-type="author"><name><surname>Smith</surname></name></contrib></contrib-group>
        <pub-date><year>2026</year></pub-date>
        <abstract><p>Dogs showed more exploratory behaviour when enrichment was available in this study.</p></abstract>
        <permissions><license><license-p>This article is licensed under CC BY-SA 4.0 <ext-link href="https://creativecommons.org/licenses/by-sa/4.0/"/></license-p></license></permissions>
        </article-meta></front><body>
        <sec><title>Results</title><p>Dogs showed more exploratory behaviour when enrichment was available in this study.</p></sec>
        <sec><title>Discussion</title><p>The study findings are limited to the observed animals and should not become a universal recommendation.</p></sec>
        </body></article></pmc-articleset>'''
        return _Response(content=xml)


def test_frontiers_pmc_connector_collects_traceable_article_level_candidate(tmp_path):
    adapter = FrontiersVeterinaryPmcAdapter(session=_PmcSession())
    st = _storage(tmp_path)
    candidates, report, collection = collect_source_candidates({"frontiers_vet": adapter}, storage=st, limit=10)
    assert report["frontiers_vet"]["status"] == "ok"
    assert report["frontiers_vet"]["found"] == 1
    assert collection == {"deduplicated": 0, "history_skipped": 0, "total_unique": 1}
    candidate = candidates[0]
    assert candidate["doi"] == "10.1/example"
    assert candidate["license"] == "CC_BY_SA"
    assert candidate["facts"][0].claim.startswith("Dogs showed")
    stored = st.source_candidates()[0]
    assert stored["license"] == "CC_BY_SA"
    assert "share adaptations" in stored["attribution_requirements"]


def test_clinical_pmc_candidate_is_held_for_manual_review():
    xml = _PmcSession().get("efetch.fcgi").content.replace(
        b"Dog welfare and enrichment", b"Canine lymphoma treatment case report")
    article = ET.fromstring(xml).find(".//article")
    candidate = FrontiersVeterinaryPmcAdapter(session=_PmcSession())._candidate(article)
    assert candidate["safety_status"] == "review"


class _FdaSession:
    def get(self, url, params=None, **kwargs):
        return _Response({"results": [{"recall_number": "R-1", "product_description": "Dog food product",
                                        "reason_for_recall": "Potential contamination", "recall_initiation_date": "20260101"}]})


def test_fda_recall_is_collected_as_review_not_owner_recommendation():
    found = FdaCvmSafetyAdapter(session=_FdaSession()).collect_candidates(limit=10)
    assert len(found) == 1
    assert found[0]["safety_status"] == "review"
    assert found[0]["facts"][0].claim.startswith("FDA enforcement record")
