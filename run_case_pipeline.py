# -*- coding: utf-8 -*-
"""run_case_pipeline.py — entrypoint production-пайплайна канала
«AI Автоматизация | Бизнес».

Примеры:
  python run_case_pipeline.py                     # dry-run: полный цикл без публикации
  python run_case_pipeline.py --publish --limit 1 # production: ≤1 пост за запуск
  python run_case_pipeline.py --sources mindbox,ibm
  python run_case_pipeline.py --test-telegram     # getMe + тестовое сообщение (нужен токен)
  python run_case_pipeline.py --reprocess-review  # прогнать AI-арбитраж над зависшими review
  python run_case_pipeline.py --test-news         # «Новость дня»: сгенерировать, НЕ публиковать
  python run_case_pipeline.py --rebuild-navigation# текст навигации (Telegram/пины не трогает)
"""
import argparse
import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from case_pipeline import (ai, config, navigation, news as news_mod,  # noqa: E402
                           pipeline, storage as storage_mod, telegram)


def cmd_dry_or_publish(args):
    summary = pipeline.run(dry_run=not args.publish, limit=args.limit,
                           sources=args.sources.split(",") if args.sources else None,
                           publish=args.publish)
    print("\n=== RUN SUMMARY ===")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


def cmd_test_telegram(args):
    me = telegram.get_me()
    if not me:
        print("BLOCKED: AI_AUTOMATION_BOT_TOKEN не задан (.env не найден или пусто?)")
        return 2
    if "error" in me:
        print("Telegram getMe FAILED: %s" % me["error"])
        return 1
    print("bot ok: @%s (id=%s)" % (me["username"], me["id"]))
    text = ("🧪 TEST — служебное сообщение платформы (не публикация).\n"
            "Pipeline «AI Автоматизация | Бизнес» подключён: канал доступен для "
            "автопостинга валидированных бизнес-кейсов.")
    res = telegram.publish_post(text, chat_id=args.chat or config.CHAT_ID)
    print("sendMessage: HTTP %s | ok=%s | message_id=%s%s" % (
        res.http_status, res.ok, res.message_id,
        "" if res.ok else " | error=%s" % res.error))
    return 0 if res.ok else 1


def cmd_reprocess_review(args):
    """Повторный прогон review-строки через полный pipeline-механизм
    (re-fetch -> classify -> AI arbitration -> evidence -> post) без публикации."""
    st = storage_mod.Storage()
    rows = st.by_status("review")
    if not rows:
        print("review rows: 0")
        return 0
    prov = ai.get_provider()
    print("review rows: %d | provider: %s (available=%s)" % (len(rows), prov.name, prov.available))
    if not prov.available:
        print("AI-провайдер недоступен (нужен GIGACHAT_API_KEY) — арбитраж невозможен, статусы сохранены")
        return 2
    art = pipeline.RunArtifacts(config.RUNS_DIR)
    for r in rows[: args.max or 3]:
        row = pipeline.process_candidate(st, art, r["url"], r["source"] or "", prov,
                                        publish=False, limit_left=0)
        print("REPROCESS %s -> %s | %s" % (r["url"], row.get("status"), row.get("reason", ""))[:220])
    print("artifacts: %s" % art.dir)
    return 0


def cmd_test_news(args):
    """Сгенерировать одну «Новость дня» из NEWS_SOURCE_URL без публикации."""
    st = storage_mod.Storage()
    prov = ai.get_provider()
    art = pipeline.RunArtifacts(config.RUNS_DIR)
    row = news_mod.process_news(st, art, prov, publish=False)
    if not row:
        print("news: свежих подходящих новостей не найдено (или все источники недоступны)")
        return 1
    print("NEWS ROW:", json.dumps(row, ensure_ascii=False)[:400])
    if row.get("status") == "post_ready":
        m = st.seen_url(row["url"])
        text = st.get(m["id"])["post_text"]
        print("=== ТЕКСТ (не опубликован) ===")
        print(text)
    return 0


def cmd_rebuild_navigation(args):
    st = storage_mod.Storage()
    text = navigation.rebuild(st)
    print("=== НАВИГАЦИЯ (Telegram НЕ трогался; закрепите вручную) ===")
    print(text)
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--publish", action="store_true", help="реальная публикация (иначе dry-run)")
    ap.add_argument("--limit", type=int, default=None, help="макс постов за запуск")
    ap.add_argument("--sources", default=None, help="csv список источников")
    ap.add_argument("--test-telegram", action="store_true")
    ap.add_argument("--chat", default=None, help="override chat id для --test-telegram")
    ap.add_argument("--reprocess-review", action="store_true")
    ap.add_argument("--max", type=int, default=3, help="макс review-строк для --reprocess-review")
    ap.add_argument("--test-news", action="store_true", help="сгенерировать новость без публикации")
    ap.add_argument("--rebuild-navigation", action="store_true",
                    help="сгенерировать текст навигации по истории публикаций")
    ap.add_argument("--status", action="store_true", help="показать счётчики статусов из БД")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if args.test_telegram:
        return cmd_test_telegram(args)
    if args.reprocess_review:
        return cmd_reprocess_review(args)
    if args.test_news:
        return cmd_test_news(args)
    if args.rebuild_navigation:
        return cmd_rebuild_navigation(args)
    if args.status:
        st = storage_mod.Storage()
        rows = st.db.execute("SELECT status, COUNT(*) c FROM materials GROUP BY status").fetchall()
        print(json.dumps({r["status"]: r["c"] for r in rows}, indent=1))
        pubs = st.db.execute("SELECT COUNT(*) c FROM publications WHERE ok=1").fetchone()
        print("published total:", pubs["c"], "| db:", config.DB_PATH)
        print("case-публикаций с прошлой новости: %d/%d (новость на %d-м)" % (
            st.count_cases_since_last_news(), config.NEWS_EVERY, config.NEWS_EVERY))
        return 0
    return cmd_dry_or_publish(args)


if __name__ == "__main__":
    sys.exit(main())
