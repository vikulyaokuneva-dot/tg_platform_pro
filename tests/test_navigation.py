# -*- coding: utf-8 -*-
"""Навигация: генерация из реальной истории, группировка, БЕЗ Telegram."""
import os

import pytest

from case_pipeline import navigation, storage as storage_mod


@pytest.fixture()
def st(tmp_path):
    s = storage_mod.Storage(str(tmp_path / "nav.db"))
    for i, (cid, tags, ctype, comp) in enumerate([
            ("case-1", "#Кейс #CRM #Mindbox", "case", "Mindbox"),
            ("case-2", "#Кейс #Маркетинг #IBM", "case", "IBM"),
            ("news-1", "#НовостьДня #Автоматизация", "news", "")]):
        mid = s.add("https://x.ru/%s" % cid, "mindbox")
        s.update(mid, status="post_ready", company=comp)
        s.mark_published(mid, 300 + i, "-100", cid, hashtags=tags, content_type=ctype)
    return s


def test_navigation_groups_real_tags(st, tmp_path, monkeypatch):
    from case_pipeline import config
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "nav.db"))
    text = navigation.build_text(st)
    assert "НАВИГАЦИЯ" in text
    assert "#Кейс" in text and "#НовостьДня" in text
    assert "#CRM" in text and "#Маркетинг" in text          # DOMAIN
    assert "#Mindbox" in text and "#IBM" in text            # COMPANY
    assert "#AIDirectorWB" in text and "#ShawarmaLab" in text  # OWN (словарь)
    assert "Кейсы автоматизации (2)" in text and "Новости дня (1)" in text


def test_rebuild_writes_file_no_telegram(st, tmp_path, monkeypatch):
    from case_pipeline import config
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "nav.db"))

    def boom(*a, **k):
        raise AssertionError("navigation must NOT send to Telegram")
    monkeypatch.setattr("case_pipeline.telegram.publish_post", boom)
    monkeypatch.setattr("case_pipeline.telegram.send_message", boom)
    text = navigation.rebuild(st, runs_dir=str(tmp_path))
    assert text and os.path.exists(str(tmp_path / "nav.db"))
    assert os.path.exists(str(tmp_path / "navigation.txt"))
    assert os.path.exists(str(tmp_path / "navigation.txt"))
