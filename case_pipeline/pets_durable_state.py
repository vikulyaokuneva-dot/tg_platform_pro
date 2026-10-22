# -*- coding: utf-8 -*-
"""Versioned durable storage for the PETS SQLite publication ledger.

The backend uses a separate Git branch and GitHub Contents API. Every
checkpoint makes a versioned commit; a SHA precondition prevents a stale run
from overwriting newer state. The workflow's pets-channel concurrency remains
the primary lock.
"""
import base64
import os

import requests


class DurableStateError(RuntimeError):
    """Backend unavailable or unsafe; callers must fail closed before send."""


class GitHubStateBackend:
    def __init__(self, repository, token, branch="pets-state",
                 path="pets/pets_channel.db", base_branch="main",
                 api_url="https://api.github.com", session=requests):
        self.repository = repository or ""
        self.token = token or ""
        self.branch = branch
        self.path = path
        self.base_branch = base_branch
        self.api_url = api_url.rstrip("/")
        self.session = session
        self.sha = None

    @property
    def configured(self):
        return bool(self.repository and self.token and self.branch and self.path)

    def _headers(self):
        return {"Accept": "application/vnd.github+json",
                "Authorization": "Bearer " + self.token,
                "X-GitHub-Api-Version": "2022-11-28"}

    def _url(self, suffix):
        return "%s/repos/%s%s" % (self.api_url, self.repository, suffix)

    def _require_configured(self):
        if not self.configured:
            raise DurableStateError("GitHub PETS state backend is not configured")

    def _ensure_branch(self):
        ref = self.session.get(self._url("/git/ref/heads/%s" % self.branch),
                               headers=self._headers(), timeout=20)
        if ref.status_code == 200:
            return
        if ref.status_code != 404:
            raise DurableStateError("state branch lookup failed: HTTP %s" % ref.status_code)
        base = self.session.get(self._url("/git/ref/heads/%s" % self.base_branch),
                                headers=self._headers(), timeout=20)
        if base.status_code != 200:
            raise DurableStateError("state base branch lookup failed: HTTP %s" % base.status_code)
        base_sha = (base.json().get("object") or {}).get("sha")
        if not base_sha:
            raise DurableStateError("state base branch has no SHA")
        created = self.session.post(self._url("/git/refs"), headers=self._headers(), timeout=20,
                                    json={"ref": "refs/heads/%s" % self.branch, "sha": base_sha})
        if created.status_code not in (201, 422):
            raise DurableStateError("state branch creation failed: HTTP %s" % created.status_code)

    def restore(self, local_path):
        """Restore state before a run. A missing state is safe only in dry-run."""
        self._require_configured()
        self._ensure_branch()
        res = self.session.get(self._url("/contents/%s" % self.path), headers=self._headers(),
                               params={"ref": self.branch}, timeout=30)
        if res.status_code == 404:
            self.sha = None
            return {"status": "missing", "durable": True}
        if res.status_code != 200:
            raise DurableStateError("state restore failed: HTTP %s" % res.status_code)
        data = res.json()
        try:
            payload = base64.b64decode((data.get("content") or "").replace("\n", ""))
        except Exception as exc:
            raise DurableStateError("state restore payload is invalid") from exc
        if not payload:
            raise DurableStateError("state restore payload is empty")
        os.makedirs(os.path.dirname(os.path.abspath(local_path)), exist_ok=True)
        with open(local_path, "wb") as fh:
            fh.write(payload)
        self.sha = data.get("sha")
        return {"status": "restored", "durable": True}

    def checkpoint(self, local_path, phase="checkpoint"):
        """Persist a snapshot. Conflict is fail-closed, never overwritten."""
        self._require_configured()
        if not os.path.exists(local_path):
            raise DurableStateError("local PETS state is missing")
        with open(local_path, "rb") as fh:
            encoded = base64.b64encode(fh.read()).decode("ascii")
        body = {"message": "pets state: %s" % phase,
                "content": encoded, "branch": self.branch}
        if self.sha:
            body["sha"] = self.sha
        res = self.session.put(self._url("/contents/%s" % self.path), headers=self._headers(),
                               json=body, timeout=40)
        if res.status_code not in (200, 201):
            if res.status_code in (409, 422):
                raise DurableStateError("state checkpoint conflict")
            raise DurableStateError("state checkpoint failed: HTTP %s" % res.status_code)
        self.sha = ((res.json().get("content") or {}).get("sha"))
        if not self.sha:
            raise DurableStateError("state checkpoint response lacks SHA")
        return {"status": "checkpointed", "durable": True, "phase": phase}


def from_config(config):
    return GitHubStateBackend(config.PETS_STATE_REPOSITORY,
                              config.PETS_STATE_GITHUB_TOKEN,
                              branch=config.PETS_STATE_BRANCH,
                              path=config.PETS_STATE_PATH,
                              base_branch=config.PETS_STATE_BASE_BRANCH,
                              api_url=config.PETS_GITHUB_API_URL)
