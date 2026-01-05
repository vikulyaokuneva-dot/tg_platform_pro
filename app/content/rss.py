# app/content/rss.py

import feedparser
from app.content.editor import shorten


def fetch(feed_url: str) -> dict | None:
    """
    Загружает RSS и возвращает один элемент в виде dict:
    {
        title,
        text,
        link,
        image (optional)
    }
    """

    feed = feedparser.parse(feed_url)
    if not feed.entries:
        return None

    entry = feed.entries[0]

    title = entry.get("title", "")
    text = entry.get("summary", "") or entry.get("description", "")
    link = entry.get("link", "")

    image = None

    # Пытаемся достать картинку
    if "media_content" in entry:
        media = entry.media_content
        if media and isinstance(media, list):
            image = media[0].get("url")

    if not image and "links" in entry:
        for link_item in entry.links:
            if link_item.get("type", "").startswith("image"):
                image = link_item.get("href")
                break

    return {
        "title": title,
        "text": text,
        "link": link,
        "image": image,
    }
