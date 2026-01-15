from bs4 import BeautifulSoup
from app.extractors.common import clean_text, shorten


def parse_automation_ai(soup: BeautifulSoup) -> dict:
    title = soup.find("h1")

    article = soup.find("article")
    if not article:
        return {}

    paragraphs = []
    for p in article.find_all("p"):
        text = p.get_text(strip=True)
        if len(text) > 120:
            paragraphs.append(text)
        if len(paragraphs) >= 3:
            break

    image = article.find("img")
    image_url = None
    if image:
        image_url = image.get("src") or image.get("data-src")

    text = shorten(clean_text("\n\n".join(paragraphs)))

    return {
        "title": title.get_text(strip=True) if title else "",
        "text": text,
        "image": image_url,
    }
