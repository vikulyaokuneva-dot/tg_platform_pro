# -*- coding: utf-8 -*-
"""Regression: lane → Telegram target не должен маскироваться.

Разбор падения 2026-10-06 («400 Bad Request: chat not found», agro lane):
фактический путь цели

    runner.py → jobs/<lane>/job.py → case_pipeline.<lane>.run
      → telegram.publish_post(channel=<lane>)
      → telegram.credentials(<lane>) → config.<LANE>_BOT_TOKEN / _CHAT_ID
      → env ← .github/workflows/*.yml ← GitHub Secrets

ломается на трёх швах, и каждый из них здесь закреплён тестом:
  1) workflow передаёт env с теми же именами, которые читает config
     (рассогласование имени переменной после отката);
  2) lane вызывает publish_post со СВОИМ channel= и не пишет в историю
     чужой chat_id (перепутанные token/target между lane/job);
  3) отклонённый Telegram-таргет остаётся видимой ошибкой, а не
     «успешным» (или молча спрятанным) результатом.

Значения в тестах фиктивные: реальные chat_id/token живут только в
env/secrets, в код и тесты не попадают.
"""
import io
import os
import re

import pytest

from case_pipeline import config, telegram

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DAILY_YML = os.path.join(ROOT, ".github", "workflows", "daily_jobs.yml")
CASE_YML = os.path.join(ROOT, ".github", "workflows", "case_pipeline.yml")
PETS_YML = os.path.join(ROOT, ".github", "workflows", "pets_channel.yml")
CONFIG_PY = os.path.join(ROOT, "case_pipeline", "config.py")


def _read(path):
    return io.open(path, encoding="utf-8").read()


class FakeResp:
    def __init__(self, payload, status=200):
        self._p, self.status_code = payload, status
        self.content = b"{}"

    def json(self):
        return self._p


# ---------- 1. workflow env ↔ config env ----------

@pytest.mark.parametrize("var,secret", [
    ("AGRO_CHAT_ID", "AGRO_CHAT_ID"),
    ("AGRO_BOT_TOKEN", "AI_AUTOMATION_BOT_TOKEN"),
    ("AI_AUTOMATION_CHAT_ID", "AI_AUTOMATION_CHAT_ID"),
    ("AI_AUTOMATION_BOT_TOKEN", "AI_AUTOMATION_BOT_TOKEN"),
])
def test_daily_workflow_env_comes_from_secrets(var, secret):
    """Каждая пара lane'а в обязательном порядке приходит из Secrets;
    переименование переменной/секрета без правки config валит тест,
    а не маскируется пустым значением в рантайме."""
    pat = re.compile(r"^\s*%s\s*:\s*\$\{\{\s*secrets\.%s\s*\}\}\s*$"
                     % (var, re.escape(secret)), re.M)
    assert pat.search(_read(DAILY_YML)), \
        "daily_jobs.yml: env %s должен читаться из secrets.%s" % (var, secret)


def test_daily_workflow_publish_gates_present():
    text = _read(DAILY_YML)
    assert re.search(r'^\s*CASE_PUBLISH\s*:\s*"1"', text, re.M)
    assert re.search(r'^\s*AGRO_PUBLISH\s*:\s*"1"', text, re.M)


def test_case_pipeline_workflow_env_comes_from_secrets():
    text = _read(CASE_YML)
    for var in ("AI_AUTOMATION_BOT_TOKEN", "AI_AUTOMATION_CHAT_ID"):
        assert re.search(r"^\s*%s\s*:\s*\$\{\{\s*secrets\.%s\s*\}\}\s*$"
                         % (var, var), text, re.M), var


def test_pets_workflow_reuses_shared_bot_secret_and_own_chat_secret():
    text = _read(PETS_YML)
    assert re.search(r"^\s*AI_AUTOMATION_BOT_TOKEN\s*:\s*\$\{\{\s*secrets\.AI_AUTOMATION_BOT_TOKEN\s*\}\}\s*$", text, re.M)
    assert re.search(r"^\s*PETS_CHAT_ID\s*:\s*\$\{\{\s*secrets\.PETS_CHAT_ID\s*\}\}\s*$", text, re.M)
    assert "PETS_BOT_TOKEN" not in text


def test_pets_scheduled_publish_requires_both_explicit_owner_flags():
    """Cron stays dry-run unless schedule and PETS publication are both enabled."""
    text = _read(PETS_YML)
    assert "PETS_SCHEDULED_RUN: ${{ github.event_name == 'schedule' && '1' || '0' }}" in text
    assert "vars.PETS_AUTONOMOUS_SCHEDULE_ENABLED == '1'" in text
    assert "vars.PETS_PUBLISH == '1'" in text
    assert "inputs.controlled_publish || (github.event_name == 'schedule'" in text


