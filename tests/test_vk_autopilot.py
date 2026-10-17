# -*- coding: utf-8 -*-
"""VK AGRO integration: API isolation, durable queue and duplicate safety."""
import io
import os

import requests

from case_pipeline import config, storage as storage_mod, vk_autopilot
from case_pipeline.vk_publisher import VkPublisher, VkResult


class Response:
    def __init__(self, body, status=200):
        self.body = body
        self.status_code = status

    def json(self):
        if isinstance(self.body, Exception):
            raise self.body
        return self.body


def _api_ok(value):
    return Response({"response": value})


def _material(st, status="post_ready"):
    mid = st.add("https://example.test/agro/article", "test")
    st.update(mid, status=status, telegram_message_id=77 if status == "published" else None,
              image_url="https://example.test/photo.jpg",
              post_text=("Как сохранить чеснок\n\n"
                         "Короткое вступление из проверенного материала.\n\n"
                         "Перед хранением просушите луковицы: влажные могут испортиться.\n\n"
                         "При хранении выбирайте только сухие и целые луковицы.\n\n"
                         "Вывод: храните только сухие и целые луковицы.\n\n"
                         "Источник: https://example.test/agro/article\n\n#Практика"))
    return mid


def _configure_vk(monkeypatch, publish=True):
    monkeypatch.setattr(config, "VK_PUBLISH", publish, raising=False)
    monkeypatch.setattr(config, "VK_PUBLISH_LIMIT", 1, raising=False)
    monkeypatch.setattr(config, "VK_SOURCE_IMAGES_ALLOWED", False, raising=False)
    monkeypatch.setattr(config, "VK_ACCESS_TOKEN", "vk-test-token", raising=False)
    monkeypatch.setattr(config, "VK_GROUP_ID", "242354758", raising=False)


def test_vk_text_post_uses_wall_post_and_never_logs_token(monkeypatch):
    calls = []

    def fake_post(url, data=None, timeout=None, **kwargs):
        calls.append((url, data, kwargs))
        return _api_ok({"post_id": 321})
    monkeypatch.setattr("case_pipeline.vk_publisher.requests.post", fake_post)

    result = VkPublisher("secret-token", "242354758", sleep=lambda _: None).publish("Текст VK")

    assert result.ok and result.post_id == 321 and result.owner_id == -242354758
    assert calls[0][0].endswith("wall.post")
    assert calls[0][1]["owner_id"] == -242354758
    assert calls[0][1]["from_group"] == 1
    assert calls[0][1]["message"] == "Текст VK"


def test_vk_uploads_photo_then_attaches_it_to_wall_post(monkeypatch):
    calls = []

    def fake_post(url, data=None, files=None, timeout=None, **kwargs):
        calls.append((url, data, files))
        if url.endswith("photos.getWallUploadServer"):
            return _api_ok({"upload_url": "https://upload.example.test/photo"})
        if url == "https://upload.example.test/photo":
            assert files and "photo" in files
            return Response({"server": 1, "photo": "[]", "hash": "h"})
        if url.endswith("photos.saveWallPhoto"):
            return _api_ok([{"id": 55, "owner_id": -242354758, "access_key": "key"}])
        if url.endswith("wall.post"):
            return _api_ok({"post_id": 78})
        raise AssertionError(url)
    monkeypatch.setattr("case_pipeline.vk_publisher.requests.post", fake_post)

    photo = b"\xff\xd8\xff" + b"x" * 2048
    result = VkPublisher("token", "242354758", sleep=lambda _: None).publish("Текст", photo)

    assert result.ok and result.post_id == 78
    wall = next(data for url, data, _ in calls if url.endswith("wall.post"))
    assert wall["attachments"] == "photo-242354758_55_key"


