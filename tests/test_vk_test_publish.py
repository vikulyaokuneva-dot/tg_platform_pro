# -*- coding: utf-8 -*-
import io
import json
import os

import pytest

from case_pipeline import storage as storage_mod
from case_pipeline import vk_test_publish
from case_pipeline.vk_publisher import VkResult


def _candidate_db(tmp_path):
    os.makedirs(str(tmp_path), exist_ok=True)
    db_path = str(tmp_path / "agro.db")
    st = storage_mod.Storage(db_path)
    material_id = st.add("https://example.test/agro/source", "control material")
    st.update(material_id, status="post_ready", post_text=(
        "Как сохранить чеснок\n\n"
        "Перед хранением просушите луковицы: влажные могут испортиться.\n\n"
        "Для хранения выбирайте только сухие и целые луковицы.\n\n"
        "Вывод: храните только сухие и целые луковицы.\n\n"
        "Источник: https://example.test/agro/source"))
    st.close()
    return db_path, material_id


def test_vk_control_preview_and_durable_claim_block_duplicates(tmp_path, capsys):
    db_path, material_id = _candidate_db(tmp_path)
    state_path = str(tmp_path / "state.json")

    candidate = vk_test_publish.preview(db_path, state_path, material_id)
    assert candidate["source_url"] == "https://example.test/agro/source"
    assert "Источник: https://example.test/agro/source" in capsys.readouterr().out

    vk_test_publish.claim(db_path, state_path, material_id)
    state = json.load(open(state_path, encoding="utf-8"))
    assert state["materials"][str(material_id)]["status"] == "publishing"
    with pytest.raises(vk_test_publish.TestPublishBlocked):
        vk_test_publish.claim(db_path, state_path, material_id)


def test_vk_control_fails_closed_without_a_restored_verified_material(tmp_path):
    with pytest.raises(vk_test_publish.TestPublishError):
        vk_test_publish.preview(str(tmp_path / "missing.db"), str(tmp_path / "state.json"), 29)


def test_vk_control_publish_records_post_id_and_timeout_stays_blocked(tmp_path):
    db_path, material_id = _candidate_db(tmp_path)
    state_path = str(tmp_path / "state.json")
    vk_test_publish.claim(db_path, state_path, material_id)

    class SuccessPublisher:
        def check_access(self, require_photo_upload=False):
            assert not require_photo_upload
            return VkResult(True)

        def publish(self, text, photo_bytes=None, dry_run=False):
            assert text and photo_bytes is None and not dry_run
            return VkResult(True, post_id=700, owner_id=-242354758)

    vk_test_publish.publish_claimed(db_path, state_path, material_id, publisher=SuccessPublisher())
    state = json.load(open(state_path, encoding="utf-8"))
    record = state["materials"][str(material_id)]
    assert record["status"] == "published" and record["vk_post_id"] == 700

    second_db, second_id = _candidate_db(tmp_path / "timeout")
    second_state = str(tmp_path / "timeout" / "state.json")
    vk_test_publish.claim(second_db, second_state, second_id)

    class TimeoutPublisher:
        def check_access(self, require_photo_upload=False):
            return VkResult(True)

        def publish(self, *args, **kwargs):
            return VkResult(False, error_kind="network", uncertain=True)

    with pytest.raises(vk_test_publish.TestPublishBlocked):
        vk_test_publish.publish_claimed(second_db, second_state, second_id, publisher=TimeoutPublisher())
    state = json.load(open(second_state, encoding="utf-8"))
    assert state["materials"][str(second_id)]["status"] == "publishing"
    assert state["materials"][str(second_id)]["last_error"]["uncertain"] is True


def test_vk_control_workflow_is_manual_confirmed_text_only_and_durable():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    workflow = io.open(os.path.join(root, ".github", "workflows", "vk_test_publish.yml"),
                       encoding="utf-8").read()

    assert "workflow_dispatch:" in workflow and "schedule:" not in workflow
    assert "PUBLISH_ONE_VK_POST" in workflow
    assert "VK_ACCESS_TOKEN: ${{ secrets.VK_ACCESS_TOKEN }}" in workflow
    assert "VK_GROUP_ID: ${{ vars.VK_GROUP_ID }}" in workflow
    assert "actions/cache/restore@v4" in workflow
    assert "git push origin HEAD:main" in workflow
    assert "python runner.py" not in workflow
    assert "photos.getWallUploadServer" not in workflow
    assert "--material-id 29" in workflow
