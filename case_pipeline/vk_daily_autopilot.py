# -*- coding: utf-8 -*-
"""Durable, image-required VK publishing lane.

The queue is a versioned file committed to the repository, not an Actions
cache or the AGRO SQLite database.  SQLite may be used as an optional intake
source, but a cache miss never erases an already prepared VK item.  A durable
``publishing`` claim is intentionally never retried automatically: this is
the only safe response to an ambiguous ``wall.post`` outcome.
"""
import argparse
import hashlib
import json
import os
import sqlite3
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from . import ai, config, httpclient, vk_autopilot
from .vk_publisher import VkPublisher


STATE_VERSION = 1
PUBLISHED_CONTROL_MATERIAL_ID = 29
ALLOWED_MEDIA_LICENSES = {"own", "licensed", "generated"}
TERMINAL_STATES = {"published", "publishing"}


class DailyPublishBlocked(RuntimeError):
    """The queue cannot safely make a network-side change."""


class DailyQueueError(RuntimeError):
    """The versioned queue is invalid or cannot be written safely."""


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _empty_state():
    return {"version": STATE_VERSION, "materials": {}}


def _load_state(path):
    if not os.path.exists(path):
        raise DailyQueueError("durable VK daily queue is unavailable")
    try:
        with open(path, encoding="utf-8") as fh:
            state = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        raise DailyQueueError("durable VK daily queue is unreadable") from exc
    if (not isinstance(state, dict) or state.get("version") != STATE_VERSION
            or not isinstance(state.get("materials"), dict)):
        raise DailyQueueError("durable VK daily queue has an unsupported format")
    for key, record in state["materials"].items():
        if not str(key).isdigit() or not isinstance(record, dict):
            raise DailyQueueError("durable VK daily queue contains an invalid material")
        if int(key) != record.get("material_id") or not record.get("source_url") or not record.get("fingerprint"):
            raise DailyQueueError("durable VK daily queue material identity is incomplete")
        text = record.get("vk_text")
        expected = hashlib.sha256(
            (str(record["material_id"]) + "\n" + record["source_url"] + "\n" + str(text or "")).encode("utf-8")
        ).hexdigest()
        if (not isinstance(text, str) or record["fingerprint"] != expected
                or ("Источник: " + record["source_url"]) not in text):
            raise DailyQueueError("durable VK daily queue material failed integrity checks")
    return state


