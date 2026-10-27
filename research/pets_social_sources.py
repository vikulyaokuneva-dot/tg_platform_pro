# -*- coding: utf-8 -*-
"""Small PETS 4.4 research-only reader for public Telegram channel previews.

This module deliberately has no dependency on ``case_pipeline`` and is never
called by a scheduled workflow. It records short metadata/excerpts only, so
it can evaluate public channels as *idea* sources without copying posts.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import requests
from bs4 import BeautifulSoup


PUBLIC_TELEGRAM_CHANNELS = (
    "vetpetcare_vpc", "ne_idealnaya_sobaka", "kanal_shukina_zooexpert",
    "koshatnikam", "prikotik", "s_pets", "PitomnikSobak", "superpet_ru",
    "bobig_ru", "textcats",
)
USER_AGENT = "PETS-4.4-research/1.0 (public idea-source audit; no crawling)"


def _excerpt(value: str, limit: int = 240) -> str:
    return re.sub(r"\s+", " ", value or "").strip()[:limit]


def _message_record(message, source_name: str) -> dict | None:
    post = message.get("data-post", "")
    if not post or "/" not in post:
        return None
    text_node = message.select_one(".tgme_widget_message_text")
    time_node = message.select_one("time[datetime]")
    photo_node = message.select_one(".tgme_widget_message_photo_wrap")
    text = _excerpt(text_node.get_text(" ", strip=True) if text_node else "")
    return {
        "platform": "telegram", "source_name": source_name,
        "post_url": "https://t.me/" + post,
        "published_at": time_node.get("datetime") if time_node else None,
        "text_excerpt": text, "text_available": bool(text),
        "image_available": photo_node is not None, "topic": "unclassified",
        "retrieval_status": "success",
    }


def fetch_public_telegram_preview(handle: str, *, limit: int = 10, session=requests) -> tuple[list[dict], dict]:
    """Read at most ten entries from a public ``t.me/s`` preview page.

    Private channels, authenticated APIs, pagination loops, and media downloads
    are intentionally unsupported.
    """
    if not 1 <= limit <= 10:
        raise ValueError("limit must be in 1..10")
    url = f"https://t.me/s/{handle}"
    response = session.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
    diagnostic = {
        "platform": "telegram", "source_name": handle, "url": url,
        "http_status": response.status_code, "response_bytes": len(response.content),
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "posts_found_in_html": 0, "posts_returned": 0,
        "retrieval_status": "http_error" if response.status_code != 200 else "empty_preview",
    }
    if response.status_code != 200:
        return [], diagnostic
    messages = BeautifulSoup(response.text, "html.parser").select(".tgme_widget_message[data-post]")
    diagnostic["posts_found_in_html"] = len(messages)
    records = [record for message in messages if (record := _message_record(message, handle))][-limit:]
    diagnostic["posts_returned"] = len(records)
    if records:
        diagnostic["retrieval_status"] = "success"
    return records, diagnostic


def run_telegram_research(handles: Iterable[str] = PUBLIC_TELEGRAM_CHANNELS, *, output: str | Path,
                          delay_seconds: float = 1.0) -> dict:
    """Run a bounded Telegram-only research probe and save non-secret JSON."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    posts, diagnostics = [], []
    for index, handle in enumerate(handles):
        if index:
            time.sleep(delay_seconds)
        found, diagnostic = fetch_public_telegram_preview(handle)
        posts.extend(found)
        diagnostics.append(diagnostic)
    payload = {"research_only": True, "platform": "telegram", "posts": posts, "diagnostics": diagnostics}
    (output / "telegram_public_preview.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


if __name__ == "__main__":
    run_telegram_research(output=Path("runs") / "pets_4_4_social_sources")
