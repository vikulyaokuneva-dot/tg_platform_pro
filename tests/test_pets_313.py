# -*- coding: utf-8 -*-
"""Offline PETS 3.1.3 tests: household relevance, evidence and durable skips."""
from case_pipeline.pets_candidates import (PmcOpenAccessAdapter, TOPIC_CATALOG, _candidate_identities,
                                            _pets_query, collect_source_candidates)
from case_pipeline.pets_storage import PetsStorage
from tests.test_pets_312 import _article


def _spec(key):
    return next(item for item in TOPIC_CATALOG if item.key == key)


def _non_domestic_article():
    article = _article("Dog enrichment in a wild setting")
    for node in article.iter():
        if node.text:
            node.text = node.text.replace("home", "field").replace("owner", "observer").replace("household", "setting")
    return article


def test_household_query_uses_title_and_abstract_without_title_only_requirement():
    query = _pets_query("dog", ("environmental enrichment", "play behaviour"))
    assert "[Title/Abstract]" in query
    assert "dog owner" in query
    assert "environmental enrichment" in query


def test_editorial_gate_requires_domestic_context_and_marks_unverified_image():
    candidate = PmcOpenAccessAdapter()._candidate(_non_domestic_article(), _spec("dog_enrichment"))
    assert candidate["editorial_status"] == "needs_editorial_review"
    assert candidate["editorial"]["criteria"]["image_search_feasible"] is False
    assert candidate["editorial"]["criteria"]["image_verified"] is False
    assert candidate["editorial"]["reason_category"] == "irrelevant_audience"


def test_narrow_owner_sample_is_review_not_a_general_owner_brief():
    candidate = PmcOpenAccessAdapter()._candidate(
        _article("Dog owner walking activity in women"), _spec("dog_walks"))
    assert candidate["editorial_status"] == "needs_editorial_review"
    assert any("population is too narrow" in reason for reason in candidate["editorial"]["reasons"])


def test_discussion_that_only_repeats_broader_evidence_is_not_a_study_fact():
    article = _article()
    discussion = article.findall(".//sec")[1]
    paragraph = discussion.find("p")
    paragraph.text = "Broader evidence suggests that owners should change routines, but this is not a direct study result."
    candidate = PmcOpenAccessAdapter()._candidate(article, _spec("dog_enrichment"))
    assert not any("Broader evidence" in fact.claim for fact in candidate["facts"])


def test_discussion_citation_is_not_promoted_as_this_studys_finding():
    article = _article()
    discussion = article.findall(".//sec")[1]
    paragraph = discussion.find("p")
    paragraph.text = "Dogs' enrichment routines were described in unrelated literature [58], not measured in this study."
    candidate = PmcOpenAccessAdapter()._candidate(article, _spec("dog_enrichment"))
    assert not any("[58]" in fact.claim for fact in candidate["facts"])


class _Adapter:
    def __init__(self, candidates):
        self.candidates = candidates

    def collect_candidates(self, limit=10):
        return self.candidates[:limit]


def test_doi_identity_normalises_variants_and_pmcid_is_retained():
    candidate = PmcOpenAccessAdapter()._candidate(_article(), _spec("dog_enrichment"))
    candidate["doi"] = "HTTPS://doi.org/10.1000/PETS.ENRICHMENT."
    identities = _candidate_identities(candidate)
    assert "doi:10.1000/pets.enrichment" in identities
    assert "pmcid:PMC900001" in identities


def test_rejected_history_skips_repeat_without_reassessing(tmp_path):
    candidate = PmcOpenAccessAdapter()._candidate(_non_domestic_article(), _spec("dog_enrichment"))
    storage = PetsStorage(str(tmp_path / "pets_313.db"))
    first, _, collection = collect_source_candidates({"pmc": _Adapter([candidate])}, storage=storage, limit=10)
    assert len(first) == 1 and collection["history_skipped"] == 0
    second, _, collection = collect_source_candidates({"pmc": _Adapter([candidate])}, storage=storage, limit=10)
    assert second == [] and collection["history_skipped"] == 1
    assert storage.source_rejection_statistics()["irrelevant_audience"] >= 1


def test_ncbi_request_uses_tool_but_never_invents_contact_email():
    class Session:
        def get(self, *args, **kwargs):
            self.params = kwargs["params"]
            return type("Response", (), {"status_code": 200, "json": lambda self: {"esearchresult": {"idlist": []}}})()
    session = Session()
    assert PmcOpenAccessAdapter(session=session).search_ids(_spec("dog_enrichment"), limit=1) == []
    assert session.params["tool"] == "tg_platform_pets"
    assert "email" not in session.params
