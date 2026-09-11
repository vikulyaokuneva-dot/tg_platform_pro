# -*- coding: utf-8 -*-
"""Job: ai_automation — канал «AI Автоматизация | Бизнес».

Реальный пайплайн вместо прежней заглушки «автопост-текст». Пубикация только
при CASE_PUBLISH=1 (и DRY_RUN!=1); по умолчанию — безопасный dry-run с
артефактами в runs/. Остальные 9 каналов и runner.py не затронуты.
"""
import os

from case_pipeline import config, pipeline


def run(ctx):
    ctx.log("ai_automation pipeline start (dry_run=%s)" % ctx.dry_run)
    try:
        summary = pipeline.run(
            dry_run=ctx.dry_run or os.getenv("CASE_PUBLISH", "0") != "1",
            limit=int(os.getenv("CASE_PUBLISH_LIMIT", "1")),
            publish=os.getenv("CASE_PUBLISH", "0") == "1" and not ctx.dry_run,
            log_to_console=False,
        )
        ctx.log("pipeline summary: %s" % summary)
        ctx.storage["last_run"] = summary
        ctx.save()
    except Exception as e:
        ctx.log("pipeline error: %s: %s" % (type(e).__name__, e))
        raise
