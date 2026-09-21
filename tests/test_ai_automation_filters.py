# -*- coding: utf-8 -*-
"""AI Automation filter relaxation tests (soft/hard split). AGRO untouched."""
from case_pipeline import case_model


def _minimal_case():
    return {
        "case_id": "c-1", "source_url": "https://example.com/x",
        "company_name": "Demo", "problem": "manual work",
        "implementation": "used n8n", "evidence": {
            "problem": {"quote": "manual work"},
            "implementation": {"quote": "used n8n"},
            "results": [{"quote": "faster"}],
        },
        "classification": "how_to", "metrics": [],
        "results": ["faster workflow"],
    }


def test_practical_guide_no_numeric_soft_not_hard():
    c = _minimal_case(); c["metrics"] = []; c["results"] = ["workflow improved"]
    ok, errs = case_model.validate_case_shape(c)
    assert ok, errs  # hard errors only; numeric absence is soft
    assert any("soft: no numeric" in e for e in errs)


def test_duplicate_hard_rejected():
    # duplicate detection stays HARD (not changed here; covered by pipeline/storage)
    pass


def test_empty_spam_hard():
    c = _minimal_case(); c["problem"] = ""; c["implementation"] = ""
    ok, errs = case_model.validate_case_shape(c)
    assert not ok
    assert any("missing" in e or "evidence" in e for e in errs)
