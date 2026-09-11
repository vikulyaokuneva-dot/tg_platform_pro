# -*- coding: utf-8 -*-
"""Классификация замороженным V2 через production-обвязку: 5 исходов lanes.

Ожидаемые предсказания зафиксированы (pinned) по валидированному holdout-прогону;
тест проверяет wiring пайплайна, а не переопределяет классификатор.
"""
import os

import pytest

from case_pipeline import extraction
from case_pipeline.classifier_lib import V2


def _cls(cleaned, meta):
    m = {"title": meta.get("title") or "",
         "description": "", "url": meta.get("url", ""),
         "publisher": "", "sitename": ""}
    return V2.classify_v2(cleaned, m, policy="strict")


def test_integrity_check_passes():
    from case_pipeline import classifier_lib
    assert classifier_lib.verify() is True


def test_tamper_detection_breaks(monkeypatch, tmp_path):
    """Любая правка frozen-классификатора => RuntimeError при загрузке."""
    import json
    import shutil
    import case_pipeline.classifier_lib as cl
    for f in ("classifier_v2.py", "classifier_baseline.py"):
        shutil.copy(os.path.join(cl.HERE, f), tmp_path)
    (tmp_path / "checksums.json").write_text(
        json.dumps({"classifier_v2.py": "0" * 64,
                    "classifier_baseline.py": "1" * 64,
                    "source": "test"}), encoding="utf-8")
    with pytest.raises(RuntimeError):
        with monkeypatch.context() as mp:
            mp.setattr(cl, "HERE", str(tmp_path))
            cl.verify()


def test_business_case_ru(mindbox_case):
    cleaned, meta, _ = mindbox_case
    r = _cls(cleaned, meta)
    assert r["type"] == "business_case"
    assert r["confidence"] >= 0.70


def test_business_case_en(ibm_case):
    cleaned, meta, _ = ibm_case
    r = _cls(cleaned, meta)
    assert r["type"] == "business_case"
    assert "Tennis" in r["company"] or "US Open" in str(r["features"])


def test_how_to(netguru_howto):
    cleaned, meta, _ = netguru_howto
    assert _cls(cleaned, meta)["type"] == "how_to"


def test_news_and_other():
    from conftest import load_item
    cleaned, meta, _ = load_item("076")
    assert _cls(cleaned, meta)["type"] == "news"
    cleaned, meta, _ = load_item("080")
    assert _cls(cleaned, meta)["type"] == "other"


def test_short_text_not_business_case():
    from conftest import load_item
    cleaned, meta, _ = load_item("001")
    r = _cls(cleaned[:300], meta)
    assert r["type"] != "business_case"
