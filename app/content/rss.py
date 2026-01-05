import feedparser
from bs4 import BeautifulSoup
import random


def fetch(feed_url: str) -> dict | None:
    feed = feedparser.parse(feed_url)
    if not feed.entries:
        return None

    entry = random.choice(feed.entries)

    html = entry.get("summary", "")
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text().strip()

    image = None
    if "media_content" in entry:
        image = entry.media_content[0].get("url")

    return {
        "title": entry.get("title", ""),
        "text": text,
        "image": image,
        "link": entry.get("link"),
    }
