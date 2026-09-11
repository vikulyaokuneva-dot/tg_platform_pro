# -*- coding: utf-8 -*-
"""Telegram publisher на моках HTTP: никаких реальных отправлений в тестах."""
import pytest
import requests

from case_pipeline import telegram


class FakeResp:
    def __init__(self, payload, status=200):
        self._p, self.status_code = payload, status
        self.content = b"{}"

    def json(self):
        return self._p


def test_send_ok(monkeypatch):
    monkeypatch.setattr(requests, "post",
                        lambda *a, **k: FakeResp({"ok": True, "result": {"message_id": 77}}))
    res = telegram.send_message("123:ABC", "-100", "текст поста")
    assert res.ok and res.message_id == 77


def test_send_channel_error(monkeypatch):
    monkeypatch.setattr(requests, "post",
                        lambda *a, **k: FakeResp({"ok": False, "description": "chat not found"}, 400))
    res = telegram.send_message("123:ABC", "-100", "текст")
    assert not res.ok and "400" in str(res.error)


def test_dry_run_no_http(monkeypatch):
    calls = []
    monkeypatch.setattr(requests, "post", lambda *a, **k: calls.append(a))
    res = telegram.send_message("123:ABC", "-100", "текст", dry_run=True)
    assert res.ok and res.message_id == 0
    assert not calls


def test_no_token_blocked(monkeypatch):
    res = telegram.send_message(None, "-100", "x")
    assert not res.ok and "token" in str(res.error).lower()
