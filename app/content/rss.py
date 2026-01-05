from bs4 import BeautifulSoup
import feedparser
import random


def extract_image_from_html(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    img = soup.find("img")
    if img and img.get("src"):
        return img["src"]
    return None


def fetch(feed_url: str) -> dict | None:
    feed = feedparser.parse(feed_url)
    if not feed.entries:
        return None

    entry = random.choice(feed.entries)

    html = entry.get("summary", "")
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text().strip()

    image = None

    # 1️⃣ media:content
    if "media_content" in entry:
        image = entry.media_content[0].get("url")

    # 2️⃣ img inside summary
    if not image:
        image = extract_image_from_html(html)

    return {
        "title": entry.get("title", ""),
        "text": text,
        "image": image,
        "link": entry.get("link"),
    }
