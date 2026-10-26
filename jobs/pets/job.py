# -*- coding: utf-8 -*-
"""Isolated PETS job. Publishing is disabled unless all explicit gates pass."""
import os
import json
from pathlib import Path

from case_pipeline import ai, config, httpclient, pets, pets_briefs, pets_durable_state, pets_sources, pets_state, telegram
from case_pipeline.pets_candidates import candidate_adapters_for, collect_source_candidates
from case_pipeline.pets_generator import GigaChatPetsGenerator, MockPetsGenerator
from case_pipeline.pets_storage import PetsStorage


def _write_preview(st, path="runs/pets_preview.md", include_demo=False):
    """Owner-only Action artifact: ready drafts never go to CI logs."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    status_clause = "IN ('post_ready','demo_ready')" if include_demo else "='post_ready'"
    rows = st.db.execute(
        "SELECT m.id,m.post_text,m.canonical_url,m.image_url,r.author,r.license,r.license_url,"
        "r.attribution,r.topic_match FROM materials m "
        "LEFT JOIN pets_image_rights r ON r.material_id=m.id "
        "WHERE m.status %s ORDER BY m.id DESC LIMIT 10" % status_clause).fetchall()
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("# PETS — черновики dry-run\n\n")
        if not rows:
            fh.write("Нет материалов со статусом `post_ready`.\n")
            return
        for row in rows:
            fh.write("## Материал %s\n\n%s\n\n" % (row["id"], row["post_text"] or ""))
            fh.write("Источник: %s\n\n" % (row["canonical_url"] or ""))
            fh.write("Изображение: %s\n" % (row["image_url"] or ""))
            fh.write("Лицензия: %s — %s\n" % (row["license"] or "", row["license_url"] or ""))
            fh.write("Атрибуция: %s\n" % (row["attribution"] or row["author"] or ""))
            fh.write("Проверка соответствия: %s\n\n" % (row["topic_match"] or ""))


def _write_json(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(value, fh, ensure_ascii=False, indent=2, sort_keys=True)


def _license_report(st):
    rows = st.db.execute(
        "SELECT m.id,m.status,r.image_url,r.license,r.license_url,r.author FROM materials m "
        "LEFT JOIN pets_image_rights r ON r.material_id=m.id ORDER BY m.id DESC LIMIT 50").fetchall()
    return [{"material_id": row["id"], "status": row["status"], "image_url": row["image_url"],
             "license": row["license"], "license_url": row["license_url"], "author": row["author"]}
            for row in rows]


def _download_preview_images(st, media_dir="runs/pets_media", include_demo=False):
    """Attach only pre-validated Commons assets; never place them in CI logs."""
    Path(media_dir).mkdir(parents=True, exist_ok=True)
    status_clause = "IN ('post_ready','demo_ready')" if include_demo else "='post_ready'"
    rows = st.db.execute(
        "SELECT m.id,m.image_url FROM materials m "
        "JOIN pets_image_rights r ON r.material_id=m.id "
        "WHERE m.status %s ORDER BY m.id DESC LIMIT 10" % status_clause).fetchall()
    checks = []
    for row in rows:
        url = row["image_url"] or ""
        if not url.startswith("https://upload.wikimedia.org/"):
            checks.append((row["id"], "not_attached: unapproved_host"))
            continue
        try:
            target = Path(media_dir) / ("pets_%s.jpg" % row["id"])
            target.write_bytes(httpclient.fetch_bytes(url))
            checks.append((row["id"], "attached"))
        except Exception:
            checks.append((row["id"], "not_attached: download_failed"))
    return checks


def run(ctx):
    backend = None
    state_error = ""
    restored = None
    if config.PETS_STATE_BACKEND == "github":
        backend = pets_durable_state.from_config(config)
        try:
            restored = backend.restore(config.PETS_DB_PATH)
        except pets_durable_state.DurableStateError as exc:
            state_error = str(exc)
    preflight = None
    if config.PETS_TELEGRAM_PREFLIGHT or config.PETS_PREFLIGHT_ONLY:
        preflight = telegram.pets_channel_preflight()
        if not preflight.get("ok"):
            state_error = state_error or "telegram preflight failed: %s" % preflight.get("reason", "unknown")
    if config.PETS_PREFLIGHT_ONLY:
        ctx.log("pets preflight completed (ok=%s)" % bool(preflight and preflight.get("ok")))
        _write_json(os.path.join(config.RUNS_DIR, "pets_diagnostics.json"),
                    {"preflight": preflight, "state_restore": restored, "state_error": state_error})
        ctx.storage["pets_preflight"] = preflight
        ctx.storage["state_restore"] = restored
        ctx.save()
        return
    # A requested real run fail-closes to dry-run when durable state cannot be
    # restored. No Telegram request occurs in that state.
    dry = ctx.dry_run or not config.PETS_PUBLISH or bool(state_error) or \
        config.PETS_STATE_BACKEND != "github"
    ctx.log("pets lane start (dry_run=%s, sources=%s, mode=%s)" %
            (dry, config.PETS_SOURCES, config.PETS_CONTENT_MODE))
    state = restored or pets_state.inspect(config.PETS_DB_PATH)
    ctx.log("pets state restore status=%s backend=%s" % (state["status"], config.PETS_STATE_BACKEND))
    if state_error:
        ctx.log("pets durable state unavailable; real publication blocked")
    st = PetsStorage(config.PETS_DB_PATH)
    allowed_evergreen_urls = tuple("draft://pets/%s" % brief["id"]
                                   for brief in pets_briefs.EVERGREEN_BRIEFS)
    migrated_demos = st.migrate_demo_materials(allowed_evergreen_urls)

    def checkpoint(phase):
        if backend is None:
            return
        backend.checkpoint(config.PETS_DB_PATH, phase)

    summary = pets.run(dry_run=dry,
                       publish=os.getenv("PETS_PUBLISH", "0") == "1" and not dry,
                       st=st, adapters=pets_sources.adapters_for(config.PETS_SOURCES),
                       checkpoint=checkpoint if backend and not state_error else None,
                       briefs=pets_briefs.DEFAULT_BRIEFS if config.PETS_DEMO_BRIEFS else (),
                       evergreen_briefs=pets_briefs.EVERGREEN_BRIEFS if config.PETS_EVERGREEN_QUEUE else ())
    if config.PETS_EXTERNAL_SOURCES:
        if config.PETS_GENERATOR_MODE == "gigachat":
            cap = config.PETS_MAX_GIGACHAT_GENERATIONS
            if not (1 <= cap <= 10):
                autonomous = {"enabled": False, "dry_run": True, "published": 0,
                              "reason": "gigachat_generation_limit_must_be_1_to_10"}
                summary["autonomous"] = autonomous
                cap = 0
            else:
                generator = GigaChatPetsGenerator(ai.get_provider(), enabled=config.PETS_ALLOW_LIVE_AI and config.PETS_AI_ENABLED)
                candidate_limit = cap
                adapters = candidate_adapters_for(config.PETS_CANDIDATE_SOURCES)
                candidate_store = st if config.PETS_ALLOW_PRODUCTION_QUEUE else PetsStorage(config.PETS_CANDIDATES_DB_PATH)
                candidates, source_report, collection = collect_source_candidates(adapters, storage=candidate_store,
                                                                                   limit=max(candidate_limit * 2, 10))
                if config.PETS_ALLOW_PRODUCTION_QUEUE:
                    autonomous = pets.replenish_verified_queue(
                        st, candidates, generator=generator, target_ready=config.PETS_QUEUE_TARGET,
                        replenish_below=config.PETS_QUEUE_REPLENISH_BELOW)
                else:
                    autonomous = {"queue_before": st.queued_count(), "queue_after": st.queued_count(),
                                  "checked": 0, "post_ready": 0, "review": 0, "rejected": 0, "skipped": 0,
                                  "blocked": "production_queue_opt_in_required"}
                autonomous.update(source_report=source_report, collection=collection,
                                  generator_mode="gigachat", enabled=True, dry_run=dry, published=0)
        else:
            generator = MockPetsGenerator()
            adapters = candidate_adapters_for(config.PETS_CANDIDATE_SOURCES)
            candidate_store = st if config.PETS_ALLOW_PRODUCTION_QUEUE else PetsStorage(config.PETS_CANDIDATES_DB_PATH)
            candidates, source_report, collection = collect_source_candidates(adapters, storage=candidate_store, limit=10)
            if config.PETS_ALLOW_PRODUCTION_QUEUE:
                autonomous = pets.replenish_verified_queue(
                    st, candidates, generator=generator, target_ready=config.PETS_QUEUE_TARGET,
                    replenish_below=config.PETS_QUEUE_REPLENISH_BELOW)
            else:
                autonomous = {"queue_before": st.queued_count(), "queue_after": st.queued_count(),
                              "checked": 0, "post_ready": 0, "review": 0, "rejected": 0, "skipped": 0,
                              "blocked": "production_queue_opt_in_required"}
            autonomous.update(source_report=source_report, collection=collection,
                              generator_mode="mock", enabled=True, dry_run=True, published=0)
    else:
        autonomous = {"enabled": False, "dry_run": True, "published": 0,
                      "source_report": {source: {"status": "disabled_pending_owner_opt_in"}
                                        for source in config.PETS_OFFICIAL_SOURCES}}
    summary["autonomous"] = autonomous
    summary["migrated_unapproved_curated_materials"] = migrated_demos
    if backend and not state_error:
        try:
            checkpoint("dry-run" if dry else "completed")
        except pets_durable_state.DurableStateError:
            summary["state_error"] = "durable checkpoint failed"
            if not dry:
                raise
    # Deliberately omit URLs/post bodies/credentials from Actions logs.
    values = tuple(summary.get(k, 0) for k in
                   ("checked", "post_ready", "published", "review", "rejected")) + \
             (summary.get("dry_run"),)
    ctx.log("pets summary: checked=%s ready=%s published=%s review=%s rejected=%s dry_run=%s" % values)
    preview_path = os.path.join(config.RUNS_DIR, "pets_preview.md")
    media_path = os.path.join(config.RUNS_DIR, "pets_media")
    diagnostics_path = os.path.join(config.RUNS_DIR, "pets_diagnostics.json")
    sources_path = os.path.join(config.RUNS_DIR, "pets_sources_report.json")
    licenses_path = os.path.join(config.RUNS_DIR, "pets_license_report.json")
    image_checks = _download_preview_images(st, media_dir=media_path, include_demo=config.PETS_DEMO_BRIEFS)
    _write_preview(st, path=preview_path, include_demo=config.PETS_DEMO_BRIEFS)
    summary["artifact_images"] = {str(mid): status for mid, status in image_checks}
    _write_json(diagnostics_path, {"summary": summary, "state_restore": state, "preflight": preflight,
                                   "demo_enabled": config.PETS_DEMO_BRIEFS,
                                   "external_sources_enabled": config.PETS_EXTERNAL_SOURCES})
    _write_json(sources_path, autonomous.get("source_report", {}))
    _write_json(licenses_path, _license_report(st))
    ctx.storage["last_run"] = summary
    ctx.storage["state_restore"] = state
    ctx.save()
