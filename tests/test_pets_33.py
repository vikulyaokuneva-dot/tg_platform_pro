# -*- coding: utf-8 -*-
"""Offline regression coverage for PETS 3.3 universal factual-brief previews."""
import json
import runpy
import sqlite3

from case_pipeline import pets_universal_preview as preview
from case_pipeline.pets_generator import GigaChatPetsGenerator, factual_brief_prompt


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


def test_loader_accepts_a_verified_non_doi_source_key(tmp_path):
    candidate = _candidate()
    candidate["doi"] = ""
    candidate["source_key"] = "official-dog-welfare-guidance"
    brief = preview.load_editorial_briefs(_artifact(tmp_path / "briefs.json", [candidate]))[0][0]
    assert brief["doi"] == ""
    assert brief["source_identity"] == "official-dog-welfare-guidance"


def test_explicit_visual_contract_overrides_english_keyword_guessing(tmp_path):
    candidate = _candidate()
    candidate["image_query"] = "dog owner walking in city"
    candidate["visual_tags"] = ["dog", "walk"]
    brief = preview.load_editorial_briefs(_artifact(tmp_path / "briefs.json", [candidate]))[0][0]
    assert preview.visual_contract(brief) == {"image_query": "dog owner walking in city", "visual_tags": ("dog", "walk")}


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


def test_photo_download_falls_back_to_original_commons_file(tmp_path):
    candidate = _candidate()
    candidate["title"] = "Outdoor exploration of domestic cats"
    artifact = _artifact(tmp_path / "briefs.json", [candidate])
    history = _history_db(tmp_path / "history.db")
    image = dict(_image(), original_url="https://upload.wikimedia.org/example/cat-original.jpg")
    calls = []
    def downloader(value):
        calls.append(value)
        return b"x" * 20000, {"status": "attached", "url": image["original_url"], "version": "original",
                                "mime_type": "image/jpeg", "bytes": 20000, "attempts": []}
    manifest = preview.build_previews(artifact, tmp_path / "out", history_db_path=history,
                                      image_resolver=lambda *_: image, image_downloader=downloader, download_images=True)
    payload = json.loads((tmp_path / "out" / manifest["posts"][0]["directory"] / "pets_post_preview.json").read_text(encoding="utf-8"))
    assert len(calls) == 1 and payload["image_download"]["status"] == "attached"
    assert (tmp_path / "out" / manifest["posts"][0]["directory"] / payload["image_download"]["file"]).exists()


def test_commons_403_is_saved_as_non_secret_download_diagnostics():
    class Response:
        status_code = 403
        content = b"blocked"
        headers = {"Content-Type": "text/html", "Content-Length": "7", "Set-Cookie": "must-not-appear"}
    class Session:
        def get(self, url, **kwargs):
            return Response()
    image = dict(_image(),
                 url="https://upload.wikimedia.org/wikipedia/commons/thumb/a/a1/Photo.jpg/1200px-Photo.jpg?temporary=secret",
                 original_url="https://upload.wikimedia.org/wikipedia/commons/a/a1/Photo.jpg?temporary=secret",
                 source_url="https://commons.wikimedia.org/wiki/File:Photo.jpg")
    data, diagnostic = preview.pets_images.download_preview_image(image, session=Session(), max_attempts=3)
    assert data is None and diagnostic["status"] == "image_download_failed"
    assert [item["http_status"] for item in diagnostic["attempts"]] == [403, 403, 403]
    assert all(item["bytes"] == 7 for item in diagnostic["attempts"])
    assert all("temporary" not in item["url"] for item in diagnostic["attempts"])
    assert "set-cookie" not in diagnostic["attempts"][0]["headers"]


def test_unverified_original_url_is_not_used_as_a_fallback():
    class Response:
        status_code = 403
        content = b"blocked"
        headers = {"Content-Type": "text/html"}
    class Session:
        def __init__(self):
            self.urls = []
        def get(self, url, **kwargs):
            self.urls.append(url)
            return Response()
    session = Session()
    image = dict(_image(), url="https://upload.wikimedia.org/wikipedia/commons/thumb/a/a1/Photo.jpg/1200px-Photo.jpg",
                 original_url="https://upload.wikimedia.org/wikipedia/commons/a/a1/A-different-file.jpg",
                 source_url="https://commons.wikimedia.org/wiki/File:Photo.jpg")
    data, diagnostic = preview.pets_images.download_preview_image(image, session=session, max_attempts=3)
    assert data is None and len(diagnostic["attempts"]) == 2
    assert image["original_url"] not in session.urls
    assert session.urls[0] == image["url"]
    assert session.urls[1].startswith("https://commons.wikimedia.org/wiki/Special:FilePath/Photo.jpg")


