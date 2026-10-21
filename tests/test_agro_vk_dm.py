# -*- coding: utf-8 -*-
"""Offline tests for AGRO's owner-only VK draft delivery."""
from case_pipeline import agro_vk_dm, config, storage as storage_mod, telegram


POST = """🌱 Как подготовить чеснок к зиме

Сажайте зубчики за 35-45 дней до устойчивых заморозков: они должны укорениться, но не тронуться в рост.

На тяжёлом грунте глубина заделки 10-12 см, а после посадки грядку мульчируют слоем 5 см.

🌿 Вывод: ориентируйтесь на прогноз и температуру почвы, чтобы чеснок не вымерз.

Источник: https://example.test/agro/chesnok

#Практика #Огород #Ботаничка"""


def _storage(tmp_path):
    st = storage_mod.Storage(str(tmp_path / "agro.db"))
    mid = st.add("https://example.test/agro/chesnok", "test")
    st.update(mid, status="published", post_text=POST)
    return st, mid


def _enable(monkeypatch, rights=False):
    monkeypatch.setattr(config, "AGRO_VK_DM_ENABLED", True, raising=False)
    monkeypatch.setattr(config, "AGRO_VK_DM_CHAT_ID", "123456", raising=False)
    monkeypatch.setattr(config, "AGRO_BOT_TOKEN", "agro-test-token", raising=False)
    monkeypatch.setattr(config, "VK_SOURCE_IMAGES_ALLOWED", rights, raising=False)


def test_disabled_mode_has_no_delivery_side_effect(tmp_path, monkeypatch):
    st, mid = _storage(tmp_path)
    monkeypatch.setattr(config, "AGRO_VK_DM_ENABLED", False, raising=False)
    monkeypatch.setattr(telegram, "send_message", lambda *a, **k: (_ for _ in ()).throw(AssertionError("DM")))

    assert agro_vk_dm.deliver_after_agro_publication(st, mid, POST, photo=b"img") == {"status": "disabled"}
    assert st.agro_vk_dm_delivery(mid) is None


def test_owner_receives_existing_photo_and_clean_vk_copy(tmp_path, monkeypatch):
    st, mid = _storage(tmp_path)
    _enable(monkeypatch, rights=False)
    seen = {"messages": [], "photos": []}

    def send_message(token, chat_id, text, **kwargs):
        seen["messages"].append((token, chat_id, text))
        return telegram.PublishResult(True, message_id=11 + len(seen["messages"]))

    def send_photo(token, chat_id, photo_bytes=None, caption=None, **kwargs):
        seen["photos"].append((token, chat_id, photo_bytes, caption))
        return telegram.PublishResult(True, message_id=99)

    monkeypatch.setattr(telegram, "send_message", send_message)
    monkeypatch.setattr(telegram, "send_photo", send_photo)

    result = agro_vk_dm.deliver_after_agro_publication(st, mid, POST, photo=b"already-fetched-photo")

    assert result == {"status": "sent", "message_id": 99, "image": True}
    assert seen["photos"] == [("agro-test-token", "123456", b"already-fetched-photo", seen["photos"][0][3])]
    assert "права на повторную публикацию" in seen["messages"][0][2].lower()
    assert "Источник: https://example.test/agro/chesnok" in seen["photos"][0][3]
    assert "Техническая заметка" not in seen["photos"][0][3]
    assert st.agro_vk_dm_delivery(mid)["status"] == "sent"


def test_no_image_sends_notice_and_copy_as_separate_messages(tmp_path, monkeypatch):
    st, mid = _storage(tmp_path)
    _enable(monkeypatch, rights=True)
    messages = []
    monkeypatch.setattr(telegram, "send_message", lambda token, chat_id, text, **kw: (
        messages.append(text), telegram.PublishResult(True, message_id=len(messages)))[1])
    monkeypatch.setattr(telegram, "send_photo", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no image")))

    result = agro_vk_dm.deliver_after_agro_publication(st, mid, POST, photo=None)

    assert result["status"] == "sent" and result["image"] is False
    assert "Фото в текущей AGRO-публикации недоступно" in messages[0]
    assert "Источник: https://example.test/agro/chesnok" in messages[1]


def test_long_copy_uses_photo_then_separate_text(tmp_path, monkeypatch):
    st, mid = _storage(tmp_path)
    _enable(monkeypatch)
    long_copy = "Заголовок\n\n" + ("Полезный абзац. " * 100) + "\n\nИсточник: https://example.test/source"
    monkeypatch.setattr(agro_vk_dm.vk_autopilot, "build_vk_post", lambda *a, **k: long_copy)
    monkeypatch.setattr(agro_vk_dm.vk_autopilot, "vk_post_contract_error", lambda text: "")
    photos, messages = [], []
    monkeypatch.setattr(telegram, "send_photo", lambda *a, **kw: (photos.append(kw), telegram.PublishResult(True, message_id=7))[1])
    monkeypatch.setattr(telegram, "send_message", lambda *a, **kw: (messages.append(a[2]), telegram.PublishResult(True, message_id=8))[1])

    result = agro_vk_dm.deliver_after_agro_publication(st, mid, POST, photo=b"bytes")

    assert result["status"] == "sent"
    assert photos[0]["caption"] is None
    assert long_copy in messages


def test_api_error_is_terminal_and_never_auto_retried(tmp_path, monkeypatch):
    st, mid = _storage(tmp_path)
    _enable(monkeypatch)
    calls = []
    monkeypatch.setattr(telegram, "send_message", lambda *a, **kw: (
        calls.append(a), telegram.PublishResult(False, error="400 chat not found"))[1])

    first = agro_vk_dm.deliver_after_agro_publication(st, mid, POST, photo=b"bytes")
    # The regular job may restart between runs; dedup must come from SQLite,
    # not the current Python process.
    st.close()
    restarted = storage_mod.Storage(str(tmp_path / "agro.db"))
    second = agro_vk_dm.deliver_after_agro_publication(restarted, mid, POST, photo=b"bytes")

    assert first["status"] == "failed"
    assert second["status"] == "duplicate"
    assert len(calls) == 1
    assert restarted.agro_vk_dm_delivery(mid)["status"] == "failed"
