# -*- coding: utf-8 -*-
"""One-off, fail-closed VK control-post helper.

It reads an already verified AGRO material from SQLite without changing that
database.  Durable duplicate protection is a versioned JSON claim file: the
workflow must push ``publishing`` before it can call ``wall.post``.
"""
import argparse
import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

from . import ai, vk_autopilot
from .vk_publisher import VkPublisher


class TestPublishBlocked(RuntimeError):
    """A durable state makes another send unsafe."""


class TestPublishError(RuntimeError):
    """The candidate cannot safely be used for a control post."""


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_state(path):
    if not os.path.exists(path):
        return {"version": 1, "materials": {}}
    with open(path, "r", encoding="utf-8") as fh:
        state = json.load(fh)
    if not isinstance(state, dict) or state.get("version") != 1 or not isinstance(state.get("materials"), dict):
        raise TestPublishError("invalid durable VK test state")
    return state


def _write_state(path, state):
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(state, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(temp, path)


def load_candidate(db_path, material_id):
    """Read and render exactly one verified AGRO material, without DB writes."""
    if not os.path.isfile(db_path):
        raise TestPublishError("AGRO database is unavailable")
    try:
        db = sqlite3.connect("file:%s?mode=ro" % os.path.abspath(db_path).replace("\\", "/"), uri=True)
        db.row_factory = sqlite3.Row
        row = db.execute(
            "SELECT id, status, url, post_text FROM materials "
            "WHERE id=? AND status IN ('post_ready', 'published')", (int(material_id),)).fetchone()
    except sqlite3.Error as exc:
        raise TestPublishError("AGRO database cannot be read: %s" % type(exc).__name__)
    finally:
        try:
            db.close()
        except UnboundLocalError:
            pass
    if not row or not (row["post_text"] or "").strip() or not (row["url"] or "").startswith(("https://", "http://")):
        raise TestPublishError("verified material text or source URL is unavailable")
    text = vk_autopilot.build_vk_post(row["post_text"], provider=ai.NullProvider())
    problem = vk_autopilot.vk_post_contract_error(text)
    if problem:
        raise TestPublishError("VK editorial gate: %s" % problem)
    _, source_url = vk_autopilot._split_verified_post(row["post_text"])
    if not source_url or ("Источник: " + source_url) not in text:
        raise TestPublishError("rendered VK text has no verified source link")
    fingerprint = hashlib.sha256((str(row["id"]) + "\n" + source_url + "\n" + text).encode("utf-8")).hexdigest()
    return {"material_id": int(row["id"]), "source_url": source_url,
            "text": text, "fingerprint": fingerprint}


def preview(db_path, state_path, material_id):
    candidate = load_candidate(db_path, material_id)
    state = _load_state(state_path)
    record = state["materials"].get(str(candidate["material_id"]))
    print("VK test preview: material_id=%s source_available=true state=%s" %
          (candidate["material_id"], (record or {}).get("status", "new")))
    print(candidate["text"])
    return candidate


def claim(db_path, state_path, material_id):
    candidate = load_candidate(db_path, material_id)
    state = _load_state(state_path)
    key = str(candidate["material_id"])
    if state["materials"].get(key):
        raise TestPublishBlocked("durable state already exists for this material")
    state["materials"][key] = {"status": "publishing", "fingerprint": candidate["fingerprint"],
                               "source_url": candidate["source_url"], "claimed_at": _now()}
    _write_state(state_path, state)
    print("VK test claim: material_id=%s status=publishing" % candidate["material_id"])
    return candidate


def publish_claimed(db_path, state_path, material_id, publisher=None):
    candidate = load_candidate(db_path, material_id)
    state = _load_state(state_path)
    record = state["materials"].get(str(candidate["material_id"]))
    if not record or record.get("status") != "publishing" or record.get("fingerprint") != candidate["fingerprint"]:
        raise TestPublishBlocked("no matching durable publishing claim")
    client = publisher or VkPublisher()
    access = client.check_access(require_photo_upload=False)
    if not access.ok:
        record["last_error"] = {"kind": access.error_kind or "access", "code": access.error_code,
                                "http_status": access.http_status}
        _write_state(state_path, state)
        raise TestPublishError("VK access check failed")
    result = client.publish(candidate["text"], photo_bytes=None, dry_run=False)
    if result.ok:
        record.update({"status": "published", "vk_post_id": result.post_id,
                       "vk_owner_id": result.owner_id, "published_at": _now()})
        _write_state(state_path, state)
        print("VK test publish: OK material_id=%s post_id=%s" %
              (candidate["material_id"], result.post_id))
        return result
    record["last_error"] = {"kind": result.error_kind or "unknown", "code": result.error_code,
                            "http_status": result.http_status, "uncertain": bool(result.uncertain)}
    _write_state(state_path, state)
    if result.uncertain:
        raise TestPublishBlocked("wall.post outcome is uncertain; durable claim remains blocked")
    raise TestPublishError("wall.post failed")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Safe one-off VK control post")
    parser.add_argument("action", choices=("preview", "claim", "publish"))
    parser.add_argument("--db", required=True)
    parser.add_argument("--state", required=True)
    parser.add_argument("--material-id", type=int, required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == "preview":
            preview(args.db, args.state, args.material_id)
        elif args.action == "claim":
            claim(args.db, args.state, args.material_id)
        else:
            publish_claimed(args.db, args.state, args.material_id)
    except (TestPublishBlocked, TestPublishError) as exc:
        print("VK test publish blocked: %s" % str(exc)[:200], file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
