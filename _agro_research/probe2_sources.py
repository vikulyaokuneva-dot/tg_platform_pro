# -*- coding: utf-8 -*-
"""Probe-2: реальные паттерны статей gismeteo/svoe_fermerstvo + полные проверки
botanichka/agroinvestor через RSS и extraction.extract_from_html. Временный."""
import io
import re

from case_pipeline import httpclient, extraction

OUT = io.open("_agro_research/source_probe2.txt", "w", encoding="utf-8")
def log(*a):
    OUT.write(" ".join(str(x) for x in a) + "\n")

def probe_article(url):
    try:
        s, html = httpclient.fetch(url, timeout=30)
        ext = extraction.extract_from_html(html, url)
        log("  ARTICLE", url[:100])
        log("    http=%s title=%r date=%r quality=%s len=%d" % (
            s, (ext.get("title") or "")[:70], ext.get("published_at"),
            ext.get("quality"), len(ext.get("text") or "")))
        log("    excerpt:", (ext.get("text") or "")[:180].replace("\n", " "))
    except Exception as e:
        log("  article fail", url[:90], type(e).__name__, str(e)[:80])

# 1) gismeteo: сырые href из ленты новостей
log("=" * 20, "gismeteo /news/")
try:
    s, html = httpclient.fetch("https://www.gismeteo.ru/news/", timeout=30)
    hrefs = sorted(set(re.findall(r'href="(https?://www\.gismeteo\.ru/news/[^"#?]+|/news/[^"#?]+)"', html)))
    arts = [h for h in hrefs if re.search(r"/news/[a-z0-9\-]+-?\d*", h) and h.rstrip("/").split("/")[-1] not in
            ("weather", "science", "nature", "video", "economics")]
    log("  unique news hrefs:", len(hrefs), "| article-like:", len(arts))
    for h in arts[:6]:
        log("   ", h[:110])
    if arts:
        probe_article(h if arts[0].startswith("http") else "https://www.gismeteo.ru" + arts[0])
except Exception as e:
    log("fail", e)

# 2) svoefermerstvo: где статьи? пробуем /analytics, /media, sitemap, rss-кандидаты
log("=" * 20, "svoe_fermerstvo")
for u in ["https://svoefermerstvo.ru/analytics/", "https://svoefermerstvo.ru/rss/",
          "https://svoefermerstvo.ru/rss.xml", "https://svoefermerstvo.ru/blog/",
          "https://svoefermerstvo.ru/sitemap.xml", "https://svoefermerstvo.ru/media/"]:
    try:
        s, html = httpclient.fetch(u, timeout=30)
        log("OK", u, s, len(html), ("RSS!" if ("<rss" in html[:400].lower() or "<urlset" in html[:400]) else "html"))
        if "<rss" in html[:400].lower():
            links = re.findall(r"<loc>([^<]+)</loc>", html)[:6]
            for l in links: log("   ", l[:110])
        elif "<urlset" in html[:400]:
            log("   sitemap entries sample:", re.findall(r"<loc>([^<]+)</loc>", html)[:4])
        else:
            hrefs = re.findall(r'href="(/[a-z0-9\-/]{6,90})"', html)
            art = [h for h in hrefs if re.search(r"/(analytics|news|articles|media|post)/", h)]
            log("   section links:", sorted(set(art))[:8])
    except Exception as e:
        log("FAIL", u, type(e).__name__, str(e)[:70])

# 3) botanichka RSS: полный разбор + 1 статья
log("=" * 20, "botanichka rss")
try:
    s, xml = httpclient.fetch("https://www.botanichka.ru/feed/", timeout=30)
    items = re.findall(r"<item>(.*?)</item>", xml, re.S)
    log("items:", len(items))
    urls = []
    for it in items[:6]:
        u = re.search(r"<link>([^<]+)</link>", it)
        d = re.search(r"<pubDate>([^<]+)</pubDate>", it)
        t = re.search(r"<title>(?:<!\[CDATA\[)?([^<\]]+)", it)
        log(" ", (u.group(1) if u else "?")[:95], "|", (d.group(1) if d else "?")[:31], "|", (t.group(1) if t else "?")[:50])
        if u: urls.append(u.group(1))
    if urls:
        probe_article(urls[0])
except Exception as e:
    log("fail", type(e).__name__, str(e)[:90])

# 4) agroinvestor RSS: журнал + новости
log("=" * 20, "agroinvestor rss")
for feed in ["https://www.agroinvestor.ru/feed/public-agroinvestor-articles.xml",
             "https://www.agroinvestor.ru/feed/public-agronews.xml"]:
    try:
        s, xml = httpclient.fetch(feed, timeout=30)
        items = re.findall(r"<item>(.*?)</item>", xml, re.S)
        log(feed, "-> items:", len(items))
        for it in items[:4]:
            u = re.search(r"<link>([^<]+)</link>", it)
            d = re.search(r"<pubDate>([^<]+)</pubDate>", it)
            log("   ", (u.group(1) if u else "?")[:95], "|", (d.group(1) if d else "?")[:31])
        if items:
            u = re.search(r"<link>([^<]+)</link>", items[0])
            if u: probe_article(u.group(1))
    except Exception as e:
        log("fail", feed, type(e).__name__, str(e)[:80])
OUT.close()
print("probe2 done")