def test_vk_token_and_photo_permission_errors_are_diagnostic(monkeypatch):
    monkeypatch.setattr("case_pipeline.vk_publisher.requests.post",
                        lambda *a, **k: Response({"error": {"error_code": 5,
                                                               "error_msg": "User authorization failed"}}))
    bad = VkPublisher("bad", "242354758", sleep=lambda _: None).check_access()
    assert not bad.ok and bad.error_code == 5 and "authorization" in bad.error
    assert bad.stage == "groups.getById"

    replies = iter([
        _api_ok([{"id": 242354758, "name": "Сад без хлопот"}]),
        Response({"error": {"error_code": 27,
                              "error_msg": "Group authorization failed"}}),
    ])
    monkeypatch.setattr("case_pipeline.vk_publisher.requests.post", lambda *a, **k: next(replies))
    photo_denied = VkPublisher("token", "242354758", sleep=lambda _: None).check_access(True)
    assert not photo_denied.ok and photo_denied.error_code == 27
    assert "user access token" in photo_denied.error
    assert photo_denied.stage == "photos.getWallUploadServer"


def test_vk_retries_rate_limit_but_stops_on_ambiguous_wall_timeout(monkeypatch):
    replies = iter([
        Response({"error": {"error_code": 6, "error_msg": "Too many requests"}}),
        _api_ok({"post_id": 91}),
    ])
    waits = []
    monkeypatch.setattr("case_pipeline.vk_publisher.requests.post", lambda *a, **k: next(replies))
    rate_limited = VkPublisher("token", "242354758", retries=1,
                               sleep=waits.append).publish("Текст")
    assert rate_limited.ok and waits == [1]

    def timeout(*args, **kwargs):
        raise requests.Timeout("network")
    monkeypatch.setattr("case_pipeline.vk_publisher.requests.post", timeout)
    uncertain = VkPublisher("token", "242354758", retries=2, sleep=lambda _: None).publish("Текст")
    assert not uncertain.ok and uncertain.uncertain and uncertain.retryable


def test_vk_queue_is_deduplicated_and_survives_reopen(tmp_path, monkeypatch):
    _configure_vk(monkeypatch)
    db = str(tmp_path / "agro.db")
    st = storage_mod.Storage(db)
    mid = _material(st)
    assert len(vk_autopilot.enqueue_eligible(st)) == 1
    assert vk_autopilot.enqueue_eligible(st) == []
    item = st.vk_by_material(mid)
    assert item["status"] == "pending" and item["material_id"] == mid
    assert st.claim_vk(item["id"])
    st.close()

    restored = storage_mod.Storage(db)
    item = restored.vk_by_material(mid)
    assert item["status"] == "publishing"
    assert restored.pending_vk() == []  # ambiguous item is never auto-retried


def test_vk_autopilot_is_independent_from_telegram_and_enforces_daily_dedup(tmp_path, monkeypatch):
    _configure_vk(monkeypatch)
    st = storage_mod.Storage(str(tmp_path / "agro.db"))
    mid = _material(st, status="published")

    class FakePublisher:
        def __init__(self):
            self.published = []

        def check_access(self, require_photo_upload=False):
            return VkResult(True, data={"group": {"id": 242354758}})

        def publish(self, text, photo_bytes=None, dry_run=False):
            self.published.append((text, photo_bytes))
            return VkResult(True, post_id=501, owner_id=-242354758)

    publisher = FakePublisher()
    summary = vk_autopilot.run(st=st, dry_run=False, publish=True, publisher=publisher)
    assert summary["published"] == 1 and len(publisher.published) == 1
    assert publisher.published[0][1] is None  # missing image rights permits text-only VK post
    assert st.get(mid)["status"] == "published"  # Telegram lifecycle is untouched
    item = st.vk_by_material(mid)
    assert item["status"] == "published" and item["vk_post_id"] == 501

    second = vk_autopilot.run(st=st, dry_run=False, publish=True, publisher=publisher)
    assert second["published"] == 0 and len(publisher.published) == 1


