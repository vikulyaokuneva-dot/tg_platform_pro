# -*- coding: utf-8 -*-
"""Isolated PETS job. Publishing is disabled unless all explicit gates pass."""
import os

from case_pipeline import config, pets, pets_sources, pets_state


def run(ctx):
    dry = ctx.dry_run or not config.PETS_PUBLISH
    ctx.log("pets lane start (dry_run=%s, sources=%s, mode=%s)" %
            (dry, config.PETS_SOURCES, config.PETS_CONTENT_MODE))
    state = pets_state.inspect(config.PETS_DB_PATH)
    ctx.log("pets state restore status=%s backend=%s" % (state["status"], config.PETS_STATE_BACKEND))
    summary = pets.run(dry_run=dry,
                       publish=os.getenv("PETS_PUBLISH", "0") == "1" and not ctx.dry_run,
                       adapters=pets_sources.adapters_for(config.PETS_SOURCES))
    # Deliberately omit URLs/post bodies/credentials from Actions logs.
    values = tuple(summary.get(k, 0) for k in
                   ("checked", "post_ready", "published", "review", "rejected")) + \
             (summary.get("dry_run"),)
    ctx.log("pets summary: checked=%s ready=%s published=%s review=%s rejected=%s dry_run=%s" % values)
    ctx.storage["last_run"] = summary
    ctx.storage["state_restore"] = state
    ctx.save()
