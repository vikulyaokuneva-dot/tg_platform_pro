# -*- coding: utf-8 -*-
"""Job: agro — канал «Агро Практика» (второй Telegram-канал платформы).

Линия case_pipeline.agro поверх общего ядра. Реальная публикация только при
AGRO_PUBLISH=1 и DRY_RUN!=1; по умолчанию — безопасный dry-run. Секреты:
AGRO_BOT_TOKEN / AGRO_CHAT_ID (env/secrets, в коде нет). runner.py добавляет
job автоматически (конвенция каталога jobs/<name>/job.py); остальные каналы
не затронуты.
"""
import os

from case_pipeline import ai, agro, config, storage as storage_mod, vk_autopilot


def run(ctx):
    dry = ctx.dry_run or not config.AGRO_PUBLISH
    ctx.log("agro lane start (dry_run=%s, sources=%s)" % (dry, config.AGRO_SOURCES))
    try:
        summary = agro.run(dry_run=dry,
                           publish=os.getenv("AGRO_PUBLISH", "0") == "1" and not ctx.dry_run)
        ctx.log("agro summary: %s" % summary)
        # VK is a separate best-effort destination.  Its queue lives in the
        # same persisted AGRO SQLite file, but it never changes Telegram
        # material/publication statuses and its errors cannot fail this job.
        # This is deliberately a deterministic, read-only diagnostic: it
        # reports all previously approved AGRO material without spending an AI
        # request or leaking post bodies/URLs into Actions logs.
        vk_storage = storage_mod.Storage(config.AGRO_DB_PATH)
        vk_report = vk_autopilot.dry_run_all(vk_storage, provider=ai.NullProvider())
        vk_log = vk_autopilot.aggregate_diagnostics(vk_report)
        ctx.log("vk agro diagnostic: %s" % vk_log)
        vk_info = {"enabled": bool(config.VK_PUBLISH), "diagnostics": vk_log}
        if config.VK_SELF_CHECK:
            vk_info["self_check"] = vk_autopilot.self_check()
            ctx.log("vk self-check: %s" % vk_info["self_check"])

        if config.VK_PUBLISH:
            try:
                vk_summary = vk_autopilot.run(
                    st=vk_storage,
                    dry_run=ctx.dry_run,
                    publish=os.getenv("VK_PUBLISH", "0") == "1" and not ctx.dry_run)
            except Exception as vk_error:
                vk_summary = {"error": "%s: %s" %
                              (type(vk_error).__name__, str(vk_error)[:160])}
            # Do not put an operator preview (post text/URLs) into Actions logs.
            ctx.log("vk agro summary: queued=%s published=%s failed=%s uncertain=%s skipped=%s" %
                    tuple(vk_summary.get(k, 0) for k in
                          ("queued", "published", "failed", "uncertain", "skipped")))
            vk_info.update(vk_summary)
        else:
            vk_info["reason"] = "VK_PUBLISH=0"
        summary["vk"] = vk_info
        ctx.storage["last_run"] = summary
        ctx.save()
    except Exception as e:
        ctx.log("agro pipeline error: %s: %s" % (type(e).__name__, e))
        raise
