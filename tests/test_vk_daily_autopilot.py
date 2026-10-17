# -*- coding: utf-8 -*-
import hashlib
import io
import json
import os

import pytest

from case_pipeline import httpclient, storage as storage_mod, vk_daily_autopilot
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
    tmp_path.mkdir(parents=True, exist_ok=True)
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


def _approved_agro_media(data):
    url = "https://images.example.test/agro.jpg"
    return {"origin": "agro_source", "source_image_url": url,
            "license": "licensed", "rights_reference": "license-record-77",
            "path": None, "sha256": hashlib.sha256(data).hexdigest()}, url


def _approved_licensed_url_media(data, attribution=None):
    url = "https://images.example.test/licensed.jpg"
    attribution = attribution or "Фото: Example Author / Example Archive — CC BY-SA 4.0"
    return {"origin": "licensed_url", "source_image_url": url,
            "license": "licensed", "rights_reference": "https://example.test/file",
            "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
            "attribution": attribution, "path": None,
            "sha256": hashlib.sha256(data).hexdigest()}, url


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


@pytest.mark.parametrize("stage, code, kind", [
    ("groups.getById", 5, "vk_api"),
    ("photos.getWallUploadServer", 27, "vk_api"),
])
def test_daily_queue_records_access_stage_before_any_upload_or_wall(tmp_path, stage, code, kind):
    state = _write_queue(tmp_path, [_record(media=_approved_media(tmp_path))])
    vk_daily_autopilot.claim_one(state, str(tmp_path))

    class Publisher:
        def check_access(self, require_photo_upload=False):
            assert require_photo_upload
            return VkResult(False, error="VK error %s" % code, error_code=code,
                            http_status=200, error_kind=kind, stage=stage)

        def publish(self, *args, **kwargs):
            raise AssertionError("publish must not run after access failure")

    with pytest.raises(vk_daily_autopilot.DailyQueueError, match="stage=%s" % stage):
        vk_daily_autopilot.publish_claimed(state, str(tmp_path), Publisher())
    record = json.loads(open(state, encoding="utf-8").read())["materials"]["77"]
    assert record["status"] == "publishing"
    assert record["last_error"] == {
        "stage": stage, "kind": kind, "code": code, "http_status": 200,
        "retryable": False, "uncertain": False, "message": "VK error %s" % code}


@pytest.mark.parametrize("stage, uncertain", [
    ("photo_multipart_upload", True),
    ("photos.saveWallPhoto", False),
    ("wall.post", True),
])
def test_daily_queue_records_each_publish_stage_and_never_retries_ambiguous_result(tmp_path, stage, uncertain):
    state = _write_queue(tmp_path, [_record(media=_approved_media(tmp_path))])
    vk_daily_autopilot.claim_one(state, str(tmp_path))

    class Publisher:
        def check_access(self, require_photo_upload=False):
            return VkResult(True, stage="photos.getWallUploadServer")

        def publish(self, *args, **kwargs):
            return VkResult(False, error="diagnostic failure", error_kind="network" if uncertain else "vk_api",
                            error_code=None if uncertain else 15, http_status=None if uncertain else 200,
                            uncertain=uncertain, retryable=uncertain, stage=stage)

    expected = vk_daily_autopilot.DailyPublishBlocked if uncertain else vk_daily_autopilot.DailyQueueError
    with pytest.raises(expected):
        vk_daily_autopilot.publish_claimed(state, str(tmp_path), Publisher())
    record = json.loads(open(state, encoding="utf-8").read())["materials"]["77"]
    assert record["status"] == "publishing"
    assert record["last_error"]["stage"] == stage
    assert record["last_error"]["uncertain"] is uncertain


def test_read_only_photo_access_diagnostic_is_safe():
    class Publisher:
        def configured(self):
            return True

        def check_access(self, require_photo_upload=False):
            assert require_photo_upload
            return VkResult(False, error="VK error 27: Group authorization failed",
                            error_code=27, http_status=200, error_kind="vk_api",
                            stage="photos.getWallUploadServer")

    assert vk_daily_autopilot.photo_access_diagnostics(Publisher()) == {
        "configured": True, "ok": False, "stage": "photos.getWallUploadServer",
        "kind": "vk_api", "code": 27, "http_status": 200,
        "retryable": False, "uncertain": False,
        "message": "VK error 27: Group authorization failed"}