def test_pets_launcher_keeps_scheduled_run_dry_without_either_flag():
    from jobs.pets.run import resolve_dry_run

    base = {"PETS_SCHEDULED_RUN": "1", "DRY_RUN": "0"}
    assert resolve_dry_run({**base, "PETS_AUTONOMOUS_SCHEDULE_ENABLED": "0", "PETS_PUBLISH": "1"})
    assert resolve_dry_run({**base, "PETS_AUTONOMOUS_SCHEDULE_ENABLED": "1", "PETS_PUBLISH": "0"})


def test_pets_launcher_allows_scheduled_real_mode_only_with_both_flags():
    from jobs.pets.run import resolve_dry_run

    assert resolve_dry_run({
        "PETS_SCHEDULED_RUN": "1",
        "PETS_AUTONOMOUS_SCHEDULE_ENABLED": "1",
        "PETS_PUBLISH": "1",
        "DRY_RUN": "1",
    }) is False


def test_pets_launcher_manual_default_remains_dry_run():
    from jobs.pets.run import resolve_dry_run

    assert resolve_dry_run({"DRY_RUN": "1"}) is True
    assert resolve_dry_run({"DRY_RUN": "0"}) is False


def test_pets_scheduled_replenishment_chain_uses_explicit_gigachat_and_queue_gates():
    """The scheduled source-to-queue path cannot silently use mock or paid AI."""
    workflow = _read(PETS_YML)
    job = _read(os.path.join(ROOT, "jobs", "pets", "job.py"))

    assert "vars.PETS_AUTONOMOUS_REPLENISH_ENABLED == '1'" in workflow
    assert "PETS_EXTERNAL_SOURCES:" in workflow
    assert "PETS_GENERATOR_MODE:" in workflow
    assert "PETS_ALLOW_LIVE_AI:" in workflow
    assert "PETS_ALLOW_PRODUCTION_QUEUE:" in workflow
    assert "PETS_MAX_GIGACHAT_GENERATIONS:" in workflow
    assert "_DailyLimitedGigaChatGenerator" in job
    assert "gigachat_generation_limit_must_be_1" in job
    assert "replenish_verified_queue(" in job


def test_workflows_do_not_hardcode_chat_id():
    """chat_id — только в Secrets/Variables: литерал в workflow = регресс."""
    for path in (DAILY_YML, CASE_YML):
        assert not re.search(r"-100\d{9,}", _read(path)), path


def test_config_reads_exactly_the_documented_env_names():
    src = _read(CONFIG_PY)
    # prod-канал: имя переменной не «съехало» на другое после отката
    assert re.search(r'^CHAT_ID\s*=\s*env\("AI_AUTOMATION_CHAT_ID"',
                     src, re.M), "config.CHAT_ID читает не AI_AUTOMATION_CHAT_ID"
    assert re.search(r'^BOT_TOKEN\s*=\s*env\("AI_AUTOMATION_BOT_TOKEN"\)',
                     src, re.M), "config.BOT_TOKEN читает не AI_AUTOMATION_BOT_TOKEN"
    # agro-канал: та же конвенция <JOB>_* и БЕЗ дефолта — пустой секрет
    # обязан означать «канал выключен», а не тихую отправку в чат AI-канала
    assert re.search(r'^AGRO_BOT_TOKEN\s*=\s*env\("AGRO_BOT_TOKEN"\)\s*$',
                     src, re.M), "AGRO_BOT_TOKEN: неожиданное имя/дефолт"
    assert re.search(r'^AGRO_CHAT_ID\s*=\s*env\("AGRO_CHAT_ID"\)\s*$',
                     src, re.M), "AGRO_CHAT_ID: неожиданное имя/дефолт"


# ---------- 2. lane → channel / chat_id ----------

def test_agro_lane_publishes_through_agro_channel():
    src = _read(os.path.join(ROOT, "case_pipeline", "agro.py"))
    assert re.search(r'publish_post\([^)]*channel\s*=\s*"agro"', src, re.S), \
        "agro lane обязан публиковать через channel='agro'"
    # история агро-канала пишется с его chat_id, не с prod-каналом
    assert "config.AGRO_CHAT_ID" in src
    assert not re.search(r'publish_post\([^)]*chat_id\s*=\s*config\.CHAT_ID', src, re.S)


@pytest.mark.parametrize("module", ["pipeline.py", "news.py"])
def test_ai_lane_never_publishes_into_agro_channel(module):
    src = _read(os.path.join(ROOT, "case_pipeline", module))
    assert 'channel="agro"' not in src, module
    assert "AGRO_BOT_TOKEN" not in src and "AGRO_CHAT_ID" not in src, module


