# -*- coding: utf-8 -*-
"""CASE schema: детерминированная сборка + структурная валидность."""
from case_pipeline import case_model, evidence
from case_pipeline.classifier_lib import V2
from case_pipeline import extraction


def _build(mindbox_case):
    cleaned, meta, html = mindbox_case
    ext = extraction.extract_from_html(html, meta["url"])
    cm = extraction.classifier_meta(ext)
    cm["url"] = meta["url"]
    cls = V2.classify_v2(ext["text"], cm, policy="strict")
    case = case_model.build_case(meta["url"], ext, cls, source="mindbox")
    return case, ext


def test_case_built_valid(mindbox_case):
    case, ext = _build(mindbox_case)
    ok, errors = case_model.validate_case_shape(case)
    assert ok, errors
    assert case["classification"] == "business_case"
    assert case["company_name"]
    assert case["problem"] and case["implementation"]
    assert case["source_url"].startswith("https://mindbox.ru")


def test_case_evidence_verbatim(mindbox_case):
    case, ext = _build(mindbox_case)
    ok, errors = evidence.validate_case(case, ext["text"])
    assert ok, errors


def test_case_missing_company_invalid(mindbox_case):
    case, _ = _build(mindbox_case)
    case["company_name"] = ""
    ok, errors = case_model.validate_case_shape(case)
    assert not ok and any("company_name" in e for e in errors)


def test_case_missing_evidence_invalid(mindbox_case):
    case, _ = _build(mindbox_case)
    case["evidence"]["problem"] = {}
    case["problem"] = ""
    ok, errors = case_model.validate_case_shape(case)
    assert not ok


def test_metrics_have_evidence_quotes(mindbox_case):
    case, ext = _build(mindbox_case)
    for m in case["metrics"]:
        q = m["evidence"]["quote"]
        assert evidence.quote_in_source(q, ext["text"])
        assert m["value"].replace(" ", "") in q.replace(" ", "").lower() or \
            m["value"].lower().strip() in q.lower()