def test_daily_queue_cache_miss_is_safe_and_control_post_is_excluded(tmp_path):
    state = _write_queue(tmp_path, [_record(29, status="published"), _record(77)])
    outcome = vk_daily_autopilot.sync_verified_sqlite(state, str(tmp_path / "missing.db"), str(tmp_path))
    assert outcome == {"database_available": False, "added": 0, "already_present": 0,
                       "media_linked": 0, "rejected": 0}
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

    assert outcome == {"database_available": True, "added": 1, "already_present": 0,
                       "media_linked": 0, "rejected": 0}
    restored = storage_mod.Storage(db_path)
    assert restored.get(material_id)["status"] == "post_ready"
    assert restored.get(material_id)["post_text"] == original
    assert restored.db.execute("SELECT COUNT(*) FROM vk_publications").fetchone()[0] == 0


def test_daily_queue_links_existing_agro_image_without_granting_rights(tmp_path):
    db_path = str(tmp_path / "agro.db")
    st = storage_mod.Storage(db_path)
    material_id = st.add("https://example.test/source", "source")
    verified = ("Практический материал\n\n"
                "Перед хранением просушите луковицы.\n\n"
                "Вывод: храните только сухие луковицы.\n\n"
                "Источник: https://example.test/source")
    image_url = "https://images.example.test/agro.jpg"
    st.update(material_id, status="post_ready", post_text=verified, image_url=image_url)
    st.close()
    state = _write_queue(tmp_path, [_record(material_id)])

    outcome = vk_daily_autopilot.sync_verified_sqlite(state, db_path, str(tmp_path))

    assert outcome == {"database_available": True, "added": 0, "already_present": 1,
                       "media_linked": 1, "rejected": 0}
    linked = json.loads(open(state, encoding="utf-8").read())["materials"][str(material_id)]
    assert linked["agro_image_url"] == image_url
    assert linked["media"]["source_image_url"] == image_url
    assert linked["media"]["license"] is None
    assert vk_daily_autopilot.queue_diagnostics(state, str(tmp_path))["publishable_material_present"] is False


def test_daily_queue_reuses_verified_agro_bytes_once_and_blocks_unavailable_url(tmp_path, monkeypatch):
    image = b"\xff\xd8\xff" + b"x" * 2048
    media, image_url = _approved_agro_media(image)
    record = _record(media=media)
    record["agro_image_url"] = image_url
    state = _write_queue(tmp_path, [record])
    calls = []
    monkeypatch.setattr(vk_daily_autopilot.httpclient, "fetch_bytes",
                        lambda url: calls.append(url) or image)

    vk_daily_autopilot.claim_one(state, str(tmp_path))

    class Publisher:
        def check_access(self, require_photo_upload=False):
            assert require_photo_upload
            return VkResult(True)

        def publish(self, text, photo_bytes=None, dry_run=False):
            assert photo_bytes == image and not dry_run
            return VkResult(True, post_id=101, owner_id=-242354758)

    vk_daily_autopilot.publish_claimed(state, str(tmp_path), Publisher())
    assert calls == [image_url]  # one existing downloader call, then runtime reuse

    bad_media, bad_url = _approved_agro_media(image)
    bad = _record(78, media=bad_media)
    bad["agro_image_url"] = bad_url
    bad_state = _write_queue(tmp_path / "bad", [bad])
    monkeypatch.setattr(vk_daily_autopilot.httpclient, "fetch_bytes",
                        lambda url: (_ for _ in ()).throw(httpclient.FetchError(url, status=404)))
    with pytest.raises(vk_daily_autopilot.DailyPublishBlocked):
        vk_daily_autopilot.claim_one(bad_state, str(tmp_path / "bad"))
    stored = json.loads(open(bad_state, encoding="utf-8").read())["materials"]["78"]
    assert stored["status"] == "pending"