def test_failed_image_download_keeps_verified_link_but_blocks_ready_status(tmp_path):
    candidate = _candidate()
    candidate["title"] = "Outdoor exploration of domestic cats"
    artifact = _artifact(tmp_path / "briefs.json", [candidate])
    history = _history_db(tmp_path / "history.db")
    class Generator:
        def generate_factual_brief(self, brief):
            return {"text": "Наблюдения за кошкой\n\nЭто результат конкретного исследования. %s" % brief["source_url"]}
    def failed(_image):
        return None, {"status": "image_download_failed", "reason": "no_accessible_image_version", "attempts": []}
    manifest = preview.build_previews(artifact, tmp_path / "out", history_db_path=history,
                                      use_live_gigachat=True, owner_approved=True, generator=Generator(),
                                      image_resolver=lambda *_: _image(), image_downloader=failed, download_images=True)
    payload = json.loads((tmp_path / "out" / manifest["posts"][0]["directory"] / "pets_post_preview.json").read_text(encoding="utf-8"))
    assert payload["image"] and not payload["validation"]["image_local_file"]
    assert payload["status"] == "review"
    assert "image:image_download_failed" in payload["review_reasons"]


def test_mock_ai_failure_never_promotes_post_to_ready(tmp_path):
    artifact = _artifact(tmp_path / "briefs.json", [_candidate()])
    history = _history_db(tmp_path / "history.db")
    class Generator:
        def generate_factual_brief(self, brief):
            return None
    manifest = preview.build_previews(artifact, tmp_path / "out", history_db_path=history,
                                      use_live_gigachat=True, owner_approved=True, generator=Generator(),
                                      image_resolver=lambda *_: _image())
    assert manifest["posts"][0]["status"] == "review"


def test_mock_gigachat_receives_selected_factual_brief_and_returns_checked_preview(tmp_path):
    candidate = _candidate()
    candidate["title"] = "Outdoor exploration of domestic cats"
    artifact = _artifact(tmp_path / "briefs.json", [candidate])
    history = _history_db(tmp_path / "history.db")
    class Provider:
        available = True
        received = []
        def complete(self, messages):
            self.received.extend(messages)
            return "Заголовок\n\n" + ("Исследование описывает конкретную группу, а не универсальное правило. https://example.org/articles/pets.preview ") * 9
    provider = Provider()
    generator = GigaChatPetsGenerator(provider, enabled=True)
    manifest = preview.build_previews(artifact, tmp_path / "out", history_db_path=history,
                                      use_live_gigachat=True, owner_approved=True, generator=generator,
                                      image_resolver=lambda *_: _image())
    assert manifest["gigachat_calls"] == 1
    assert manifest["posts"][0]["status"] == "ready_for_manual_approval"
    assert "10.1000/pets.preview" in provider.received[0]["content"]


def test_generation_prompt_uses_the_selected_brief_species_not_a_cat_default(tmp_path):
    dog = _candidate("10.1000/dog.preview")
    dog["species"] = "dog"
    for fact in dog["facts"]:
        fact["species"] = "dog"
    brief = preview.load_editorial_briefs(_artifact(tmp_path / "briefs.json", [dog]))[0][0]
    assert "владельцев собак" in factual_brief_prompt(brief)


def test_ogl_v3_facts_are_accepted_with_their_own_attribution_terms():
    candidate = _candidate("10.1000/ogl.preview")
    for fact in candidate["facts"]:
        fact["license"] = "OGL-3.0"
        fact["license_source_url"] = "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
        fact["attribution_requirements"] = "acknowledge the information provider and source; link to OGL where possible"
    facts = tuple(preview._fact_from_json(value) for value in candidate["facts"])
    assert preview.validate_fact_set(facts) == (True, "")


def test_ogl_version_is_attribution_not_an_unsupported_editorial_number():
    candidate = _candidate("10.1000/ogl.generated")
    for fact in candidate["facts"]:
        fact["license"] = "OGL-3.0"
        fact["adaptation_allowed"] = True
    facts = tuple(preview._fact_from_json(value) for value in candidate["facts"])
    text = "Practical owner checklist. Licensed under the Open Government Licence v3.0."
    assert preview.validate_generated_text(text, facts, citation_text=candidate["source_url"]) == (True, "")
    assert preview.validate_generated_text(text + " It needs 42 walks.", facts,
                                           citation_text=candidate["source_url"]) == (
                                               False, "generated_text_has_unsupported_number")


