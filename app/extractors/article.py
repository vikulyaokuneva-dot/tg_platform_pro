from bs4 import BeautifulSoup


def extract_article(soup: BeautifulSoup) -> dict:
    title = soup.find("h1")
    paragraphs = soup.find_all("p")
    image = soup.find("img")

    text = "\n".join(
        p.get_text(strip=True)
        for p in paragraphs
        if len(p.get_text(strip=True)) > 50
    )

    image_url = image["src"] if image and image.get("src") else None

    return {
        "title": title.get_text(strip=True) if title else "",
        "text": text[:3500],  # лимит Telegram
        "image": image_url,
    }