@pytest.mark.parametrize("status, expected", [
    (403, "approved image HTTP 403 unavailable"),
    (404, "approved image HTTP 404 unavailable"),
    (429, "approved image HTTP 429 rate limited"),
])
def test_daily_queue_classifies_remote_image_http_failures(tmp_path, monkeypatch, status, expected):
    image = b"\xff\xd8\xff" + b"x" * 2048
    media, _ = _approved_licensed_url_media(image)
    record = _record(media=media)
    record["vk_text"] += "\n\n" + media["attribution"]
    record["fingerprint"] = hashlib.sha256(
        ("77\n" + record["source_url"] + "\n" + record["vk_text"]).encode("utf-8")).hexdigest()
    state = _write_queue(tmp_path, [record])
    monkeypatch.setattr(vk_daily_autopilot.httpclient, "fetch_bytes",
                        lambda url: (_ for _ in ()).throw(httpclient.FetchError(url, status=status)))
    report = vk_daily_autopilot.queue_diagnostics(state, str(tmp_path), verify_source=True)
    assert report["metadata_eligible_material_present"] is True
    assert report["verified_media_material_present"] is False
    assert report["publication_ready"] is False
    assert report["media_holds"] == {expected: 1}


def test_daily_queue_classifies_network_image_failure(tmp_path, monkeypatch):
    image = b"\xff\xd8\xff" + b"x" * 2048
    media, _ = _approved_licensed_url_media(image)
    record = _record(media=media)
    record["vk_text"] += "\n\n" + media["attribution"]
    record["fingerprint"] = hashlib.sha256(
        ("77\n" + record["source_url"] + "\n" + record["vk_text"]).encode("utf-8")).hexdigest()
    state = _write_queue(tmp_path, [record])
    monkeypatch.setattr(vk_daily_autopilot.httpclient, "fetch_bytes",
                        lambda url: (_ for _ in ()).throw(httpclient.FetchError(url, reason="ConnectionError")))
    assert vk_daily_autopilot.queue_diagnostics(state, str(tmp_path), verify_source=True)["media_holds"] == {
        "approved image network error (ConnectionError)": 1}


def test_daily_queue_accepts_only_explicitly_licensed_external_image_with_attribution(tmp_path, monkeypatch):
    image = b"\xff\xd8\xff" + b"x" * 2048
    media, _ = _approved_licensed_url_media(image)
    record = _record(media=media)
    record["vk_text"] += "\n\n" + media["attribution"]
    record["fingerprint"] = hashlib.sha256(
        ("77\n" + record["source_url"] + "\n" + record["vk_text"]).encode("utf-8")).hexdigest()
    state = _write_queue(tmp_path, [record])
    monkeypatch.setattr(vk_daily_autopilot.httpclient, "fetch_bytes", lambda url: image)

    report = vk_daily_autopilot.queue_diagnostics(state, str(tmp_path), verify_source=True)
    assert report["publishable_material_present"] is True
    assert vk_daily_autopilot.preview_material(state, 77, str(tmp_path), verify_source=True) == {
        "material_id": 77, "status": "pending", "media_location": "remote_url",
        "media_verified": True, "publication_ready": True, "publishable": True}
    claimed = vk_daily_autopilot.claim_one(state, str(tmp_path), expected_material_id=77)
    assert claimed["status"] == "publishing"

    missing_credit = _record(78, media=media)
    missing_credit["fingerprint"] = hashlib.sha256(
        ("78\n" + missing_credit["source_url"] + "\n" + missing_credit["vk_text"]).encode("utf-8")).hexdigest()
    blocked = _write_queue(tmp_path / "missing_credit", [missing_credit])
    assert vk_daily_autopilot.queue_diagnostics(blocked, str(tmp_path / "missing_credit"))["publishable_material_present"] is False
    with pytest.raises(vk_daily_autopilot.DailyPublishBlocked):
        vk_daily_autopilot.claim_one(blocked, str(tmp_path / "missing_credit"))


def test_daily_queue_refuses_a_different_requested_material(tmp_path):
    state = _write_queue(tmp_path, [_record(media=_approved_media(tmp_path))])
    with pytest.raises(vk_daily_autopilot.DailyPublishBlocked):
        vk_daily_autopilot.claim_one(state, str(tmp_path), expected_material_id=78)
    with pytest.raises(vk_daily_autopilot.DailyPublishBlocked):
        vk_daily_autopilot.preview_material(state, 78, str(tmp_path))


