from bs4 import BeautifulSoup
from app.extractors.common import clean_text, shorten


def parse_automation_ai(soup: BeautifulSoup) -> dict:
    title_tag = soup.find("h1")

    content_block = soup.find("div", class_="entry-content")
    if not content_block:
        return {}

    paragraphs = []
    for p in content_block.find_all("p"):
        text = p.get_text(strip=True)
        if len(text) > 120:
            paragraphs.append(text)
        if len(paragraphs) >= 3:
            break

    image = content_block.find("img")
    image_url = image.get("src") if image else None

    text = shorten(clean_text("\n\n".join(paragraphs)))

    if not title_tag or not text:
        return {}

    return {
        "title": title_tag.get_text(strip=True),
        "text": text,
        "image": image_url,
    }
