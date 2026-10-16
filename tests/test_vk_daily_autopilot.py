# -*- coding: utf-8 -*-
import hashlib
import io
import json
import os

import pytest

from case_pipeline import storage as storage_mod, vk_daily_autopilot
from case_pipeline.vk_publisher import VkResult


def _record(material_id=77, status="pending", media=None):
    source = "https://example.test/agro/%s" % material_id
    text = ("🌿 Проверенный материал %s\n\n"
            "Практическая рекомендация взята из проверенного материала.\n\n"
            "Источник: %s" % (material_id, source))
    return {"material_id": material_id, "source_url": source,
            "fingerprint": hashlib.sha256(
                (str(material_id) + "\n" + source + "\n" + text).encode("utf-8")).hexdigest(),
            "vk_text": text, "editorial_status": "verified", "status": status,
            "media": media or {"license": None, "path": None, "sha256": None}}


def _write_queue(tmp_path, records):
    path = tmp_path / "queue.json"
    path.write_text(json.dumps({"version": 1, "materials": {
        str(item["material_id"]): item for item in records}}, ensure_ascii=False), encoding="utf-8")
    return str(path)


def _approved_media(tmp_path, license_kind="own"):
    assets = tmp_path / "assets"
    assets.mkdir(exist_ok=True)
    path = assets / "approved.jpg"
    data = b"\xff\xd8\xff" + b"x" * 2048
    path.write_bytes(data)
    return {"license": license_kind, "rights_reference": "internal-rights-record-1",
            "path": "assets/approved.jpg",
            "sha256": hashlib.sha256(data).hexdigest()}


def test_daily_queue_blocks_missing_or_unlicensed_media(tmp_path):
    missing = _write_queue(tmp_path, [_record()])
    report = vk_daily_autopilot.queue_diagnostics(missing, str(tmp_path))
    assert report["publishable_material_present"] is False
    assert report["media_holds"] == {"media license is not explicitly approved": 1}
    with pytest.raises(vk_daily_autopilot.DailyPublishBlocked):
        vk_daily_autopilot.claim_one(missing, str(tmp_path))

    unlicensed = _write_queue(tmp_path, [_record(78, media=_approved_media(tmp_path, "source"))])
    with pytest.raises(vk_daily_autopilot.DailyPublishBlocked):
        vk_daily_autopilot.claim_one(unlicensed, str(tmp_path))


def test_daily_queue_claims_once_and_does_not_republish(tmp_path):
    state = _write_queue(tmp_path, [_record(media=_approved_media(tmp_path))])
    claimed = vk_daily_autopilot.claim_one(state, str(tmp_path), now="2026-10-16T08:00:00Z")
    assert claimed["status"] == "publishing"
    with pytest.raises(vk_daily_autopilot.DailyPublishBlocked):
        vk_daily_autopilot.claim_one(state, str(tmp_path), now="2026-10-16T08:01:00Z")

    class Publisher:
        def check_access(self, require_photo_upload=False):
            assert require_photo_upload
            return VkResult(True)

        def publish(self, text, photo_bytes=None, dry_run=False):
            assert text and photo_bytes and not dry_run
            return VkResult(True, post_id=900, owner_id=-242354758)

    result = vk_daily_autopilot.publish_claimed(state, str(tmp_path), Publisher(), now="2026-10-16T08:02:00Z")
    assert result.post_id == 900
    stored = json.loads(open(state, encoding="utf-8").read())["materials"]["77"]
    assert stored["status"] == "published" and stored["vk_post_id"] == 900
    with pytest.raises(vk_daily_autopilot.DailyPublishBlocked):
        vk_daily_autopilot.claim_one(state, str(tmp_path), now="2026-10-16T08:03:00Z")


