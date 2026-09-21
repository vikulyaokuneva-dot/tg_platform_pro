# -*- coding: utf-8 -*-
"""Probe-3: gismeteo article; svoefermerstvo /analytics сырые ссылки."""
import io, re
from case_pipeline import httpclient, extraction

OUT = io.open("_agro_research/source_probe3.txt", "w", encoding="utf-8")
def log(*a): OUT.write(" ".join(str(x) for x in a) + "\n")

# 1) gismeteo — настоящая статья
try:
    s, html = httpclient.fetch("https://www.gismeteo.ru/news/animals/pochemu-kot-mnet-lapami-podushku/", timeout=30)
    ext = extraction.extract_from_html(html, "https://www.gismeteo.ru/news/animals/pochemu-kot-mnet-lapami-podushku/")
    log("gismeteo article: http", s, "title=", repr((ext.get("title") or "")[:70]),
        "date=", repr(ext.get("published_at")), "q=", ext.get("quality"), "len=", len(ext.get("text") or ""))
    log("excerpt:", (ext.get("text") or "")[:150].replace("\n", " "))
except Exception as e:
    log("gismeteo fail", type(e).__name__, str(e)[:100])

# 2) svoefermerstvo /analytics/ — ВСЕ href
try:
    s, html = httpclient.fetch("https://svoefermerstvo.ru/analytics/", timeout=30)
    hrefs = re.findall(r'href="([^"]+)"', html)
    internal = sorted(set(h for h in hrefs if "svoefermerstvo" in h or h.startswith("/")))
    log("svoefermerstvo /analytics/ hrefs:", len(hrefs), "unique internal:", len(internal))
    for h in internal[:40]:
        log("  ", h[:120])
    art = sorted(set(h for h in hrefs if re.search(r"/(article|material|post|text|news)/", h)))
    log("  article-like:", art[:10])
    # есть ли в HTML даты/JSON-данные (SSR?)
    log("  date markers:", re.findall(r"\d{2}\.\d{2}\.20\d\d", html)[:5],
        "| iso:", re.findall(r"20\d\d-\d\d-\d\d", html)[:5])
except Exception as e:
    log("svoe fail", type(e).__name__, str(e)[:100])
OUT.close()
print("probe3 done")
