# -*- coding: utf-8 -*-
"""Юнит-тесты извлечения: RU/EN сырой HTML -> text+metadata+quality."""
import os

import pytest

from case_pipeline import extraction


def test_mindbox_ru_extraction(mindbox_case):
    cleaned, meta, html = mindbox_case
    ext = extraction.extract_from_html(html, meta["url"])
    assert ext["quality"] in ("good", "partial")
    assert len(ext["text"]) >= 700
    assert ext["language"] == "ru"
    assert ext["title"]
    assert "Директ" in ext["text"] or "директ" in ext["text"].lower()


def test_ibm_en_extraction(ibm_case):
    cleaned, meta, html = ibm_case
    ext = extraction.extract_from_html(html, meta["url"])
    assert ext["quality"] in ("good", "partial")
    assert ext["language"] == "en"
    assert "tennis" in ext["text"].lower() or "us open" in ext["text"].lower()


def test_extraction_matches_baseline(mindbox_case):
    """Извлечение из raw.html воспроизводит baseline cleaned.txt (та же длина в допуске)."""
    cleaned, meta, html = mindbox_case
    ext = extraction.extract_from_html(html, meta["url"])
    assert abs(len(ext["text"]) - len(cleaned)) <= 0.25 * len(cleaned)


def test_failed_extraction_empty_html():
    ext = extraction.extract_from_html("<html><body></body></html>", "https://x.test/a")
    assert ext["quality"] == "failed"
    assert ext["text"] == ""


def test_classifier_meta_mapping(mindbox_case):
    cleaned, meta, html = mindbox_case
    ext = extraction.extract_from_html(html, meta["url"])
    cm = extraction.classifier_meta(ext)
    assert set(cm) == {"title", "description", "url", "publisher", "sitename"}
    assert isinstance(cm["title"], str)