def test_credentials_route_each_lane_to_its_own_pair(monkeypatch):
    monkeypatch.setattr(config, "BOT_TOKEN", "AI-TOKEN", raising=False)
    monkeypatch.setattr(config, "CHAT_ID", "-100AI", raising=False)
    monkeypatch.setattr(config, "AGRO_BOT_TOKEN", "AGRO-TOKEN", raising=False)
    monkeypatch.setattr(config, "AGRO_CHAT_ID", "-100AGRO", raising=False)
    monkeypatch.setattr(config, "PETS_CHAT_ID", "-100PETS", raising=False)
    assert telegram.credentials() == ("AI-TOKEN", "-100AI")
    assert telegram.credentials("ai") == ("AI-TOKEN", "-100AI")
    assert telegram.credentials("agro") == ("AGRO-TOKEN", "-100AGRO")
    assert telegram.credentials("pets") == ("AI-TOKEN", "-100PETS")


def test_publish_post_sends_to_lane_pair(monkeypatch):
    """publish_post(channel) → конкретная пара token/chat в send_message:
    никакого fallback на чужую пару при любом channel."""
    monkeypatch.setattr(config, "BOT_TOKEN", "AI-TOKEN", raising=False)
    monkeypatch.setattr(config, "CHAT_ID", "-100AI", raising=False)
    monkeypatch.setattr(config, "AGRO_BOT_TOKEN", "AGRO-TOKEN", raising=False)
    monkeypatch.setattr(config, "AGRO_CHAT_ID", "-100AGRO", raising=False)
    monkeypatch.setattr(config, "PETS_CHAT_ID", "-100PETS", raising=False)
    sent = {}

    def spy(token, chat_id, text, dry_run=False, parse_mode=None, retries=2):
        sent.update(token=token, chat=chat_id)
        return telegram.PublishResult(True, message_id=11)
    monkeypatch.setattr(telegram, "send_message", spy)

    assert telegram.publish_post("Заголовок\n\nТекст поста", channel="agro").ok
    assert sent == {"token": "AGRO-TOKEN", "chat": "-100AGRO"}, sent

    assert telegram.publish_post("Заголовок\n\nТекст поста", channel="ai").ok
    assert sent == {"token": "AI-TOKEN", "chat": "-100AI"}, sent

    assert telegram.publish_post("Заголовок\n\nТекст поста", channel="pets").ok
    assert sent == {"token": "AI-TOKEN", "chat": "-100PETS"}, sent


# ---------- 3. отклонённый таргет не маскируется ----------

def test_chat_not_found_stays_visible_failure(monkeypatch):
    """Telegram отверг таргет → результат обязан быть ok=False с реальным
    описанием ошибки (не «успешной» публикацией и не проглоченным статусом)."""
    monkeypatch.setattr(config, "AGRO_BOT_TOKEN", "T", raising=False)
    monkeypatch.setattr(config, "AGRO_CHAT_ID", "-100WRONG", raising=False)
    monkeypatch.setattr(telegram.requests, "post",
                        lambda *a, **k: FakeResp(
                            {"ok": False, "description": "chat not found"}, 400))
    res = telegram.publish_post("Заголовок\n\nТекст поста", channel="agro")
    assert res.ok is False
    assert "400" in str(res.error) and "chat not found" in str(res.error)


def test_agro_publish_failure_is_not_counted_as_published(monkeypatch, tmp_path):
    """Провал публикации не должен попадать в published (маскировка ошибки
    таргета счётчиком успеха): материал возвращается в review с реальной
    причиной от Telegram."""
    from case_pipeline import agro as agro_mod, storage as storage_mod
    from test_agro_channel import ART_URL, _art_html

    st = storage_mod.Storage(str(tmp_path / "agro.db"))
    monkeypatch.setattr(config, "AGRO_PUBLISH", True, raising=False)
    monkeypatch.setattr(config, "AGRO_BOT_TOKEN", "T", raising=False)
    monkeypatch.setattr(config, "AGRO_CHAT_ID", "-100WRONG", raising=False)
    monkeypatch.setattr(agro_mod.httpclient, "fetch",
                        lambda url, timeout=30, **kw: (200, _art_html()))
    # image-контракт: байты изображения валидируются ДО отправки
    monkeypatch.setattr(agro_mod.httpclient, "fetch_bytes",
                        lambda url, **kw: b"\xff\xd8" + b"x" * 20000)
    monkeypatch.setattr(agro_mod.telegram, "publish_post",
                        lambda *a, **k: telegram.PublishResult(
                            False, error="400 Bad Request: chat not found"))
    row = agro_mod.process_url(st, ART_URL, "botanichka",
                               publish=True, dry_run=False)
    assert row["status"] != "published", row
    assert "chat not found" in row.get("reason", ""), row
    # в истории публикаций — ни одной строки: ошибка не «залипла» успехом
    rows = st.db.execute("SELECT COUNT(*) c FROM publications").fetchone()
    assert rows["c"] == 0
