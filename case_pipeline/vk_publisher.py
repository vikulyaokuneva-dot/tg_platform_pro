# -*- coding: utf-8 -*-
"""Minimal, isolated VK API publisher for the AGRO lane.

The module never logs request parameters: they contain ``access_token``.
It distinguishes a deterministic VK API rejection from an ambiguous network
failure after a mutating request.  The latter is intentionally surfaced as
``uncertain`` so the queue can stop instead of creating a duplicate wall post.
"""
from dataclasses import dataclass
import logging
import time

import requests

from . import config

log = logging.getLogger("case_pipeline.vk")
API_URL = "https://api.vk.com/method/"
MAX_PHOTO_BYTES = 10 * 1024 * 1024
MIN_PHOTO_BYTES = 1024


@dataclass
class VkResult:
    ok: bool
    post_id: int = None
    owner_id: int = None
    error: str = ""
    error_code: int = None
    http_status: int = None
    retryable: bool = False
    uncertain: bool = False
    data: object = None


class VkPublisher:
    """VK API client.  Token and group id may be injected only by tests."""
    def __init__(self, token=None, group_id=None, timeout=None, retries=None,
                 sleep=time.sleep):
        self.token = token if token is not None else config.VK_ACCESS_TOKEN
        self.group_id = str(group_id if group_id is not None else config.VK_GROUP_ID or "").strip()
        self.timeout = timeout if timeout is not None else config.VK_TIMEOUT_SEC
        self.retries = retries if retries is not None else config.VK_RETRIES
        self.sleep = sleep

    def configured(self):
        return bool(self.token and self.group_id.isdigit() and int(self.group_id) > 0)

    @staticmethod
    def _error(code, message, http_status=None, retryable=False, uncertain=False):
        # VK error payload does not need request echoing; avoid carrying tokens
        # or signed upload URLs into logs/SQLite diagnostics.
        return VkResult(False, error="VK error%s: %s" %
                        ((" %s" % code) if code is not None else "", (message or "unknown")[:300]),
                        error_code=code, http_status=http_status,
                        retryable=retryable, uncertain=uncertain)

    def _api(self, method, params=None, mutating=False):
        if not self.configured():
            return self._error(None, "VK_ACCESS_TOKEN or VK_GROUP_ID is not configured")
        payload = dict(params or {})
        payload.update({"access_token": self.token, "v": config.VK_API_VERSION})
        last = None
        for attempt in range(self.retries + 1):
            try:
                response = requests.post(API_URL + method, data=payload,
                                         timeout=self.timeout)
            except requests.RequestException as exc:
                if mutating:
                    return self._error(None, "network error during %s: %s" %
                                       (method, type(exc).__name__),
                                       retryable=True, uncertain=True)
                last = self._error(None, "network error during %s: %s" %
                                   (method, type(exc).__name__), retryable=True)
            else:
                if response.status_code == 429:
                    last = self._error(429, "HTTP rate limit", response.status_code, retryable=True)
                elif response.status_code >= 500:
                    if mutating:
                        return self._error(response.status_code,
                                           "server error during %s" % method,
                                           response.status_code, retryable=True,
                                           uncertain=True)
                    last = self._error(response.status_code,
                                       "server error during %s" % method,
                                       response.status_code, retryable=True)
                else:
                    try:
                        data = response.json()
                    except ValueError:
                        if mutating:
                            return self._error(response.status_code,
                                               "invalid response during %s" % method,
                                               response.status_code, uncertain=True)
                        last = self._error(response.status_code,
                                           "invalid response during %s" % method,
                                           response.status_code, retryable=True)
                    else:
                        err = data.get("error") if isinstance(data, dict) else None
                        if not err:
                            return VkResult(True, http_status=response.status_code,
                                            data=data.get("response") if isinstance(data, dict) else data)
                        code = err.get("error_code")
                        message = err.get("error_msg") or "VK API error"
                        # Error response is a confirmed non-publication, so a
                        # small bounded retry for VK throttling is safe.
                        last = self._error(code, message, response.status_code,
                                           retryable=code in (6, 9))
                        if code not in (6, 9):
                            return last
            if attempt < self.retries and last and last.retryable:
                self.sleep(min(2 ** attempt, 4))
                continue
            return last or self._error(None, "VK API call failed")
        return last or self._error(None, "VK API call failed")

    def check_access(self, require_photo_upload=False):
        """Verifies token + requested community without creating a post."""
        result = self._api("groups.getById", {"group_id": self.group_id})
        if not result.ok:
            return result
        groups = result.data if isinstance(result.data, list) else []
        group = groups[0] if groups else {}
        if str(group.get("id") or "") != self.group_id:
            return self._error(None, "requested VK group is not available to this token")
        info = {"group": {"id": group.get("id"), "name": group.get("name", "")}}
        if not require_photo_upload:
            return VkResult(True, data=info)
        upload = self._api("photos.getWallUploadServer", {"group_id": self.group_id})
        if not upload.ok:
            if upload.error_code == 27:
                upload.error += ("; photo upload is unavailable for this token. "
                                 "Use a VK user access token with wall and photos permissions "
                                 "for this community, or publish text-only.")
            return upload
        info["upload_url"] = upload.data.get("upload_url") if isinstance(upload.data, dict) else ""
        if not info["upload_url"]:
            return self._error(None, "VK did not return a wall photo upload URL")
        return VkResult(True, data=info)

    @staticmethod
    def prepare_photo(photo_bytes):
        """Accepts only common image formats and never performs conversion."""
        data = photo_bytes or b""
        if not (MIN_PHOTO_BYTES <= len(data) <= MAX_PHOTO_BYTES):
            return None, "image size must be between %d and %d bytes" % (MIN_PHOTO_BYTES, MAX_PHOTO_BYTES)
        if data.startswith(b"\xff\xd8\xff"):
            return ("photo.jpg", "image/jpeg"), ""
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            return ("photo.png", "image/png"), ""
        return None, "unsupported image format (only JPEG and PNG are accepted)"

    def _upload_photo(self, photo_bytes):
        upload_server = self._api("photos.getWallUploadServer", {"group_id": self.group_id})
        if not upload_server.ok:
            return upload_server
        upload_url = (upload_server.data or {}).get("upload_url")
        if not upload_url:
            return self._error(None, "VK did not return a wall photo upload URL")
        meta, error = self.prepare_photo(photo_bytes)
        if error:
            return self._error(None, error)
        try:
            response = requests.post(upload_url,
                                     files={"photo": (meta[0], photo_bytes, meta[1])},
                                     timeout=self.timeout)
            data = response.json()
        except (requests.RequestException, ValueError) as exc:
            # An upload can have succeeded server-side.  Keep the queue locked
            # rather than starting a new media chain automatically.
            return self._error(None, "photo upload outcome is uncertain: %s" % type(exc).__name__,
                               retryable=True, uncertain=True)
        if response.status_code != 200 or not all(data.get(k) is not None for k in ("server", "photo", "hash")):
            return self._error(response.status_code, "VK photo upload rejected", response.status_code)
        saved = self._api("photos.saveWallPhoto", {
            "group_id": self.group_id, "server": data["server"],
            "photo": data["photo"], "hash": data["hash"]}, mutating=True)
        if not saved.ok:
            return saved
        photos = saved.data if isinstance(saved.data, list) else []
        photo = photos[0] if photos else {}
        if not photo.get("id") or photo.get("owner_id") is None:
            return self._error(None, "VK did not return saved wall photo")
        attachment = "photo%s_%s" % (photo["owner_id"], photo["id"])
        if photo.get("access_key"):
            attachment += "_" + str(photo["access_key"])
        return VkResult(True, data={"attachment": attachment})

    def publish(self, text, photo_bytes=None, dry_run=False):
        """Creates one wall post.  ``dry_run`` performs no VK API call."""
        if dry_run:
            return VkResult(True, post_id=0, owner_id=-int(self.group_id or 0), data={"dry_run": True})
        if not (text or "").strip():
            return self._error(None, "VK post text is empty")
        attachment = ""
        if photo_bytes is not None:
            photo = self._upload_photo(photo_bytes)
            if not photo.ok:
                return photo
            attachment = photo.data["attachment"]
        params = {"owner_id": -int(self.group_id), "from_group": 1,
                  "message": text.strip()}
        if attachment:
            params["attachments"] = attachment
        posted = self._api("wall.post", params, mutating=True)
        if not posted.ok:
            return posted
        data = posted.data if isinstance(posted.data, dict) else {}
        post_id = data.get("post_id")
        if not post_id:
            return self._error(None, "VK did not return wall post id", uncertain=True)
        return VkResult(True, post_id=int(post_id), owner_id=-int(self.group_id),
                        http_status=posted.http_status)
