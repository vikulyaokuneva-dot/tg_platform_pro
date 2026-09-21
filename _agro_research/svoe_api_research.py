# -*- coding: utf-8 -*-
"""§8 Исследование «Своё Фермерство» (svoefermerstvo.ru): есть ли стабильный
публичный discovery-слой (sitemap/RSS/API/embedded state). Только GET без
авторизации; ничего не меняем в коде."""
import io
import json
import re
import sys

sys.path.insert(0, ".")
from case_pipeline import httpclient

OUT = io.open("_agro_research/svoe_api_research.txt", "w", encoding="utf-8")
def w(*x): OUT.write(" ".join(str(i)[:220] for i in x) + "\n")

def probe(u, note=""):
    try:
        s, body = httpclient.fetch(u, timeout=30)
        return s, body, note
    except Exception as e:
        return None, None, "%s: %s" % (type(e).__name__, str(e)[:90])

w("1) robots.txt / sitemap-указания")
s, body, err = probe("https://svoefermerstvo.ru/robots.txt")
if body:
    w("  robots http=%s:" % s)
    for line in body.splitlines()[:25]:
        w("   ", line[:150])
else:
    w("  robots fail:", err)

w("\n2) sitemap-кандидаты")
for u in ["https://svoefermerstvo.ru/sitemap.xml", "https://svoefermerstvo.ru/sitemap_index.xml",
          "https://svoefermerstvo.ru/sitemap/sitemap.xml", "https://svoefermerstvo.ru/yandex.xml"]:
    s, body, err = probe(u)
    if body:
        locs = re.findall(r"<loc>([^<]+)</loc>", body)
        w("  OK %s http=%s size=%d loc=%d" % (u, s, len(body), len(locs)))
        for l in locs[:5]:
            w("     ", l[:120])
    else:
        w("  FAIL %s -> %s" % (u, err))

w("\n3) RSS-кандидаты")
for u in ["https://svoefermerstvo.ru/rss.xml", "https://svoefermerstvo.ru/feed",
          "https://svoefermerstvo.ru/rss", "https://svoefermerstvo.ru/api/rss"]:
    s, body, err = probe(u)
    if body:
        is_xml = "<rss" in body[:300].lower() or "<feed" in body[:300].lower()
        w("  %s -> http %s, xml=%s" % (u, s, is_xml))
    else:
        w("  %s -> %s" % (u, err))

w("\n4) __NUXT__ embedded state на /analytics/ (ссылки в SSR-данных?)")
s, abody, err = probe("https://svoefermerstvo.ru/analytics/")
body = abody
if body:
    w("  /analytics/ http=%s size=%d" % (s, len(body)))
    m = re.search(r'<script[^>]+id="__NUXT_DATA__"[^>]*>(.*?)</script>', body, re.S)
    blob = m.group(1) if m else None
    w("  __NUXT_DATA__ present:", bool(blob), "len:", len(blob or ""))
    hay = blob or body
    slugs = sorted(set(re.findall(r'"(/[a-z0-9\-]*(?:article|news|material|analytics|post)[a-z0-9\-/\"]{0,60})"', hay, re.I)))
    w("  state article-like paths:", slugs[:15])
    api = sorted(set(re.findall(r'"(https?://[^"]*api[^"]{0,80}|/[a-z\-]+/api/[^"]{0,60}|/api/[^"]{0,60})"', hay, re.I)))
    w("  api hints:", api[:15])
else:
    w("  fail:", err)

w("\n5) вероятные публичные JSON-эндпоинты (по хинтам/типичные для бэка)")
for u in ["https://svoefermerstvo.ru/api/articles?page=1", "https://svoefermerstvo.ru/api/posts",
          "https://svoefermerstvo.ru/api/news?page=1", "https://svoefermerstvo.ru/api/v1/articles",
          "https://api.svoefermerstvo.ru/articles", "https://svoefermerstvo.ru/bff/articles"]:
    s, body, err = probe(u)
    kind = "NONE"
    if body:
        kind = ("JSON" if body[:20].strip().startswith(("{", "[")) else "html/spa")
    w("  %s -> %s %s" % (u, s or err.split(':')[0], kind))

w("\n6) имя бэкенда из HTML-мета/скриптов (эвристика)")
if abody:
    tech = re.findall(r'(content-api|strapi|directus|drupal|bitrix|kubernetes|graphql)[^"\s]{0,30}', abody, re.I)
    w("  tech hints:", sorted(set(t.lower() for t in tech))[:6])
OUT.close()
print("svoe research done")
