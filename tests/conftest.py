# -*- coding: utf-8 -*-
import io
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

HOLDOUT = os.path.join(ROOT, "parser_poc_results", "classifier_holdout_80")


@pytest.fixture(autouse=True)
def hermetic_env(monkeypatch):
    """Тесты не должны трогать реальные секреты/API:
    GigaChat-доступность и BOT_TOKEN выключаются на весь тест."""
    from case_pipeline import config
    from case_pipeline.ai import GigaChatProvider
    monkeypatch.setattr(GigaChatProvider, "available", False, raising=False)
    monkeypatch.setattr(config, "BOT_TOKEN", None)
    monkeypatch.setattr(config, "GIGACHAT_KEY", None)


def load_item(item_id):
    d = os.path.join(HOLDOUT, item_id)
    cleaned = io.open(os.path.join(d, "cleaned.txt"), encoding="utf-8").read()
    meta = json.load(io.open(os.path.join(d, "metadata.json"), encoding="utf-8"))
    html = io.open(os.path.join(d, "raw.html"), encoding="utf-8").read()
    return cleaned, meta, html


@pytest.fixture(scope="session")
def mindbox_case():
    return load_item("001")


@pytest.fixture(scope="session")
def ibm_case():
    return load_item("032")


@pytest.fixture(scope="session")
def netguru_howto():
    return load_item("048")