def test_vk_dry_run_checks_all_real_ready_materials_without_queue_mutation(tmp_path, monkeypatch):
    _configure_vk(monkeypatch, publish=False)
    st = storage_mod.Storage(str(tmp_path / "agro.db"))
    good_id = _material(st, status="published")
    bad_id = st.add("https://example.test/agro/no-conclusion", "missing conclusion")
    st.update(bad_id, status="post_ready", post_text=(
        "Сезонная работа\n\nПервый проверенный факт. Второй проверенный факт. "
        "Третий проверенный факт. Четвёртый проверенный факт. Пятый проверенный факт. "
        "Шестой проверенный факт. Седьмой проверенный факт. Восьмой проверенный факт.\n\n"
        "Источник: https://example.test/agro/no-conclusion"))

    report = vk_autopilot.dry_run_all(st)

    assert report["found"] == 2
    assert report["suitable"] == 1
    assert report["rejected"] == 1
    assert report["already_queued"] == 0
    assert report["reason_counts"] == {"VK editor: no verified practical value": 1}
    good = next(item for item in report["items"] if item["material_id"] == good_id)
    assert good["ready"] and good["image_mode"] == "text"
    assert st.get(good_id)["status"] == "published"
    assert st.get(bad_id)["status"] == "post_ready"
    assert st.db.execute("SELECT COUNT(*) FROM vk_publications").fetchone()[0] == 0
    safe_log = vk_autopilot.aggregate_diagnostics(report)
    assert "items" not in safe_log and "source_url" not in str(safe_log)


def test_vk_timeout_keeps_queue_locked_and_dry_run_never_calls_wall(tmp_path, monkeypatch):
    _configure_vk(monkeypatch)
    st = storage_mod.Storage(str(tmp_path / "agro.db"))
    _material(st)

    preview = vk_autopilot.run(st=st, dry_run=True, publish=False)
    assert preview["preview"] and "Вывод:" in preview["preview"]["text"]
    assert st.pending_vk() == []  # dry-run does not mutate durable queue

    class TimeoutPublisher:
        def check_access(self, require_photo_upload=False):
            return VkResult(True)

        def publish(self, *args, **kwargs):
            return VkResult(False, error="network timeout during wall.post", uncertain=True)

    summary = vk_autopilot.run(st=st, dry_run=False, publish=True, publisher=TimeoutPublisher())
    assert summary["uncertain"] == 1
    item = st.pending_vk()  # none because the row stays publishing
    assert item == []
    row = st.db.execute("SELECT status,error FROM vk_publications").fetchone()
    assert row["status"] == "publishing" and "timeout" in row["error"]


def test_vk_read_only_self_check_calls_groups_get_by_id_only(monkeypatch):
    _configure_vk(monkeypatch)
    methods = []

    def fake_post(url, data=None, **kwargs):
        methods.append(url.rsplit("/", 1)[-1])
        return _api_ok([{"id": 242354758, "name": "Сад без хлопот"}])

    monkeypatch.setattr("case_pipeline.vk_publisher.requests.post", fake_post)
    result = vk_autopilot.self_check(VkPublisher("vk-test-token", "242354758", sleep=lambda _: None))

    assert result == {"configured": True, "ok": True, "error_code": None,
                      "http_status": 200, "error_kind": "ok",
                      "response_shape": {"response_present": True, "error_present": False,
                                         "response_type": "list", "expected_response_types": ["dict", "list"],
                                         "expected_group_fields": ["id"], "group_container": "list_first_item",
                                         "direct_id_present": True, "nested_structure_present": False,
                                         "first_item_type": "dict",
                                         "community_id_match": True,
                                         "response_object_fields": [],
                                         "groups_container": {"present": False, "type": None,
                                                              "first_item_type": None,
                                                              "first_item_has_id": None}}}
    assert methods == ["groups.getById"]


def test_vk_self_check_preserves_vk_api_error_code(monkeypatch):
    _configure_vk(monkeypatch)
    monkeypatch.setattr("case_pipeline.vk_publisher.requests.post", lambda *a, **k: Response({
        "error": {"error_code": "5", "error_msg": "User authorization failed"}}))

    result = vk_autopilot.self_check(VkPublisher("vk-test-token", "242354758", sleep=lambda _: None))

    assert result == {"configured": True, "ok": False, "error_kind": "vk_api",
                      "error_code": 5, "http_status": 200,
                      "response_shape": {"response_present": False, "error_present": True,
                                         "response_type": None, "expected_response_types": ["dict", "list"],
                                         "expected_group_fields": ["id"],
                                         "group_container": None, "direct_id_present": False,
                                         "nested_structure_present": None,
                                         "community_id_match": None,
                                         "response_object_fields": [],
                                         "groups_container": {"present": False, "type": None,
                                                              "first_item_type": None,
                                                              "first_item_has_id": None}}}


