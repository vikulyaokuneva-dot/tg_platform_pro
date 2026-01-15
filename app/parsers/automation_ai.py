from bs4 import BeautifulSoup
from app.extractors.common import clean_text, shorten


def parse_automation_ai(soup: BeautifulSoup) -> dict:
    """
    Парсер статей automation-ai.pro
    """
    title_tag = soup.find("h1")
    content_block = soup.find("article") or soup.find("div", class_="entry-content")

    paragraphs = content_block.find_all("p") if content_block else []
    image_tag = content_block.find("img") if content_block else None

    text = "\n".join(
        p.get_text(strip=True)
        for p in paragraphs
        if len(p.get_text(strip=True)) > 70
    )

    text = shorten(clean_text(text))

    return {
        "title": title_tag.get_text(strip=True) if title_tag else "",
        "text": text,
        "image": image_tag["src"] if image_tag and image_tag.get("src") else None,
    }
