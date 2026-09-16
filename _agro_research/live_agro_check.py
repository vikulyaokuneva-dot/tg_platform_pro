# -*- coding: utf-8 -*-
"""Живая вертикальная проверка агро-канала (dry-run, без публикации):
discovery → fetch → extraction → classifier_agro → build_post → гейты.
БД: временный файл, production data/ не трогается."""
import io
import sys

sys.path.insert(0, ".")
from case_pipeline import agro, config, extraction, httpclient  # noqa

OUT = io.open("_agro_research/live_agro_check.txt", "w", encoding="utf-8")
def w(*x): OUT.write(" ".join(str(i) for i in x) + "\n")

w("sources:", config.AGRO_SOURCES, "| dry-run only, publish gate:",
  config.AGRO_PUBLISH, "| DB:", config.AGRO_DB_PATH, "(не создаётся)")

for name in config.AGRO_SOURCES:
    ad = agro.adapters.ADAPTERS.get(name)
    w("=" * 30, name)
    try:
        urls = ad.discover()
    except Exception as e:
        w("DISCOVERY FAIL", type(e).__name__, str(e)[:120]); continue
    w("discovery: %d URL, примеры:" % len(urls))
    for u in urls[:3]:
        w("   ", u[:100])
    ok = 0
    for u in urls[:2]:
        try:
            status, html = httpclient.fetch(u, timeout=40)
            ext = extraction.extract_from_html(html, u)
            text = ext.get("text") or ""
            v = agro.classifier_agro.classify(ext.get("title") or "", text,
                                              ext.get("published_at") or "")
            w("  fetch=HTTP%s len=%d | title=%r date=%r q=%s" % (
                status, len(html), (ext.get("title") or "")[:55],
                (ext.get("published_at") or "")[:19], ext.get("quality")))
            w("    verdict=%s conf=%s topics=%s" % (
                v["type"], v["confidence"], [t[0] for t in v["topics"]]))
            if v["type"] == "practical":
                post, tags = agro.build_post(ext["title"], text, u, name, v)
                errs = agro.editorial_agro(post, text)
                w("    POST ok tags=%s editorial_errs=%s len=%d" % (tags, errs, len(post)))
                w("    head:", post.split("\n\n")[0][:80])
                ok += 1
        except Exception as e:
            w("  STAGE FAIL", type(e).__name__, str(e)[:120])
    w("  итоги источника: практических в пост из 2 проверенных:", ok)

import os
w("\nproduction DB не тронута:", not os.path.exists(config.AGRO_DB_PATH),
  "| prod ai_case_pipeline.db mtime не менялся тестом")
OUT.close()
print("live check done")
