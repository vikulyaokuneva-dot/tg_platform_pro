# -*- coding: utf-8 -*-
"""Isolated PETS job. Publishing is disabled unless all explicit gates pass."""
import os
from pathlib import Path

from case_pipeline import config, httpclient, pets, pets_briefs, pets_durable_state, pets_sources, pets_state
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
    migrated_demos = st.migrate_demo_materials()

    def checkpoint(phase):
        if backend is None:
            return
        backend.checkpoint(config.PETS_DB_PATH, phase)

    summary = pets.run(dry_run=dry,
                       publish=os.getenv("PETS_PUBLISH", "0") == "1" and not dry,
                       st=st, adapters=pets_sources.adapters_for(config.PETS_SOURCES),
                       checkpoint=checkpoint if backend and not state_error else None,
                       briefs=pets_briefs.DEFAULT_BRIEFS if config.PETS_DEMO_BRIEFS else ())
    summary["migrated_demo_materials"] = migrated_demos
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
    image_checks = _download_preview_images(st, include_demo=config.PETS_DEMO_BRIEFS)
    _write_preview(st, include_demo=config.PETS_DEMO_BRIEFS)
    summary["artifact_images"] = {str(mid): status for mid, status in image_checks}
    ctx.storage["last_run"] = summary
    ctx.storage["state_restore"] = state
    ctx.save()