def test_vk_self_check_classifies_error_payload_without_code(monkeypatch):
    _configure_vk(monkeypatch)
    monkeypatch.setattr("case_pipeline.vk_publisher.requests.post", lambda *a, **k: Response({
        "error": {"error_msg": "Unknown API error"}}))

    result = vk_autopilot.self_check(VkPublisher("vk-test-token", "242354758", sleep=lambda _: None))

    assert result == {"configured": True, "ok": False, "error_kind": "vk_api",
                      "error_code": None, "http_status": 200,
                      "response_shape": {"response_present": False, "error_present": True,
                                         "response_type": None, "expected_response_types": ["dict", "list"],
                                         "expected_group_fields": ["id"],
                                         "group_container": None, "direct_id_present": False,
                                         "nested_structure_present": None,
                                         "community_id_match": None,
                                         "response_object_fields": [],
                                         "groups_container": {"present": False, "type": None,
                                                              "first_item_type": None,
                                                              "first_item_has_id": None}}}


def test_vk_self_check_classifies_http_network_json_and_response_errors(monkeypatch):
    _configure_vk(monkeypatch)
    publisher = VkPublisher("vk-test-token", "242354758", retries=0, sleep=lambda _: None)

    monkeypatch.setattr("case_pipeline.vk_publisher.requests.post", lambda *a, **k: Response({}, status=429))
    assert vk_autopilot.self_check(publisher)["error_kind"] == "http"
    assert vk_autopilot.self_check(publisher)["http_status"] == 429

    def timeout(*args, **kwargs):
        raise requests.Timeout("network")
    monkeypatch.setattr("case_pipeline.vk_publisher.requests.post", timeout)
    assert vk_autopilot.self_check(publisher)["error_kind"] == "network"

    monkeypatch.setattr("case_pipeline.vk_publisher.requests.post",
                        lambda *a, **k: Response(ValueError("invalid JSON")))
    assert vk_autopilot.self_check(publisher)["error_kind"] == "json"

    monkeypatch.setattr("case_pipeline.vk_publisher.requests.post", lambda *a, **k: Response({"bad": "shape"}))
    assert vk_autopilot.self_check(publisher)["error_kind"] == "response"


def test_vk_self_check_accepts_direct_object_response(monkeypatch):
    _configure_vk(monkeypatch)
    publisher = VkPublisher("vk-test-token", "242354758", sleep=lambda _: None)

    monkeypatch.setattr("case_pipeline.vk_publisher.requests.post",
                        lambda *a, **k: _api_ok({"id": 242354758}))
    result = vk_autopilot.self_check(publisher)

    assert result["ok"] and result["http_status"] == 200
    assert result["response_shape"] == {
        "response_present": True, "error_present": False, "response_type": "dict",
        "expected_response_types": ["dict", "list"], "expected_group_fields": ["id"],
        "group_container": "object", "direct_id_present": True,
        "nested_structure_present": False, "first_item_type": None,
        "community_id_match": True,
        "response_object_fields": [{"name": "id", "type": "number"}],
        "groups_container": {"present": False, "type": None,
                             "first_item_type": None, "first_item_has_id": None}}


