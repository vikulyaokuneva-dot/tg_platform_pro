# -*- coding: utf-8 -*-
from case_pipeline import pets_approved_previews
from case_pipeline.pets_storage import PetsStorage


def test_owner_approved_preview_is_validated_then_queued_once(tmp_path):
    st = PetsStorage(str(tmp_path / "pets-approved.db"))
    result = pets_approved_previews.queue_first_approved_post(st)
    assert result["status"] == "post_ready"
    row = st.queued_materials()[0]
    assert row["source"] == "approved_factual_preview"
    assert row["queue_status"] == "ready"
    assert "Собака для квартиры" in row["post_text"]
    assert pets_approved_previews.queue_first_approved_post(st)["status"] == "skipped"
