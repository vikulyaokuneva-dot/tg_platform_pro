# -*- coding: utf-8 -*-
"""case_pipeline.extraction — HTML -> clean text + metadata + quality.

Стратегия перенесена из валидированного PoC (parser_poc_results/poc_extract.py):
JSON-LD + OpenGraph + trafilatura (strict no_fallback и default-with-tables,
берётся более длинный). Качество: good/partial/poor/failed по длине текста
(пороги = size-gate классификатора).
"""
import json
import re

import trafilatura
from bs4 import BeautifulSoup

from . import config

LD_FIELDS = ["headline", "description", "datePublished", "dateModified",
             "author", "publisher", "image", "articleSection", "url",
             "@type", "mainEntityOfPage"]

SUSPECT_RX = re.compile(r"showcaptcha|cf-challenge|just a moment|"
                        r"enable javascript and cookies|__wbaas", re.I)


def _walk_ld(node, out):
    if isinstance(node, list):
        for n in node:
            _walk_ld(n, out)
    elif isinstance(node, dict):
        t = node.get("@type", "")
        types = t if isinstance(t, list) else [t]
        if any(x in ("Article", "BlogPosting", "NewsArticle", "TechArticle",
                     "Reportage", "WebPage", "Report") for x in types):
            out.append({k: node.get(k) for k in LD_FIELDS if node.get(k) is not None})
        for key in ("@graph", "mainEntity", "about", "subjectOf"):
            if node.get(key):
                _walk_ld(node[key], out)


def extract_ld(html):
    soup = BeautifulSoup(html, "html.parser")
    found = []
    for s in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = s.string or s.get_text()
        if not raw:
            continue
        try:
            data = json.loads(raw.strip())
        except Exception:
            try:
                data = json.loads(raw.strip()[: raw.rfind("}") + 1])
            except Exception:
                continue
        _walk_ld(data, found)
    return found


def extract_og(html):
    soup = BeautifulSoup(html, "html.parser")
    og = {}
    for prop in ("og:title", "og:description", "og:url", "og:image", "og:type",
                 "og:site_name", "article:published_time", "article:modified_time"):
        m = soup.find("meta", attrs={"property": prop}) or soup.find("meta", attrs={"name": prop})
        if m and m.get("content"):
            og[prop] = m["content"].strip()
    t = soup.find("title")
    if t and t.string:
        og["<title>"] = t.string.strip()
    return og


def _first_article(recs):
    for r in recs:
        if r.get("headline") or r.get("description"):
            return r
    return {}


def _lang_of(text):
    cyr = len(re.findall(r"[а-яёА-ЯЁ]", text[:4000] or ""))
    lat = len(re.findall(r"[a-zA-Z]", text[:4000] or ""))
    return "ru" if cyr > lat else "en"


def extract_from_html(html, url):
    """Возвращает dict: text, quality, language, title, description,
    published_at, author, image, publisher, sitename, suspect_captcha."""
    ld = extract_ld(html)
    og = extract_og(html)
    art = _first_article(ld)

    a = trafilatura.extract(html, url=url, include_comments=False,
                            include_tables=False, no_fallback=True)
    b = trafilatura.extract(html, url=url, include_comments=False,
                            include_tables=True)
    text = b if (b and (not a or len(b) > len(a))) else a
    text = (text or "").strip()

    meta = trafilatura.bare_extraction(html, url=url, with_metadata=True)
    md = meta.as_dict() if meta is not None else {}

    n = len(text)
    if n == 0:
        quality = "failed"
    elif n < config.QUALITY_PARTIAL:
        quality = "poor"
    elif n < config.QUALITY_GOOD:
        quality = "partial"
    else:
        quality = "good"

    author = art.get("author") or md.get("author") or ""
    if isinstance(author, dict):
        author = author.get("name", "")
    elif isinstance(author, list) and author:
        author = author[0].get("name", "") if isinstance(author[0], dict) else str(author[0])

    # Порядок title: trafilatura/OG (как в валидированном holdout-замере),
    # JSON-LD headline — только fallback.
    title = md.get("title") or og.get("og:title") or og.get("<title>") or art.get("headline") or ""

    return {
        "text": text,
        "quality": quality,
        "language": _lang_of(text),
        "title": title,
        "description": md.get("description") or og.get("og:description") or art.get("description") or "",
        "published_at": art.get("datePublished") or og.get("article:published_time") or md.get("date") or "",
        "author": author,
        "image": art.get("image") if isinstance(art.get("image"), str) else (og.get("og:image") or ""),
        "publisher": art.get("publisher").get("name", "") if isinstance(art.get("publisher"), dict) else (art.get("publisher") or ""),
        "sitename": md.get("sitename") or og.get("og:site_name") or "",
        "suspect_captcha": bool(SUSPECT_RX.search(html[:8000] or "")),
    }


def classifier_meta(ext):
    """Маппинг extraction-результата в metadata-контракт классификатора
    (идентично валидированному ho_classify.load_item)."""
    return {
        "title": ext.get("title") or "",
        "description": ext.get("description") or "",
        "url": "",
        "publisher": ext.get("publisher") or "",
        "sitename": ext.get("sitename") or "",
    }