def test_vk_self_check_rejects_missing_or_mismatched_id_without_guessing_nested_path(monkeypatch):
    _configure_vk(monkeypatch)
    publisher = VkPublisher("vk-test-token", "242354758", sleep=lambda _: None)

    monkeypatch.setattr("case_pipeline.vk_publisher.requests.post",
                        lambda *a, **k: _api_ok({"name": "not logged"}))
    missing_id = vk_autopilot.self_check(publisher)

    assert missing_id["error_kind"] == "access"
    assert missing_id["http_status"] == 200
    assert missing_id["response_shape"]["direct_id_present"] is False
    assert missing_id["response_shape"]["nested_structure_present"] is False
    assert missing_id["response_shape"]["community_id_match"] is None

    monkeypatch.setattr("case_pipeline.vk_publisher.requests.post",
                        lambda *a, **k: _api_ok({"group": {"id": 242354758}}))
    nested_id = vk_autopilot.self_check(publisher)

    assert nested_id["error_kind"] == "access"
    assert nested_id["response_shape"]["direct_id_present"] is False
    assert nested_id["response_shape"]["nested_structure_present"] is True
    assert nested_id["response_shape"]["community_id_match"] is None
    assert nested_id["response_shape"]["response_object_fields"] == [
        {"name": "group", "type": "dict"}]
    assert nested_id["response_shape"]["groups_container"] == {
        "present": False, "type": None, "first_item_type": None,
        "first_item_has_id": None}

    monkeypatch.setattr("case_pipeline.vk_publisher.requests.post",
                        lambda *a, **k: _api_ok([{"id": 1, "name": "not logged"}]))
    wrong_id = vk_autopilot.self_check(publisher)

    assert wrong_id["error_kind"] == "access"
    assert wrong_id["http_status"] == 200
    assert wrong_id["response_shape"]["community_id_match"] is False


def test_vk_self_check_accepts_confirmed_groups_container(monkeypatch):
    _configure_vk(monkeypatch)
    publisher = VkPublisher("vk-test-token", "242354758", sleep=lambda _: None)
    monkeypatch.setattr("case_pipeline.vk_publisher.requests.post", lambda *a, **k: _api_ok({
        "groups": [{"id": 242354758, "name": "not logged"}], "profiles": []}))

    result = vk_autopilot.self_check(publisher)

    assert result["ok"] and result["http_status"] == 200
    assert result["response_shape"]["group_container"] == "object_groups_first_item"
    assert result["response_shape"]["groups_container"] == {
        "present": True, "type": "list", "first_item_type": "dict",
        "first_item_has_id": True}
    assert result["response_shape"]["community_id_match"] is True


def test_vk_self_check_rejects_empty_or_wrong_groups_container_id(monkeypatch):
    _configure_vk(monkeypatch)
    publisher = VkPublisher("vk-test-token", "242354758", sleep=lambda _: None)

    monkeypatch.setattr("case_pipeline.vk_publisher.requests.post",
                        lambda *a, **k: _api_ok({"groups": [], "profiles": []}))
    empty_groups = vk_autopilot.self_check(publisher)

    assert empty_groups["error_kind"] == "access"
    assert empty_groups["response_shape"]["group_container"] == "object_groups_first_item"
    assert empty_groups["response_shape"]["community_id_match"] is None

    monkeypatch.setattr("case_pipeline.vk_publisher.requests.post",
                        lambda *a, **k: _api_ok({"groups": [{"id": 1}], "profiles": []}))
    wrong_group = vk_autopilot.self_check(publisher)

    assert wrong_group["error_kind"] == "access"
    assert wrong_group["http_status"] == 200
    assert wrong_group["response_shape"]["community_id_match"] is False


def test_vk_defaults_are_safe_and_daily_limit_is_one():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    source = io.open(os.path.join(root, "case_pipeline", "config.py"), encoding="utf-8").read()
    assert 'VK_PUBLISH = env("VK_PUBLISH", "0") == "1"' in source
    assert 'VK_PUBLISH_LIMIT = int(env("VK_PUBLISH_LIMIT", "1"))' in source
    assert 'VK_SELF_CHECK = env("VK_SELF_CHECK", "0") == "1"' in source


def test_vk_editor_uses_existing_provider_but_rejects_new_numbers():
    verified = ("Уход за чесноком\n\nПросушите луковицы перед хранением.\n\n"
                "Вывод: храните только сухие луковицы.")

    class Provider:
        available = True

        def complete(self, messages):
            assert messages[0]["content"] == vk_autopilot.VK_EDITOR_SYSTEM
            return ("Уход за чесноком\n\nПросушите луковицы.\n\n"
                    "🌱 Храните их в сухом месте.\n\n"
                    "🌿 Вывод: проверяйте 99 луковиц.")

    post = vk_autopilot.build_vk_post(verified, provider=Provider())
    assert "99" not in post  # небоснованная цифра -> детерминированный fallback
    assert "Вывод: храните только сухие луковицы." in post


