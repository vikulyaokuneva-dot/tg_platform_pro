# -*- coding: utf-8 -*-
"""Offline regression coverage for PETS 3.3 universal factual-brief previews."""
import json
import sqlite3

from case_pipeline import pets_universal_preview as preview
from case_pipeline.pets_generator import factual_brief_prompt


def _candidate(doi="10.1000/pets.preview"):
    source_url = "https://example.org/articles/%s" % doi.rsplit("/", 1)[-1]
    fact_base = {
        "topic": "Домашняя кошка и исследовательское поведение", "species": "cat",
        "source_url": source_url, "source_name": "Open source", "source_type": "primary_research",
        "author_or_body": "Example Author", "published_at": "2026", "license": "CC_BY",
        "license_source_url": "https://creativecommons.org/licenses/by/4.0/",
        "attribution_requirements": "credit author, source and licence", "adaptation_allowed": True,
        "evidence_level": "primary_research", "source_section": "discussion", "fact_kind": "study_discussion",
    }
    return {"editorial_status": "editorially_ready", "doi": doi, "source_url": source_url,
            "adaptation_allowed": True, "title": fact_base["topic"], "species": "cat", "category": "behavior",
            "limitations": ["This study is not a universal owner recommendation."],
            "facts": [dict(fact_base, claim="Observed behaviour differed between individual cats."),
                      dict(fact_base, claim="The result describes an association in the studied group."),
                      dict(fact_base, claim="The authors discuss limits of the survey design.")]}


def _artifact(path, candidates):
    path.write_text(json.dumps({"candidates": candidates}, ensure_ascii=False), encoding="utf-8")
    return path


def _image():
    return {"url": "https://upload.wikimedia.org/example/cat-outdoors.jpg", "author": "Example Author",
            "source_url": "https://commons.wikimedia.org/wiki/File:Cat_outdoors.jpg", "license": "CC-BY-4.0",
            "license_url": "https://creativecommons.org/licenses/by/4.0/", "attribution": "Example Author / CC BY 4.0",
            "query": "domestic cat outdoors", "topic_match": "cat+outdoor", "semantic_tags": ("cat", "outdoor"),
            "required_tags": ("cat", "outdoor"), "semantic_evidence": "cat outdoors in garden"}


def _history_db(path, published_url=None):
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE materials(canonical_url TEXT,post_text TEXT,status TEXT)")
        if published_url:
            db.execute("INSERT INTO materials VALUES(?,?, 'published')", (published_url, "old published PETS text"))
    return path


def test_loader_accepts_only_real_editorial_briefs_and_never_fills_the_limit(tmp_path):
    bad = _candidate("10.1000/bad")
    bad["editorial_status"] = "needs_editorial_review"
    accepted, rejected, report = preview.load_editorial_briefs(_artifact(tmp_path / "briefs.json", [_candidate(), bad]), max_previews=3)
    assert len(accepted) == 1 and accepted[0]["doi"] == "10.1000/pets.preview"
    assert rejected == [{"identity": "10.1000/bad", "reason": "candidate_not_editorially_ready"}]
    assert report["accepted"] == 1


def test_offline_preview_writes_review_artifacts_without_ai_or_telegram(tmp_path):
    candidate = _candidate()
    candidate["title"] = "Outdoor exploration of domestic cats"
    artifact = _artifact(tmp_path / "briefs.json", [candidate])
    history = _history_db(tmp_path / "history.db")
    manifest = preview.build_previews(artifact, tmp_path / "out", history_db_path=history,
                                      image_resolver=lambda *_: _image())
    assert manifest["gigachat_calls"] == 0 and manifest["telegram_sent"] is False
    assert manifest["posts"][0]["status"] == "review"
    post_dir = tmp_path / "out" / manifest["posts"][0]["directory"]
    payload = json.loads((post_dir / "pets_post_preview.json").read_text(encoding="utf-8"))
    assert payload["text_origin"] == "offline_factual_outline"
    assert "offline_outline_requires_editorial_text" in payload["review_reasons"][0]
    for name in ("pets_post_preview.md", "pets_post_preview.json", "pets_post_validation.json"):
        assert (post_dir / name).exists()


