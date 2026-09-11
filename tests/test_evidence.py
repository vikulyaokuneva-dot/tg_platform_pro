# -*- coding: utf-8 -*-
"""Evidence validator: цитаты и числа должны быть заземлены в исходнике."""
from case_pipeline import evidence

SRC = ("Retailer X struggled with manual price updates. They implemented "
       "an AI pipeline that cut processing time by 45% and saved 12 hours "
       "per week. Revenue grew by 1.4 million USD.")


def _case(overrides=None):
    c = {
        "company_name": "Retailer X",
        "problem": "Retailer X struggled with manual price updates.",
        "implementation": "They implemented an AI pipeline that cut processing time by 45%",
        "results": ["Revenue grew by 1.4 million USD."],
        "metrics": [{"value": "45%", "evidence": {"quote": "cut processing time by 45% and saved"}}],
        "economic_effect": "",
        "source_excerpt": "Retailer X struggled with manual price updates. They implemented an AI pipeline",
        "source_title": "Retailer X case",
        "evidence": {
            "problem": {"quote": "Retailer X struggled with manual price updates."},
            "implementation": {"quote": "They implemented an AI pipeline that cut processing time by 45%"},
            "results": [{"quote": "Revenue grew by 1.4 million USD."}],
            "metrics": ["cut processing time by 45% and saved"],
        },
    }
    c.update(overrides or {})
    return c


def test_valid_case_passes():
    ok, errors = evidence.validate_case(_case(), SRC)
    assert ok, errors


def test_hallucinated_quote_fails():
    c = _case()
    c["evidence"]["problem"]["quote"] = "Company Y wanted to automate its warehouse robots fleet nationwide."
    ok, errors = evidence.validate_case(c, SRC)
    assert not ok and any("quote not found" in e for e in errors)


def test_hallucinated_number_fails():
    c = _case()
    c["results"] = ["Revenue grew by 973%."]
    c["evidence"]["results"] = [{"quote": "Revenue grew by 973%."}]
    ok, errors = evidence.validate_case(c, SRC)
    assert not ok and any("not found" in e or "numbers" in e for e in errors)


def test_number_only_in_post_field_fails():
    c = _case({"economic_effect": "экономия 88 процентов в год"})
    ok, errors = evidence.validate_case(c, SRC)
    assert not ok


def test_valid_numbers_pass():
    c = _case({"economic_effect": "saved 12 hours per week"})
    ok, errors = evidence.validate_case(c, SRC)
    assert ok, errors


def test_unicode_quotes_normalized():
    c = _case()
    q = "Retailer X struggled with manual price updates."
    src_typo = SRC.replace("Retailer X", "Retailer\u00a0X")  # nbsp
    ok, _ = evidence.validate_case(c, src_typo)
    assert ok  # ws-нормализация эквивалентна
