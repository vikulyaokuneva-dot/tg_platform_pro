# -*- coding: utf-8 -*-
"""PETS 4.5 research-only content quality checks.

It never calls Telegram's Bot API, AI services, or the PETS production storage.
The rules are deliberately conservative and the labels are diagnostics, not a
claim that a third-party post is safe to republish.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import requests
from bs4 import BeautifulSoup


SITE_PAGES = {
    "proplan_sharpei": "https://www.proplan.ru/dog/breeds/sharpej",
    "proplan_sled_dogs": "https://www.proplan.ru/dog/article/ezdovye-porody",
    "purinaone_breeds": "https://www.purinaone.ru/sitemap",
    "sobakovod_puppy_biting": "https://blog.sobakovod.pro/articles/shchenok-kusaetsya-chto-delat",
    "royalcanin_breeds": "https://royalcanin.ru/dog-breed",
    "petstory_apartment_dogs": "https://petstory.ru/knowledge/dogs/dog-adoption/samye-spokoynye-porody-sobak-malenkogo-srednego-i-bolshogo-razmera/",
    "yandex_market_apartment_dogs": "https://m.integration.vs.market.yandex.net/journal/porody-sobak-dlya-kvartiry-kak-vybrat-kompanona-kotoryy-idealno-vpishetsya-v-vashu-zhizn",
}

PROMO = ("скидк", "промокод", "куп", "закаж", "магазин", "акци", "маркетплейс", "рацион", "корм", "записат", "конференц")
META = ("голосуй", "подпис", "конкурс", "ваканси", "работе", "помощи", "заявк", "с празд", "донат")
MEDICAL = ("ветерин", "ветврач", "болезн", "лечени", "препарат", "паразит", "блох", "клещ", "бешен", "вакцин", "здоров")
CAT = ("кош", "кот", "котён", "котен")
DOG = ("собак", "щен", "пс", "пёс", "пес", "пород")


def _normalise(text: str) -> str:
    return re.sub(r"[^а-яёa-z0-9 ]", " ", (text or "").lower()).strip()


def _matches(text: str, words: tuple[str, ...]) -> bool:
    return any(word in text for word in words)


def label_post(post: dict) -> dict:
    """Return a conservative label for an already-retrieved short excerpt."""
    raw = post.get("text_excerpt") or ""
    text = _normalise(raw)
    tokens = set(text.split())
    species = "mixed"
    if _matches(text, CAT) and not _matches(text, DOG):
        species = "cat"
    elif _matches(text, DOG) and not _matches(text, CAT):
        species = "dog"
    label = "useful_theme"
    reason = "concrete pet-owner topic requires independent factual brief"
    if len(tokens) < 5:
        label, reason = "irrelevant_or_empty", "no usable textual topic in short excerpt"
    elif _matches(text, PROMO):
        label, reason = "advertising_or_promo", "commercial or conversion language present"
    elif _matches(text, META):
        label, reason = "irrelevant_or_meta", "channel/community administration rather than an owner topic"
    veterinary_review = _matches(text, MEDICAL)
    ready_for_original = label == "useful_theme" and not veterinary_review
    return {
        **post, "species": species, "quality_label": label, "quality_reason": reason,
        "veterinary_review_required": veterinary_review,
        "eligible_as_original_topic": ready_for_original,
    }


def analyse_posts(posts: list[dict]) -> dict:
    labelled = [label_post(post) for post in posts]
    # A repeat is deliberately narrow: almost the same non-trivial excerpt.
    # Broadly similar subjects are still useful independent ideas and must be
    # reviewed by an editor rather than erased by a heuristic.
    fingerprints: list[set[str]] = []
    for item in labelled:
        tokens = set(_normalise(item.get("text_excerpt", "")).split())
        duplicate = any(
            len(tokens) >= 8 and len(previous) >= 8
            and len(tokens & previous) / len(tokens | previous) >= 0.85
            for previous in fingerprints
        )
        if duplicate and item["quality_label"] == "useful_theme":
            item["quality_label"] = "repeat_or_near_duplicate"
            item["quality_reason"] = "near-identical short excerpt already present in this sample"
            item["eligible_as_original_topic"] = False
        fingerprints.append(tokens)
    counts = Counter(item["quality_label"] for item in labelled)
    species = Counter(item["species"] for item in labelled if item["quality_label"] == "useful_theme")
    eligible = [item for item in labelled if item["eligible_as_original_topic"]]
    veterinary = [item for item in labelled if item["veterinary_review_required"]]
    return {
        "posts_total": len(labelled), "labels": dict(counts), "useful_species": dict(species),
        "eligible_original_topic_count": len(eligible), "veterinary_review_count": len(veterinary),
        "items": labelled,
    }


def probe_page(source_id: str, url: str, session=requests) -> dict:
    """One bounded HTTP request; no crawl, login, media download, or scraping loop."""
    response = session.get(url, headers={"User-Agent": "PETS-4.5-research/1.0 (bounded source audit)"}, timeout=20)
    soup = BeautifulSoup(response.text, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    h1 = soup.find("h1")
    paragraphs = [node.get_text(" ", strip=True) for node in soup.select("p")]
    links = [node.get("href", "") for node in soup.select("a[href]")]
    internal_links = [href for href in links if href.startswith("/") or url.split("/")[2] in href]
    return {
        "source_id": source_id, "requested_url": url, "final_url": response.url,
        "http_status": response.status_code, "response_bytes": len(response.content),
        "title": title[:240], "h1": h1.get_text(" ", strip=True)[:240] if h1 else "",
        "text_available": bool(" ".join(paragraphs).strip()),
        "paragraph_count": len(paragraphs), "internal_link_count": len(internal_links),
        "navigation_or_catalog_detected": len(internal_links) >= 10,
        "retrieval_status": "success" if response.status_code == 200 and title else "failed",
    }


def write_analysis(telegram_json: str | Path, output: str | Path) -> dict:
    """Analyse an existing Telegram artifact only; this function does no network I/O."""
    payload = json.loads(Path(telegram_json).read_text(encoding="utf-8"))
    result = analyse_posts(payload["posts"])
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "telegram_content_quality.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result
