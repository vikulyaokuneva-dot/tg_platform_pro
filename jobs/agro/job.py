# -*- coding: utf-8 -*-
"""Job: agro — канал «Агро Практика» (второй Telegram-канал платформы).

Линия case_pipeline.agro поверх общего ядра. Реальная публикация только при
AGRO_PUBLISH=1 и DRY_RUN!=1; по умолчанию — безопасный dry-run. Секреты:
AGRO_BOT_TOKEN / AGRO_CHAT_ID (env/secrets, в коде нет). runner.py добавляет
job автоматически (конвенция каталога jobs/<name>/job.py); остальные каналы
не затронуты.
"""
import os

from case_pipeline import agro, config


def run(ctx):
    dry = ctx.dry_run or not config.AGRO_PUBLISH
    ctx.log("agro lane start (dry_run=%s, sources=%s)" % (dry, config.AGRO_SOURCES))
    try:
        summary = agro.run(dry_run=dry,
                           publish=os.getenv("AGRO_PUBLISH", "0") == "1" and not ctx.dry_run)
        ctx.log("agro summary: %s" % summary)
        ctx.storage["last_run"] = summary
        ctx.save()
    except Exception as e:
        ctx.log("agro pipeline error: %s: %s" % (type(e).__name__, e))
        raise
