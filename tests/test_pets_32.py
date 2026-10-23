# -*- coding: utf-8 -*-
"""Offline regression coverage for the PETS 3.2 manual post preview."""
import json

from case_pipeline.pets_facts import validate_fact_set
from case_pipeline.pets_generator import factual_brief_prompt
from case_pipeline import pets_post_preview as preview


def _image():
    return {"url": "https://upload.wikimedia.org/example/cat-outdoors.jpg", "author": "Example Author",
            "source_url": "https://commons.wikimedia.org/wiki/File:Cat_outdoors.jpg", "license": "CC-BY-4.0",
            "license_url": "https://creativecommons.org/licenses/by/4.0/", "attribution": "Example Author / CC BY 4.0",
            "query": "domestic cat outdoors", "topic_match": "cat+outdoor", "semantic_tags": ("cat", "outdoor"),
            "required_tags": ("cat", "outdoor"), "semantic_evidence": "cat outdoors in garden"}


def test_313_brief_is_traceable_and_prompt_contains_all_editorial_boundaries():
    brief = preview.factual_brief()
    assert validate_fact_set(brief["facts"]) == (True, "")
    prompt = factual_brief_prompt(brief)
    for value in (brief["doi"], brief["source_url"], brief["limitations"][0],
                  brief["allowed_conclusions"][0], brief["forbidden_conclusions"][0]):
        assert value in prompt


def test_offline_preview_creates_complete_manual_approval_artifacts(tmp_path):
    payload = preview.build_preview(tmp_path, image_resolver=lambda *_: _image())
    assert payload["status"] == "ready_for_manual_approval"
    assert payload["gigachat"]["calls"] == 0
    assert payload["telegram_sent"] is False and payload["pets_publish"] is False
    assert payload["image"]["license"] == "CC-BY-4.0"
    assert payload["validation"]["manual_review_required"] is True
    for name in ("pets_post_preview.md", "pets_post_preview.json", "pets_post_validation.json", "pets_post_diagnostics.json"):
        assert (tmp_path / name).exists()
    saved = json.loads((tmp_path / "pets_post_preview.json").read_text(encoding="utf-8"))
    assert saved["telegram_preview"]["mode"] in {"photo_with_caption", "photo_then_text"}


def test_live_generation_cannot_start_without_explicit_owner_approval(tmp_path):
    class Generator:
        def generate_factual_brief(self, brief):
            raise AssertionError("GigaChat must not be called before owner approval")
    payload = preview.build_preview(tmp_path, use_live_gigachat=True, owner_approved=False,
                                    generator=Generator(), image_resolver=lambda *_: _image())
    assert payload["gigachat"]["calls"] == 0
    assert payload["gigachat"]["status"] == "awaiting_explicit_owner_approval"


def test_preview_marks_unsupported_causal_wording_for_review():
    brief = preview.factual_brief()
    result = preview.validate_post("Тестовый заголовок", "Связь вызывает одинаковое поведение у всех кошек.", brief,
                                   origin="test")
    assert result["ok"] is False
    assert result["checks"]["no_causal_claim"] is False


def test_telegram_layout_splits_when_caption_is_too_long():
    brief = preview.factual_brief()
    layout = preview._telegram_layout("Заголовок", "Текст " * 400, brief)
    assert layout["mode"] == "photo_then_text"
    assert layout["continuation"]
    assert layout["caption_length"] <= 1024