def test_cached_prior_gigachat_result_is_revalidated_without_a_new_call(tmp_path):
    candidate = _candidate("10.1000/cached.preview")
    candidate["title"] = "Outdoor exploration of domestic cats"
    artifact = _artifact(tmp_path / "briefs.json", [candidate])
    history = _history_db(tmp_path / "history.db")
    cached = {"10.1000/cached.preview": {
        "title": "Checked title",
        "body": "Observed behaviour differed between individual cats. " + candidate["source_url"],
    }}
    manifest = preview.build_previews(
        artifact, tmp_path / "out", history_db_path=history, precomputed_texts=cached,
        image_resolver=lambda *_: _image())
    payload = json.loads((tmp_path / "out" / manifest["posts"][0]["directory"] / "pets_post_preview.json").read_text(encoding="utf-8"))
    assert manifest["gigachat_calls"] == 0
    assert payload["text_origin"] == "gigachat_cached"
    assert payload["status"] == "ready_for_manual_approval"


def test_cc_by_2_photo_is_allowed_when_context_and_attribution_are_verified():
    image = dict(_image(), license="CC-BY-2.0", license_url="https://creativecommons.org/licenses/by/2.0/")
    assert preview.pets_images.validate_image(image) == (True, "")


def test_universal_preview_only_constructs_real_provider_after_all_live_gates(monkeypatch):
    monkeypatch.setenv("PETS_33_USE_LIVE_GIGACHAT", "1")
    monkeypatch.setenv("PETS_33_OWNER_APPROVED", "1")
    monkeypatch.setenv("PETS_33_MAX_GIGACHAT_CALLS", "1")
    monkeypatch.setenv("PETS_ALLOW_LIVE_AI", "0")
    monkeypatch.setattr("case_pipeline.pets_universal_preview.build_previews", lambda *args, **kwargs: kwargs)
    called = []
    monkeypatch.setattr("case_pipeline.ai.get_provider", lambda: called.append(True))
    runpy.run_module("jobs.pets.universal_preview", run_name="__main__")
    assert called == []


def test_image_retry_transient_429_then_success_without_leaking_url():
    class Response:
        def __init__(self, status):
            self.status_code = status
            self.content = b'x' * 20000 if status == 200 else b'limit'
            self.headers = {'Content-Type': 'image/jpeg' if status == 200 else 'text/plain'}
    class Session:
        def __init__(self):
            self.statuses = iter([429, 200])
        def get(self, *args, **kwargs):
            return Response(next(self.statuses))
    delays = []
    data, diag = preview.pets_images.download_preview_image(
        {'url': 'https://user:secret@upload.wikimedia.org/file.jpg?token=secret'},
        session=Session(), max_attempts=3, sleep=delays.append)
    assert data and [a['http_status'] for a in diag['attempts']] == [429, 200]
    assert delays == [1.5]
    assert 'secret' not in str(diag)


def test_image_retry_permanent_failure_stops_without_sleep():
    class Response:
        status_code = 403
        content = b'blocked'
        headers = {'Content-Type': 'text/plain'}
    class Session:
        def get(self, *args, **kwargs):
            return Response()
    delays = []
    data, diag = preview.pets_images.download_preview_image(
        {'url': 'https://upload.wikimedia.org/file.jpg'}, session=Session(),
        max_attempts=3, sleep=delays.append)
    assert data is None and len(diag['attempts']) == 1
    assert diag['attempts'][0]['reason'] == 'http_status_403' and not delays


def test_image_retry_budget_is_global_across_verified_versions():
    class Response:
        status_code = 429
        content = b"limited"
        headers = {'Content-Type': 'text/html'}
    class Session:
        def get(self, *args, **kwargs):
            return Response()
    image = dict(_image(),
                 url="https://upload.wikimedia.org/wikipedia/commons/thumb/a/a1/Photo.jpg/1200px-Photo.jpg",
                 original_url="https://upload.wikimedia.org/wikipedia/commons/a/a1/Photo.jpg",
                 source_url="https://commons.wikimedia.org/wiki/File:Photo.jpg")
    delays = []
    data, diag = preview.pets_images.download_preview_image(image, session=Session(), max_attempts=3,
                                                              sleep=delays.append)
    assert data is None and len(diag["attempts"]) == 3
    assert [attempt["version"] for attempt in diag["attempts"]] == ["thumbnail"] * 3
    assert delays == [1.5, 3]
