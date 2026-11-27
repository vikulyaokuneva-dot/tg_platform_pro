from types import SimpleNamespace

from experiments import structured_editor as editor


def test_dry_run_uses_only_preverified_brief_and_never_calls_network():
    payload = editor.dry_run_preview(editor.resolve_brief("agro"), "Подготовка плодовых деревьев к зиме")
    assert payload["gigachat_calls"] == 0
    assert payload["telegram_sent"] is False
    assert payload["production_sqlite_written"] is False
    assert payload["topic_resolution"] == "preverified_brief_only"
    assert "title" in payload["structured_schema"]["properties"]


def test_unknown_owner_topic_is_not_silently_improvised():
    try:
        editor.resolve_brief("pets", "Как выбрать корм")
    except ValueError as error:
        assert "предварительно проверенная" in str(error)
    else:
        raise AssertionError("arbitrary topic must require an actual source-search implementation")


def test_structured_output_rejects_unknown_source_id():
    brief = editor.resolve_brief("pets")
    draft = editor.StructuredDraft(
        title="Спокойная прогулка начинается с коротких шагов",
        body="Начните с короткого спокойного отрезка. Когда поводок снова свободен, отметьте это поощрением и продолжите путь. Затем спокойно дайте собаке безопасную паузу на обнюхивание.",
        category="pet_care",
        source_ids=["not_a_source"],
        image_search_query="спокойная прогулка с собакой на поводке",
        editorial_notes="Нужна обычная ручная проверка фактов.",
    )
    assert "unknown_source_ids:not_a_source" in editor.validate_structured_draft(draft, brief)


def test_native_structured_result_is_parsed_and_validated_with_fake_sdk_call():
    brief = editor.resolve_brief("ai_automation")

    def fake_call(prompt):
        assert "JSON Schema" in prompt
        return SimpleNamespace(usage=SimpleNamespace(total_tokens=123, prompt_tokens=80, completion_tokens=43)), editor.StructuredDraft(
            title="ИИ для обращений: сначала ограничьте роль помощника",
            body="Сначала определите обращения, которые система может классифицировать и передать человеку. Затем зафиксируйте путь эскалации и собирайте обратную связь об ошибках.",
            category="ai_automation",
            source_ids=["ai_nist_rmf_core", "ai_nist_gai_profile"],
            image_search_query="сотрудник проверяет очередь клиентских обращений",
            editorial_notes="Не обещать измеримый эффект без собственных метрик.",
        )

    result = editor.call_structured_editor(brief, 1, structured_call=fake_call)
    assert result.status == "passed"
    assert result.native_structured_output is True
    assert result.usage["total_tokens"] == 123


def test_current_editor_result_records_mechanical_fact_gate():
    brief = editor.resolve_brief("pets")

    class FakeProvider:
        last_usage = {"total_tokens": 55}

        def complete(self, _messages):
            return "Спокойная прогулка без рывков\n\nНачните с коротких спокойных отрезков и отмечайте свободный поводок. Дайте собаке безопасную паузу на обнюхивание, когда она идёт спокойно."

    result = editor.call_current_editor(brief, 1, FakeProvider())
    assert result.status == "passed"
    assert result.native_structured_output is False
    assert result.usage["total_tokens"] == 55


def test_unsupported_harvest_promise_is_sent_to_review():
    brief = editor.resolve_brief("agro")
    errors = editor.validate_reader_post(
        "Осенний уход за плодовым садом",
        "Проверьте почву и защитите молодой ствол. Деревья отблагодарят вас щедрым урожаем весной.",
        brief,
    )
    assert "unsupported_promise_or_medical_claim" in errors
