# -*- coding: utf-8 -*-
import base64

import pytest

from case_pipeline.pets_durable_state import DurableStateError, GitHubStateBackend


class Resp:
    def __init__(self, status, payload=None):
        self.status_code = status
        self._payload = payload or {}

    def json(self):
        return self._payload


class Session:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, *args, **kwargs):
        self.calls.append(("get", args, kwargs))
        return self.responses.pop(0)

    def post(self, *args, **kwargs):
        self.calls.append(("post", args, kwargs))
        return self.responses.pop(0)

    def put(self, *args, **kwargs):
        self.calls.append(("put", args, kwargs))
        return self.responses.pop(0)


def test_github_backend_restores_and_checkpoints_with_sha(tmp_path):
    local = tmp_path / "pets.db"
    encoded = base64.b64encode(b"sqlite-fixture").decode()
    session = Session([
        Resp(200),  # state branch exists
        Resp(200, {"content": encoded, "sha": "old-sha"}),
        Resp(200, {"content": {"sha": "new-sha"}}),
    ])
    backend = GitHubStateBackend("owner/repo", "test-token", session=session)
    assert backend.restore(str(local))["status"] == "restored"
    assert local.read_bytes() == b"sqlite-fixture"
    local.write_bytes(b"new-sqlite")
    assert backend.checkpoint(str(local), "claimed")["phase"] == "claimed"
    payload = session.calls[-1][2]["json"]
    assert payload["sha"] == "old-sha"
    assert base64.b64decode(payload["content"]) == b"new-sqlite"
    assert "test-token" not in str(payload)


def test_github_backend_conflict_fails_closed(tmp_path):
    local = tmp_path / "pets.db"
    local.write_bytes(b"sqlite")
    backend = GitHubStateBackend("owner/repo", "test-token", session=Session([Resp(409)]))
    with pytest.raises(DurableStateError, match="conflict"):
        backend.checkpoint(str(local))