def _write_state(path, state):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    with open(temporary, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(state, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(temporary, target)


def _runtime_media_path(state_path, material_id):
    """Ephemeral same-run copy avoids downloading an approved AGRO image twice."""
    return Path(state_path).parent / ".runtime" / ("%s.bin" % material_id)


def _media_error(record, root_dir, fetch_source=False):
    """Load only an explicitly approved local or linked AGRO-source asset."""
    media = record.get("media") or {}
    license_kind = media.get("license")
    path = media.get("path")
    checksum = media.get("sha256")
    if license_kind not in ALLOWED_MEDIA_LICENSES:
        return "media license is not explicitly approved", None
    if not isinstance(media.get("rights_reference"), str) or not media["rights_reference"].strip():
        return "media rights evidence is absent", None
    source_image_url = media.get("source_image_url")
    if source_image_url:
        if (media.get("origin") != "agro_source"
                or source_image_url != record.get("agro_image_url")
                or not source_image_url.startswith(("https://", "http://"))):
            return "AGRO source image link is not bound to this material", None
        if not isinstance(checksum, str) or len(checksum) != 64:
            return "approved AGRO image checksum is absent", None
        if not fetch_source:
            return "approved AGRO image has not been prepared", None
        try:
            data = httpclient.fetch_bytes(source_image_url)
        except httpclient.FetchError:
            return "approved AGRO image is unavailable", None
        if hashlib.sha256(data).hexdigest() != checksum:
            return "approved AGRO image checksum does not match", None
        _, image_error = VkPublisher.prepare_photo(data)
        if image_error:
            return image_error, None
        return "", data
    if not isinstance(path, str) or not path or os.path.isabs(path):
        return "approved local media file is unavailable", None
    root = Path(root_dir).resolve()
    candidate = (root / path).resolve()
    if root not in candidate.parents or not candidate.is_file():
        return "approved local media file is unavailable", None
    data = candidate.read_bytes()
    if not isinstance(checksum, str) or hashlib.sha256(data).hexdigest() != checksum:
        return "approved local media checksum does not match", None
    _, image_error = VkPublisher.prepare_photo(data)
    if image_error:
        return image_error, None
    return "", data


def _is_published_today(record, now=None):
    published_at = record.get("published_at") or ""
    return bool(published_at) and published_at[:10] == (now or _now())[:10]


def _next_publishable(state, root_dir, now=None, fetch_source=False):
    """Return first durable pending record with verified local media."""
    for material_id in sorted(state["materials"], key=lambda value: int(value)):
        record = state["materials"][material_id]
        if record.get("status") != "pending":
            continue
        error, image = _media_error(record, root_dir, fetch_source=fetch_source)
        if not error:
            return material_id, record, image
    return None, None, None


def queue_diagnostics(state_path, root_dir=".", verify_source=False):
    """Safe aggregate status; never logs source text, URL, or media paths."""
    state = _load_state(state_path)
    counts = {}
    media_reasons = {}
    for record in state["materials"].values():
        status = record.get("status", "invalid")
        counts[status] = counts.get(status, 0) + 1
        if status == "pending":
            error, _ = _media_error(record, root_dir, fetch_source=verify_source)
            if error:
                media_reasons[error] = media_reasons.get(error, 0) + 1
    material_id, _, _ = _next_publishable(state, root_dir, fetch_source=verify_source)
    return {"queue_version": STATE_VERSION, "materials": len(state["materials"]),
            "states": counts, "media_holds": media_reasons,
            "publishable_material_present": material_id is not None,
            "control_material_29_state": (state["materials"].get("29") or {}).get("status")}


def sync_verified_sqlite(state_path, db_path, root_dir="."):
    """Optionally import verified AGRO text; cache is intake only, never state.

    This helper does not alter AGRO rows or the old ``vk_publications`` table.
    New imported items are deliberately held in ``pending`` until an approved
    local image and its license metadata are committed to this queue.
    """
    state = _load_state(state_path)
    outcome = {"database_available": False, "added": 0, "already_present": 0,
               "media_linked": 0, "rejected": 0}
    if not os.path.isfile(db_path):
        return outcome
    try:
        db = sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)
        db.row_factory = sqlite3.Row
        rows = db.execute(
            "SELECT id, post_text, image_url FROM materials "
            "WHERE status IN ('post_ready', 'published') ORDER BY id"
        ).fetchall()
    except (OSError, sqlite3.Error):
        return outcome
    outcome["database_available"] = True
    try:
        for row in rows:
            material_id = str(row["id"])
            if material_id in state["materials"]:
                outcome["already_present"] += 1
                current = state["materials"][material_id]
                image_url = (row["image_url"] or "").strip()
                media = current.get("media") or {}
                # Preserve a human-approved licence/reference/checksum, but
                # bind its AGRO URL to the verified material if it was absent.
                if image_url and not media.get("source_image_url"):
                    media.update({"origin": "agro_source", "source_image_url": image_url,
                                  "license": media.get("license"),
                                  "rights_reference": media.get("rights_reference"),
                                  "sha256": media.get("sha256"), "path": None})
                    current["media"] = media
                    current["agro_image_url"] = image_url
                    outcome["media_linked"] += 1
                continue
            text = vk_autopilot.build_vk_post(row["post_text"], provider=ai.NullProvider())
            if vk_autopilot.vk_post_contract_error(text):
                outcome["rejected"] += 1
                continue
            _, source_url = vk_autopilot._split_verified_post(row["post_text"])
            if not source_url or ("Источник: " + source_url) not in text:
                outcome["rejected"] += 1
                continue
            fingerprint = hashlib.sha256(
                (material_id + "\n" + source_url + "\n" + text).encode("utf-8")).hexdigest()
            state["materials"][material_id] = {
                "material_id": int(material_id), "source_url": source_url,
                "fingerprint": fingerprint, "vk_text": text,
                "editorial_status": "verified", "agro_image_url": (row["image_url"] or "").strip() or None,
                "media": {"origin": "agro_source", "source_image_url": (row["image_url"] or "").strip() or None,
                          "license": None, "rights_reference": None, "path": None, "sha256": None},
                "status": "pending", "created_at": _now(),
            }
            outcome["added"] += 1
    finally:
        db.close()
    if outcome["added"] or outcome["media_linked"]:
        _write_state(state_path, state)
    return outcome


def claim_one(state_path, root_dir=".", now=None):
    """Persist a claim before any upload or wall.post request."""
    state = _load_state(state_path)
    if any(_is_published_today(record, now) for record in state["materials"].values()):
        raise DailyPublishBlocked("daily VK limit is already reached")
    material_id, record, image = _next_publishable(state, root_dir, now, fetch_source=True)
    if not record:
        raise DailyPublishBlocked("no verified queue item has approved local media")
    record["status"] = "publishing"
    record["claimed_at"] = now or _now()
    record.pop("last_error", None)
    _write_state(state_path, state)
    # Source bytes were already checked above; keep them only for this runner.
    # The committed claim and SHA-256 remain the cross-run safety boundary.
    if image is not None and (record.get("media") or {}).get("source_image_url"):
        runtime = _runtime_media_path(state_path, material_id)
        runtime.parent.mkdir(parents=True, exist_ok=True)
        runtime.write_bytes(image)
    return deepcopy(record)


def publish_claimed(state_path, root_dir=".", publisher=None, now=None):
    """Upload one approved image and post one already-claimed queue record."""
    state = _load_state(state_path)
    claimed = [(key, item) for key, item in state["materials"].items()
               if item.get("status") == "publishing"]
    if len(claimed) != 1:
        raise DailyPublishBlocked("exactly one durable publishing claim is required")
    material_id, record = claimed[0]
    runtime = _runtime_media_path(state_path, material_id)
    image = None
    if runtime.is_file():
        candidate = runtime.read_bytes()
        expected = (record.get("media") or {}).get("sha256")
        if hashlib.sha256(candidate).hexdigest() == expected:
            _, image_error = VkPublisher.prepare_photo(candidate)
            if not image_error:
                image = candidate
    media_error = ""
    if image is None:
        media_error, image = _media_error(record, root_dir, fetch_source=True)
    if media_error:
        record["last_error"] = {"kind": "media", "reason": media_error}
        _write_state(state_path, state)
        raise DailyPublishBlocked(media_error)
    client = publisher or VkPublisher()
    access = client.check_access(require_photo_upload=True)
    if not access.ok:
        record["last_error"] = {"kind": access.error_kind or "access", "code": access.error_code,
                                "http_status": access.http_status}
        _write_state(state_path, state)
        raise DailyQueueError("VK access or photo upload check failed")
    result = client.publish(record["vk_text"], photo_bytes=image, dry_run=False)
    if result.ok:
        record.update({"status": "published", "vk_post_id": result.post_id,
                       "vk_owner_id": result.owner_id, "published_at": now or _now()})
        _write_state(state_path, state)
        return result
    record["last_error"] = {"kind": result.error_kind or "unknown", "code": result.error_code,
                            "http_status": result.http_status, "uncertain": bool(result.uncertain)}
    # Both a timeout and a confirmed error retain the claim.  Retrying after a
    # confirmed failure is a separate, deliberate editorial decision; a timeout
    # must first be reconciled manually to avoid a duplicate wall post.
    _write_state(state_path, state)
    if result.uncertain:
        raise DailyPublishBlocked("wall.post outcome is uncertain; durable claim remains blocked")
    raise DailyQueueError("VK wall.post failed; durable claim remains blocked")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Durable, image-required VK daily queue")
    parser.add_argument("action", choices=("preview", "sync", "claim", "publish"))
    parser.add_argument("--state", required=True)
    parser.add_argument("--root", default=".")
    parser.add_argument("--db", default="data/agro_channel.db")
    parser.add_argument("--verify-media", action="store_true",
                        help="read approved AGRO image URLs without publishing")
    args = parser.parse_args(argv)
    try:
        if args.action == "preview":
            print("VK daily queue diagnostic: %s" % json.dumps(
                queue_diagnostics(args.state, args.root, verify_source=args.verify_media),
                sort_keys=True, ensure_ascii=True))
        elif args.action == "sync":
            print("VK daily queue sync: %s" % json.dumps(
                sync_verified_sqlite(args.state, args.db, args.root), sort_keys=True, ensure_ascii=True))
        elif args.action == "claim":
            record = claim_one(args.state, args.root)
            print("VK daily queue claim: material_id=%s status=publishing" % record["material_id"])
        else:
            if not config.VK_PUBLISH:
                raise DailyPublishBlocked("VK_PUBLISH is not enabled")
            result = publish_claimed(args.state, args.root)
            print("VK daily publish: OK post_id=%s" % result.post_id)
    except (DailyPublishBlocked, DailyQueueError) as exc:
        print("VK daily autopilot blocked: %s" % str(exc)[:200], file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
