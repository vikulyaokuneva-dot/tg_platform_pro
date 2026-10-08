# -*- coding: utf-8 -*-
"""Regression: persistence/dedup публикаций МЕЖДУ последовательными запусками.

Цепочка, которую закрепляют тесты:

    RUN1: candidate -> published -> запись в data/*.db (materials + publications)
          -> save-шаг workflow сохраняет data/ в кэш (if: always())
    RUN2: restore того же кэша -> тот же URL
          -> skipped 'already published' ДО fetch и ДО publish
          (никакой повторной отправки в Telegram).

Способы потерять состояние между runs и что их закрывает:
  1) единый actions/cache@v4 объявляет post-if: success() — при падении шага
     запуска снапшот data/ не сохранялся бы и следующий run восстановил бы
     состояние ДО публикации -> раздельный actions/cache/save@v4 c if: always();
  2) restore/save стоят не вокруг запуска пайплайна или смотрят мимо data/
     -> тесты порядка шагов и покрытия путей БД.

Логика дедупа не изменяется: published/post_ready/review/publishing —
терминальные статусы (_known_skip), источник истины — SQLite в data/.
"""
import io
import os
import re

import pytest

from case_pipeline import agro, config, storage as storage_mod, telegram

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DAILY_YML = os.path.join(ROOT, ".github", "workflows", "daily_jobs.yml")
CASE_YML = os.path.join(ROOT, ".github", "workflows", "case_pipeline.yml")
CONFIG_PY = os.path.join(ROOT, "case_pipeline", "config.py")


def _read(path):
    return io.open(path, encoding="utf-8").read()


# ---------- 1. RUN1 published -> RUN2 skipped (после «рестарта» процесса) ----------

def test_run2_skips_url_published_in_run1(tmp_path, monkeypatch):
    """RUN1 публикует -> запись в файле БД; «новый прогон» (новое соединение
    Storage к тому же файлу, как после restore кэша) видит published и
    выходит в skipped ДО fetch и ДО publish."""
    from test_agro_channel import ART_URL, _art_html

    db = str(tmp_path / "agro.db")

    # RUN1: полный путь до mark_published (Telegram подменён фейком)
    monkeypatch.setattr(agro.httpclient, "fetch",
                        lambda url, timeout=30, **kw: (200, _art_html()))
    monkeypatch.setattr(agro.telegram, "publish_post",
                        lambda *a, **k: telegram.PublishResult(True, message_id=777))
    st1 = storage_mod.Storage(db)
    try:
        out1 = agro.process_url(st1, ART_URL, "botanichka",
                                publish=True, dry_run=False)
    finally:
        st1.close()   # конец RUN1: дальше состояние живёт только в файле
    assert out1["status"] == "published", out1
    assert out1["telegram_message_id"] == 777, out1

    # RUN2: тот же URL, но fetch/publish защищены ловушками —
    # дедуп обязан сработать раньше любых side-effect'ов
    def _blocked(*a, **k):
        raise AssertionError("RUN2 must not fetch/publish — already published")
    monkeypatch.setattr(agro.httpclient, "fetch", _blocked)
    monkeypatch.setattr(agro.telegram, "publish_post", _blocked)

    st2 = storage_mod.Storage(db)   # «новый прогон»: свежее соединение
    try:
        out2 = agro.process_url(st2, ART_URL, "botanichka",
                                publish=True, dry_run=False)
        row = st2.get(st2.add(ART_URL, "botanichka"))  # та же canonical_url
        pubs = st2.db.execute(
            "SELECT material_id, telegram_message_id, ok FROM publications").fetchall()
    finally:
        st2.close()

    assert out2["status"] == "skipped", out2
    assert out2["reason"] == "already published", out2
    # журнал публикаций пережил «рестарт»: статус и telegram_message_id на месте
    assert row["status"] == "published" and row["telegram_message_id"] == 777, row
    assert any(p["material_id"] == row["id"] and p["ok"] == 1 for p in pubs), pubs