def test_vk_fallback_splits_a_long_verified_paragraph_without_inventing():
    verified = ("Романтический сад\n\nПервое проверенное предложение. Второе "
                "проверенное предложение. Третье проверенное предложение. "
                "Четвёртое проверенное предложение. Пятое проверенное предложение.\n\n"
                "Источник: https://example.test/a")
    post = vk_autopilot.build_vk_post(verified)
    blocks = post.split("\n\n")
    assert len(blocks) >= 4
    assert "Первое проверенное предложение." in post
    assert "Вывод:" not in post
    assert "no verified practical value" in vk_autopilot.vk_post_contract_error(post)


def test_vk_uses_a_verbatim_recommendation_when_source_has_no_conclusion():
    verified = ("Подготовка пионов\n\n"
                "В октябре здоровые листья ещё питают корни.\n\n"
                "В октябре достаточно убрать то, что может навредить, и не создать новых проблем.\n\n"
                "При сырой мульче почки могут пострадать.\n\n"
                "Источник: https://example.test/peonies")

    post = vk_autopilot.build_vk_post(verified)

    recommendation = "В октябре достаточно убрать то, что может навредить, и не создать новых проблем."
    assert recommendation in post
    assert post.count(recommendation) == 1
    assert vk_autopilot.vk_post_contract_error(post) == ""


def test_vk_keeps_a_confirmed_source_conclusion():
    verified = ("Хранение чеснока\n\n"
                "Перед хранением луковицы должны полностью просохнуть.\n\n"
                "При высокой влажности чеснок может испортиться.\n\n"
                "Вывод: храните только сухие и целые луковицы.\n\n"
                "Источник: https://example.test/garlic")

    post = vk_autopilot.build_vk_post(verified)

    assert "🌿 Вывод: храните только сухие и целые луковицы." in post
    assert vk_autopilot.vk_post_contract_error(post) == ""


def test_vk_allows_practical_facts_without_creating_a_conclusion():
    verified = ("Земляника осенью\n\n"
                "При первых заморозках почва вокруг земляники остывает медленнее воздуха.\n\n"
                "После листопада почва под мульчей дольше сохраняет влагу.\n\n"
                "Источник: https://example.test/strawberry")

    post = vk_autopilot.build_vk_post(verified)

    assert "🌿 Вывод:" not in post
    assert vk_autopilot.vk_post_contract_error(post) == ""


def test_vk_discards_an_invented_recommendation_from_editor():
    verified = ("Земляника осенью\n\n"
                "При первых заморозках почва вокруг земляники остывает медленнее воздуха.\n\n"
                "После листопада почва под мульчей дольше сохраняет влагу.\n\n"
                "Источник: https://example.test/strawberry")

    class InventingProvider:
        available = True

        def complete(self, _messages):
            return ("Земляника осенью\n\n"
                    "Почва остывает медленнее воздуха.\n\n"
                    "💧 Наливайте 10 литров воды под каждый куст.\n\n"
                    "Источник: https://example.test/strawberry")

    post = vk_autopilot.build_vk_post(verified, provider=InventingProvider())

    assert "10 литров" not in post
    assert vk_autopilot.vk_post_contract_error(post) == ""


def test_vk_rejects_descriptive_material_without_practical_value():
    verified = ("Романтический сад\n\n"
                "Романтизм возник в искусстве в конце восемнадцатого столетия.\n\n"
                "Это направление переплеталось с рококо и сентиментализмом.\n\n"
                "Источник: https://example.test/romantic")

    post = vk_autopilot.build_vk_post(verified)

    assert vk_autopilot.vk_post_contract_error(post) == "VK editor: no verified practical value"


