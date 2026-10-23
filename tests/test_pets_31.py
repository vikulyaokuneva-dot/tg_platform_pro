# -*- coding: utf-8 -*-
"""Offline PETS 3.1 safety and source-contract regression tests."""
from case_pipeline import pets
from case_pipeline.pets_facts import Fact
from case_pipeline.pets_generator import MockPetsGenerator
from case_pipeline.pets_planner import Topic, choose_topics
from case_pipeline.pets_sources import FdaCvmAdapter
from case_pipeline.pets_storage import PetsStorage


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