def test_case_published_hard_dedup_survives_restart(tmp_path):
    """Hard dedup lane 'ai_automation' (_publish_backlog: case_id ->
    никогда повторно) читает publications из того же файла БД: переживает
    рестарт процесса между запусками."""
    db = str(tmp_path / "case.db")
    st1 = storage_mod.Storage(db)
    mid = st1.add("https://x.test/case-42", "src")
    st1.mark_published(mid, 555, "-100CHAT", "case-42")
    st1.close()

    st2 = storage_mod.Storage(db)   # следующий запуск
    try:
        assert st2.case_published("case-42")
        assert "case-42" in st2.published_case_ids()
        assert not st2.case_published("case-never-published")
    finally:
        st2.close()


# ---------- 2. workflow: кэш сохраняется ВСЕГДА и охватывает data/ ----------

def _assert_always_save(path, runner_marker):
    text = _read(path)
    name = os.path.basename(path)

    # отдельный restore/save вместо объединённого actions/cache@v4
    # (у объединённого пост-шаг имеет post-if: success())
    assert "uses: actions/cache@v4" not in text, \
        "%s: объединённый actions/cache@v4 не сохранит data/ при падении job" % name
    assert re.search(r"^\s*uses: actions/cache/restore@v4\s*$", text, re.M), name
    save = re.search(r"- name: Save pipeline DB\n"
                     r"\s+if: always\(\)\n"
                     r"\s+uses: actions/cache/save@v4\n"
                     r"\s+with:\n"
                     r"\s+path: data\n"
                     r"\s+key: case-db-\$\{\{ github\.run_id \}\}", text)
    assert save, \
        "%s: шаг 'Save pipeline DB' обязан быть c if: always(), path: data " \
        "и ключом case-db-${{ github.run_id }}" % name
    restore = re.search(r"- name: Restore pipeline DB\n"
                        r"\s+uses: actions/cache/restore@v4\n"
                        r"\s+with:\n"
                        r"\s+path: data\n"
                        r"\s+key: case-db-\$\{\{ github\.run_id \}\}\n"
                        r"\s+restore-keys: case-db-", text)
    assert restore, "%s: restore-шаг с path: data и префиксом case-db-" % name

    # порядок: restore -> запуск пайплайна -> save (иначе в кэш попадает
    # состояние до публикации, а не после)
    i_restore = text.index("actions/cache/restore@v4")
    i_run = text.index(runner_marker)
    i_save = text.index("actions/cache/save@v4")
    assert i_restore < i_run < i_save, \
        "%s: restore обязан идти до '%s', save — после" % (name, runner_marker)


def test_daily_workflow_restores_then_runs_then_always_saves():
    _assert_always_save(DAILY_YML, "python runner.py")


def test_case_pipeline_workflow_restores_then_runs_then_always_saves():
    _assert_always_save(CASE_YML, "run_case_pipeline.py")


def test_cache_path_covers_default_db_locations():
    """Кэшируется каталог data/, а БД по умолчанию лежат внутри него:
    другой путь по умолчанию (или другой path в workflow) = состояние
    публикаций больше не переживает рестарт."""
    for yml in (DAILY_YML, CASE_YML):
        assert re.search(r"^\s+path: data\s*$", _read(yml), re.M), yml
    src = _read(CONFIG_PY)
    assert 'os.path.join(ROOT, "data", "ai_case_pipeline.db")' in src
    assert 'os.path.join(ROOT, "data", "agro_channel.db")' in src


def test_db_env_overrides_stay_inside_cached_data_dir(monkeypatch):
    """Env-переопределение пути (CASE_DB_PATH/AGRO_DB_PATH) — осознанный
    выход из-под кэша: тест фиксирует, что дефолт (CI-вариант) остаётся
    в data/, пока workflow кэширует именно data/."""
    assert config.DB_PATH.endswith(os.path.join("data", "ai_case_pipeline.db"))
    assert config.AGRO_DB_PATH.endswith(os.path.join("data", "agro_channel.db"))