def test_live_generation_requires_explicit_owner_approval(tmp_path):
    class Generator:
        def generate_factual_brief(self, brief):
            raise AssertionError("GigaChat must not be called without permission")
    artifact = _artifact(tmp_path / "briefs.json", [_candidate()])
    manifest = preview.build_previews(artifact, tmp_path / "out", use_live_gigachat=True,
                                      owner_approved=False, generator=Generator(), image_resolver=lambda *_: _image())
    assert manifest["gigachat_calls"] == 0


def test_read_only_history_is_not_mutated_and_blocks_a_published_source(tmp_path):
    candidate = _candidate()
    history = _history_db(tmp_path / "history.db", candidate["source_url"])
    before = history.read_bytes()
    result = preview.read_published_history(history)
    assert history.read_bytes() == before and result["status"] == "read_only"
    artifact = _artifact(tmp_path / "briefs.json", [candidate])
    manifest = preview.build_previews(artifact, tmp_path / "out", history_db_path=history,
                                      image_resolver=lambda *_: _image())
    assert "duplicate:published_source_url" in manifest["posts"][0]["review_reasons"]
    assert history.read_bytes() == before


def test_explicit_mocked_generation_can_become_manual_approval_ready(tmp_path):
    candidate = _candidate()
    candidate["title"] = "Outdoor exploration of domestic cats"
    artifact = _artifact(tmp_path / "briefs.json", [candidate])
    history = _history_db(tmp_path / "history.db")
    class Generator:
        def generate_factual_brief(self, brief):
            return {"text": "Наблюдения за домашними кошками\n\nИсследование описывает наблюдение в изученной группе, а не универсальное правило. %s" % brief["source_url"]}
    manifest = preview.build_previews(artifact, tmp_path / "out", history_db_path=history,
                                      use_live_gigachat=True, owner_approved=True, generator=Generator(),
                                      image_resolver=lambda *_: _image())
    assert manifest["gigachat_calls"] == 1
    assert manifest["posts"][0]["status"] == "ready_for_manual_approval"


def test_photo_download_falls_back_to_original_commons_file(tmp_path, monkeypatch):
    candidate = _candidate()
    candidate["title"] = "Outdoor exploration of domestic cats"
    artifact = _artifact(tmp_path / "briefs.json", [candidate])
    history = _history_db(tmp_path / "history.db")
    image = dict(_image(), original_url="https://upload.wikimedia.org/example/cat-original.jpg")
    calls = []
    def fetch(url):
        calls.append(url)
        if "original" not in url:
            raise RuntimeError("thumbnail blocked")
        return b"x" * 20000
    monkeypatch.setattr(preview.httpclient, "fetch_bytes", fetch)
    manifest = preview.build_previews(artifact, tmp_path / "out", history_db_path=history,
                                      image_resolver=lambda *_: image, download_images=True)
    payload = json.loads((tmp_path / "out" / manifest["posts"][0]["directory"] / "pets_post_preview.json").read_text(encoding="utf-8"))
    assert len(calls) == 2 and payload["image_download"]["status"] == "attached"
    assert (tmp_path / "out" / manifest["posts"][0]["directory"] / payload["image_download"]["file"]).exists()


def test_generation_prompt_uses_the_selected_brief_species_not_a_cat_default(tmp_path):
    dog = _candidate("10.1000/dog.preview")
    dog["species"] = "dog"
    for fact in dog["facts"]:
        fact["species"] = "dog"
    brief = preview.load_editorial_briefs(_artifact(tmp_path / "briefs.json", [dog]))[0][0]
    assert "владельцев собак" in factual_brief_prompt(brief)
