# -*- coding: utf-8 -*-
"""Offline regression tests for PETS 3.1.2 editorial source selection."""
import xml.etree.ElementTree as ET

from case_pipeline.pets_candidates import (PmcOpenAccessAdapter, TOPIC_CATALOG, _species,
                                            _title_is_excluded, collect_source_candidates)
from case_pipeline.pets_storage import PetsStorage


def _spec(key):
    return next(item for item in TOPIC_CATALOG if item.key == key)


def _article(title="Dog enrichment at home"):
    xml = """
    <pmc-articleset><article><front><article-meta>
      <article-id pub-id-type="pmcid">PMC900001</article-id>
      <article-id pub-id-type="doi">10.1000/pets.enrichment</article-id>
      <title-group><article-title>%s</article-title></title-group>
      <contrib-group><contrib contrib-type="author"><name><surname>Author</surname></name></contrib></contrib-group>
      <pub-date><year>2026</year></pub-date>
      <permissions><license><license-p>CC BY 4.0 <ext-link href="https://creativecommons.org/licenses/by/4.0/"/></license-p></license></permissions>
    </article-meta></front><body>
      <sec><title>Results</title>
        <p>Dogs offered a rotating enrichment routine spent more time engaged with approved toys during the observed home sessions.</p>
        <p>Dogs in the enrichment group showed fewer repeated attention-seeking behaviours during the two-week observation period.</p>
        <p>The recorded dog outcome was associated with the structured enrichment routine in this small owner-reported study and does not prove causation.</p>
      </sec>
      <sec><title>Discussion</title><p>The findings describe this study sample and should be interpreted alongside each individual dog's needs and environment.</p></sec>
      <sec><title>Limitations</title><p>The sample was small and owner reports may not generalize to all dogs or households.</p></sec>
    </body></article></pmc-articleset>""" % title
    return ET.fromstring(xml).find(".//article")


def test_full_text_facts_are_traceable_and_editorially_ready():
    candidate = PmcOpenAccessAdapter()._candidate(_article(), _spec("dog_enrichment"))
    assert candidate["technical_status"] == "source_usable"
    assert candidate["editorial_status"] == "editorially_ready"
    assert candidate["editorial"]["score"] == 14
    assert len(candidate["facts"]) >= 3
    assert {fact.source_section for fact in candidate["facts"]} <= {"result", "discussion", "conclusion"}
    assert candidate["limitations"][0].startswith("The sample was small")


def test_sample_demographics_are_not_promoted_to_owner_facts():
    article = _article()
    result = article.find(".//sec")
    demographic = ET.Element("p")
    demographic.text = "The majority of participants were women and most respondents lived in suburban areas."
    result.insert(1, demographic)
    candidate = PmcOpenAccessAdapter()._candidate(article, _spec("dog_enrichment"))
    assert not any("participants were women" in fact.claim for fact in candidate["facts"])


def test_student_or_specialist_article_is_not_editorially_ready():
    title = "Canine osteology teaching for veterinary students"
    candidate = PmcOpenAccessAdapter()._candidate(_article(title), _spec("dog_enrichment"))
    assert candidate["editorial_status"] == "needs_editorial_review"
    assert any("excluded=student" in reason for reason in candidate["editorial"]["reasons"])


def test_clinical_title_cannot_pass_from_a_matching_training_word():
    title = "Dog training after surgery: a clinical follow-up"
    candidate = PmcOpenAccessAdapter()._candidate(_article(title), _spec("dog_training"))
    assert candidate["editorial_status"] == "needs_editorial_review"
    assert any("excluded=surgery" in reason for reason in candidate["editorial"]["reasons"])


def test_non_pet_and_biomedical_false_keyword_matches_are_excluded():
    assert _title_is_excluded("Differences in post-conflict behaviour in wolves") == "wolv"
    assert _title_is_excluded("Glycosylation of canine tetherin antiviral activity") == "viral"
    assert _title_is_excluded("Molecular study of canine genes") == "molecular"
    assert _species("BAR-CAT: Targeted Recovery of Synthetic Genes") == "general"


def test_specialist_technology_and_breeder_topics_are_not_owner_ready():
    assert _title_is_excluded("Cat behavior recognition network from video") == "recognition"
    assert _title_is_excluded("Domestic dog breeders and competitive behaviour") == "breeder"
    assert _title_is_excluded("Nanoparticle activity against canine skin pathogens") == "nanoparticle"


class _Adapter:
    def __init__(self, candidates):
        self.candidates = candidates

    def collect_candidates(self, limit=10):
        return self.candidates[:limit]


def test_doi_deduplication_and_editorial_fields_are_persisted(tmp_path):
    candidate = PmcOpenAccessAdapter()._candidate(_article(), _spec("dog_enrichment"))
    duplicate = dict(candidate, source_id="frontiers_vet")
    st = PetsStorage(str(tmp_path / "candidates.db"))
    selected, report, collection = collect_source_candidates(
        {"pmc": _Adapter([candidate]), "frontiers": _Adapter([duplicate])}, storage=st, limit=10)
    assert len(selected) == 1
    assert collection["deduplicated"] == 1
    assert report["pmc"]["editorially_ready"] == 1
    row = st.source_candidates()[0]
    assert row["editorial_status"] == "editorially_ready"
    assert row["topic_key"] == "dog_enrichment"