def test_vk_removes_technical_rubric_and_uses_at_most_four_thematic_emojis():
    verified = ("🌦 Погода и сезон Подготовка пионов к зиме\n\n"
                "Осенью секатором легко срезать листья раньше времени.\n\n"
                "При сырой мульче почки могут пострадать.\n\n"
                "В октябре достаточно убрать то, что может навредить.\n\n"
                "Источник: https://example.test/peonies")

    post = vk_autopilot.build_vk_post(verified)
    first_line = post.splitlines()[0]
    emojis = ("🛡️", "✂️", "💧", "🌿", "🌬️", "🍂", "⚠️", "🌱")

    assert first_line.endswith("Подготовка пионов к зиме")
    assert first_line.startswith(("🍂 ", "✂️ "))
    assert "Погода и сезон" not in first_line and "🌦" not in first_line
    assert 2 <= sum(post.count(emoji) for emoji in emojis) <= 4
    assert "🌿 При сырой мульче" in post
    assert "⚠️ В октябре достаточно убрать" in post


def test_vk_keeps_direct_quote_and_attribution_in_one_paragraph():
    verified = ("Опавшая листва\n\n"
                "«Часть сухих листьев можно собрать в мешки и сохранить до следующего сезона. "
                "Весной ими удобно мульчировать овощные грядки», — советует агроном.\n\n"
                "При хранении сухая листва остаётся пригодной для мульчи.\n\n"
                "Источник: https://example.test/leaves")

    post = vk_autopilot.build_vk_post(verified)

    quote = ("«Часть сухих листьев можно собрать в мешки и сохранить до следующего сезона. "
             "Весной ими удобно мульчировать овощные грядки», — советует агроном.")
    assert quote in post
    assert "сезона.\n\nВесной" not in post


def test_vk_queue_records_editorial_rejection_without_touching_telegram(tmp_path, monkeypatch):
    _configure_vk(monkeypatch)
    st = storage_mod.Storage(str(tmp_path / "agro.db"))
    mid = st.add("https://example.test/without-conclusion", "test")
    st.update(mid, status="published", telegram_message_id=88,
              post_text=("Тема\n\nПервый проверенный факт. Второй проверенный факт. "
                         "Третий проверенный факт. Четвёртый проверенный факт.\n\n"
                         "Источник: https://example.test/without-conclusion"))
    assert vk_autopilot.enqueue_eligible(st) == []
    row = st.vk_by_material(mid)
    assert row["status"] == "failed" and row["error"].startswith("VK editor:")
    assert st.get(mid)["status"] == "published" and st.get(mid)["telegram_message_id"] == 88


def test_daily_workflow_maps_vk_secrets_without_changing_schedule():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    workflow = io.open(os.path.join(root, ".github", "workflows", "daily_jobs.yml"),
                       encoding="utf-8").read()
    assert "VK_ACCESS_TOKEN: ${{ secrets.VK_ACCESS_TOKEN }}" in workflow
    assert "VK_GROUP_ID: ${{ vars.VK_GROUP_ID }}" in workflow
    assert "VK_PUBLISH: ${{ vars.VK_PUBLISH }}" in workflow
    assert "VK_SELF_CHECK: ${{ vars.VK_SELF_CHECK }}" in workflow
    assert "path: data" in workflow  # vk_publications is persisted in agro_channel.db
    assert 'cron: "0 6 * * *"' in workflow and 'cron: "0 18 * * *"' in workflow


def test_vk_self_check_workflow_is_manual_and_read_only():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    workflow = io.open(os.path.join(root, ".github", "workflows", "vk_self_check.yml"),
                       encoding="utf-8").read()

    assert "workflow_dispatch:" in workflow
    assert "schedule:" not in workflow
    assert "VK_ACCESS_TOKEN: ${{ secrets.VK_ACCESS_TOKEN }}" in workflow
    assert "VK_GROUP_ID: ${{ vars.VK_GROUP_ID }}" in workflow
    assert 'VK_PUBLISH: "0"' in workflow and 'VK_SELF_CHECK: "1"' in workflow
    assert "vk_autopilot.self_check()" in workflow
    assert "VK self-check: OK" in workflow
    assert 'result["response_shape"]' in workflow
    assert 'result["error"]' not in workflow
    assert "runner.py" not in workflow
    assert "wall.post" not in workflow and "photos.getWallUploadServer" not in workflow
    assert "cache/" not in workflow and "sqlite" not in workflow.lower()