def test_daily_queue_keeps_claim_blocked_on_vk_error_or_timeout(tmp_path):
    for name, result in (("api", VkResult(False, error_kind="vk_api", error_code=15)),
                         ("timeout", VkResult(False, error_kind="network", uncertain=True))):
        folder = tmp_path / name
        folder.mkdir()
        state = _write_queue(folder, [_record(media=_approved_media(folder))])
        vk_daily_autopilot.claim_one(state, str(folder))

        class Publisher:
            def check_access(self, require_photo_upload=False):
                return VkResult(True)

            def publish(self, *args, **kwargs):
                return result

        with pytest.raises((vk_daily_autopilot.DailyQueueError, vk_daily_autopilot.DailyPublishBlocked)):
            vk_daily_autopilot.publish_claimed(state, str(folder), Publisher())
        record = json.loads(open(state, encoding="utf-8").read())["materials"]["77"]
        assert record["status"] == "publishing"
        assert record["last_error"]["kind"] == result.error_kind
        assert record["last_error"]["uncertain"] is result.uncertain


def test_daily_queue_cache_miss_is_safe_and_control_post_is_excluded(tmp_path):
    state = _write_queue(tmp_path, [_record(29, status="published"), _record(77)])
    outcome = vk_daily_autopilot.sync_verified_sqlite(state, str(tmp_path / "missing.db"), str(tmp_path))
    assert outcome == {"database_available": False, "added": 0, "already_present": 0, "rejected": 0}
    report = vk_daily_autopilot.queue_diagnostics(state, str(tmp_path))
    assert report["control_material_29_state"] == "published"
    loaded = json.loads(open(state, encoding="utf-8").read())
    assert loaded["materials"]["29"]["status"] == "published"


def test_daily_queue_sync_reads_agro_database_without_changing_telegram_rows(tmp_path):
    db_path = str(tmp_path / "agro.db")
    st = storage_mod.Storage(db_path)
    material_id = st.add("https://example.test/source", "source")
    original = ("Как сохранить чеснок\n\n"
                "Перед хранением просушите луковицы: влажные могут испортиться.\n\n"
                "Вывод: храните только сухие и целые луковицы.\n\n"
                "Источник: https://example.test/source")
    st.update(material_id, status="post_ready", post_text=original)
    st.close()
    state = _write_queue(tmp_path, [])

    outcome = vk_daily_autopilot.sync_verified_sqlite(state, db_path, str(tmp_path))

    assert outcome == {"database_available": True, "added": 1, "already_present": 0, "rejected": 0}
    restored = storage_mod.Storage(db_path)
    assert restored.get(material_id)["status"] == "post_ready"
    assert restored.get(material_id)["post_text"] == original
    assert restored.db.execute("SELECT COUNT(*) FROM vk_publications").fetchone()[0] == 0


def test_daily_queue_rejects_tampered_editorial_text(tmp_path):
    record = _record(media=_approved_media(tmp_path))
    record["vk_text"] = "changed"
    state = _write_queue(tmp_path, [record])
    with pytest.raises(vk_daily_autopilot.DailyQueueError):
        vk_daily_autopilot.queue_diagnostics(state, str(tmp_path))


def test_daily_workflow_is_independent_durable_and_disabled_by_default():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    workflow = io.open(os.path.join(root, ".github", "workflows", "vk_daily_autopilot.yml"),
                       encoding="utf-8").read()
    assert "workflow_dispatch:" in workflow and 'cron: "15 7 * * *"' in workflow
    assert "VK_ACCESS_TOKEN: ${{ secrets.VK_ACCESS_TOKEN }}" in workflow
    assert "VK_GROUP_ID: ${{ vars.VK_GROUP_ID }}" in workflow
    assert "VK_PUBLISH: ${{ vars.VK_DAILY_PUBLISH }}" in workflow
    assert "VK_DAILY_PUBLISH == '1'" in workflow
    assert "PUBLISH_ONE_DAILY_VK_POST" in workflow
    assert "concurrency:" in workflow and "vk-daily-autopilot" in workflow
    assert "git push origin HEAD:main" in workflow
    assert "uses: actions/cache" not in workflow and "runner.py" not in workflow
    assert "photos.getWallUploadServer" not in workflow
