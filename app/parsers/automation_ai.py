import requests
from bs4 import BeautifulSoup

from app.extractors.common import clean_text, shorten


URL = "https://www.automationai.io/blog"


def parse_automation_ai():
    """
    Парсер AutomationAI — AI автоматизация, бизнес, инструменты
    """
    articles = []

    resp = requests.get(
        URL,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=15,
    )

    if resp.status_code != 200:
        print("[automation_ai] page not loaded")
        return articles

    soup = BeautifulSoup(resp.text, "html.parser")

    for card in soup.select("article"):
        try:
            title_el = card.find("h2")
            link_el = card.find("a")
            img_el = card.find("img")

            if not title_el or not link_el:
                continue

            title = clean_text(title_el.get_text())
            link = link_el.get("href")

            if not link.startswith("http"):
                link = "https://www.automationai.io" + link

            # Загружаем страницу статьи
            page = requests.get(link, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            article_soup = BeautifulSoup(page.text, "html.parser")

            content_el = article_soup.select_one("article")

            if not content_el:
                continue

            text = clean_text(content_el.get_text())
            text = shorten(text)

            image = None
            if img_el:
                image = img_el.get("src")

            articles.append(
                {
                    "title": title,
                    "content": text,
                    "image": image,
                    "source": link,
                }
            )

        except Exception as e:
            print("[automation_ai] skip article:", e)

    print(f"[automation_ai] parsed {len(articles)} articles")
    return articles