def test_daily_queue_does_not_create_a_second_unresolved_claim(tmp_path):
    first = _record(77, status="publishing", media=_approved_media(tmp_path))
    second = _record(78, media=_approved_media(tmp_path))
    state = _write_queue(tmp_path, [first, second])
    with pytest.raises(vk_daily_autopilot.DailyPublishBlocked):
        vk_daily_autopilot.claim_one(state, str(tmp_path), expected_material_id=78)


def test_daily_queue_rejects_tampered_editorial_text(tmp_path):
    record = _record(media=_approved_media(tmp_path))
    record["vk_text"] = "changed"
    state = _write_queue(tmp_path, [record])
    with pytest.raises(vk_daily_autopilot.DailyQueueError):
        vk_daily_autopilot.queue_diagnostics(state, str(tmp_path))


def test_committed_control_image_is_offline_ready_and_integral(monkeypatch):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    state_path = os.path.join(root, "vk_daily", "queue.json")
    state = json.load(open(state_path, encoding="utf-8"))
    media = state["materials"]["104"]["media"]
    assert media["origin"] == "licensed_file"
    assert media["path"] == "vk_daily/assets/monstera-deliciosa-smatu-cc-by-sa-4.0.jpg"
    assert media["source_image_url"].startswith("https://upload.wikimedia.org/")
    monkeypatch.setattr(vk_daily_autopilot.httpclient, "fetch_bytes",
                        lambda url: (_ for _ in ()).throw(AssertionError("network must not be used")))
    preview = vk_daily_autopilot.preview_material(state_path, 104, root, verify_source=True)
    assert preview["media_location"] == "repository_file"
    assert preview["publication_ready"] is True


def test_daily_queue_blocks_missing_or_tampered_local_image(tmp_path):
    media = _approved_media(tmp_path)
    state = _write_queue(tmp_path, [_record(media=media)])
    os.remove(tmp_path / media["path"])
    assert vk_daily_autopilot.queue_diagnostics(state, str(tmp_path))["media_holds"] == {
        "approved local media file is unavailable": 1}

    media = _approved_media(tmp_path)
    path = tmp_path / media["path"]
    path.write_bytes(b"\xff\xd8\xff" + b"corrupted" * 300)
    tampered = _write_queue(tmp_path, [_record(media=media)])
    assert vk_daily_autopilot.queue_diagnostics(tampered, str(tmp_path))["media_holds"] == {
        "approved local media checksum does not match": 1}


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
    assert "actions/cache/restore@v4" in workflow and "runner.py" not in workflow
    assert "Sync new verified AGRO materials and their image links" in workflow
    assert "--verify-media" in workflow
    assert "photos.getWallUploadServer" not in workflow


def test_manual_image_control_workflow_is_single_post_and_safe_by_default():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    workflow = io.open(os.path.join(root, ".github", "workflows", "vk_image_control_publish.yml"),
                       encoding="utf-8").read()
    assert "workflow_dispatch:" in workflow and "schedule:" not in workflow
    assert "runner.py" not in workflow and "daily_jobs.yml" not in workflow
    assert "VK_ACCESS_TOKEN: ${{ secrets.VK_ACCESS_TOKEN }}" in workflow
    assert "VK_GROUP_ID: ${{ vars.VK_GROUP_ID }}" in workflow
    assert "PUBLISH_ONE_LICENSED_VK_IMAGE" in workflow
    assert "--material-id \"${{ inputs.material_id }}\"" in workflow
    assert "VK_PUBLISH: '1'" in workflow
    assert "photos.getWallUploadServer" not in workflow and "wall.post" not in workflow


def test_photo_access_diagnostic_workflow_is_manual_and_read_only():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    workflow = io.open(os.path.join(root, ".github", "workflows", "vk_photo_access_diagnostic.yml"),
                       encoding="utf-8").read()
    assert "workflow_dispatch:" in workflow and "schedule:" not in workflow
    assert "contents: read" in workflow
    assert "VK_ACCESS_TOKEN: ${{ secrets.VK_ACCESS_TOKEN }}" in workflow
    assert "VK_GROUP_ID: ${{ vars.VK_GROUP_ID }}" in workflow
    assert "access-check" in workflow
    assert "runner.py" not in workflow and "wall.post" not in workflow
    assert "photos.saveWallPhoto" not in workflow and "git push" not in workflow
