# -*- coding: utf-8 -*-
"""Живой probe 4 агро-источников: RSS, URL-паттерны статей, даты, извлекаемость.
Временный исследовательский скрипт. Пишет UTF-8-отчёт, консоль не трогает."""
import io
import re

from case_pipeline import httpclient, extraction

OUT = io.open("_agro_research/source_probe.txt", "w", encoding="utf-8")
def log(*a):
    OUT.write(" ".join(str(x) for x in a) + "\n")

CANDIDATES = {
    "botanichka": ["https://botanichka.ru/", "https://botanichka.ru/feed/",
                   "https://botanichka.ru/category/sad-i-ogorod"],
    "svoe_fermerstvo": ["https://svoefermerstvo.ru/", "https://agroexpedition.ru/",
                        "https://svoefermerstvo.ru/feed/"],
    "gismeteo": ["https://www.gismeteo.ru/news/", "https://www.gismeteo.ru/"],
    "agroinvestor": ["https://www.agroinvestor.ru/", "https://www.agroinvestor.ru/news/",
                     "https://www.agroinvestor.ru/rss/"],
}

for src, urls in CANDIDATES.items():
    log("=" * 25, src)
    for u in urls:
        try:
            status, html = httpclient.fetch(u, timeout=30)
        except Exception as e:
            log("FETCH FAIL", u, type(e).__name__, str(e)[:90])
            continue
        log("OK %s  http=%s len=%d" % (u, status, len(html)))
        # RSS-ссылки на странице
        for m in re.finditer(r'<link[^>]+type="application/rss\+xml"[^>]*>', html)[:3] if False else \
                list(re.finditer(r'<link[^>]+type="application/rss\+xml"[^>]*>', html))[:3]:
            log("  RSS tag:", m.group(0)[:160])
        if u.endswith((".xml", "/feed/", "/feed", "/rss/")) or "<rss" in html[:500].lower() or "<feed" in html[:500].lower():
            items = re.findall(r"<link>([^<]+)</link>|<loc>([^<]+)</loc>", html)
            links = [a or b for a, b in items][:8]
            log("  RSS items:", len(links))
            for l in links:
                log("    ", l[:110])
            dates = re.findall(r"<pubDate>([^<]+)</pubDate>", html)[:3]
            log("  pubDates:", dates)
        else:
            # паттерны внутренних ссылок-кандидатов на статьи
            hrefs = re.findall(r'href="(/[a-z0-9\-/]{4,80})"', html)
            from collections import Counter
            pref = Counter(h.split("/")[1] for h in hrefs if not h.startswith("//"))
            log("  top path sections:", pref.most_common(12))
            art = [h for h in hrefs if re.search(r"/(\d{4}[-/]|article|news|material|blog|analytics|text)", h)][:6]
            log("  article-like:", art)
    OUT.flush()

# извлечение одной статьи с каждого (если найдём url)
log("=" * 25, "extraction probes")
for u in ["https://www.gismeteo.ru/news/", "https://botanichka.ru/"]:
    try:
        status, html = httpclient.fetch(u, timeout=30)
        m = re.findall(r'href="(https?://[^"]+)"', html)
        cands = [x for x in m if ("botanichka.ru/" in x and re.search(r"/\d{4}/|/article/", x))
                 or ("gismeteo.ru/news/" in x and re.search(r"/\d", x))]
        log(u, "-> article candidates:", len(cands), cands[:4])
        if cands:
            s2, art_html = httpclient.fetch(cands[0], timeout=30)
            ext = extraction.extract(art_html, url=cands[0])
            log("  ARTICLE", cands[0][:90])
            log("  title=%r date=%r quality=%s len=%d" % (
                (ext.get("title") or "")[:60], ext.get("published_at"),
                ext.get("quality"), len(ext.get("text") or "")))
            log("  excerpt:", (ext.get("text") or "")[:200].replace("\n", " "))
    except Exception as e:
        log("probe fail", u, type(e).__name__, str(e)[:100])
OUT.close()
print("probe done")
