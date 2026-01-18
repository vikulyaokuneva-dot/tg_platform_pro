
from bs4 import BeautifulSoup


def extract_hackernoon_links(soup: BeautifulSoup) -> list[str]:
    """
    Извлекает ссылки на статьи из HackerNoon по тегам
    """

    links = []
    seen = set()

    for a in soup.select("a.story-card-title"):
        href = a.get("href")
        if not href:
            continue

        if href.startswith("/"):
            href = "https://hackernoon.com" + href

        if href not in seen:
            links.append(href)
            seen.add(href)

    return links
