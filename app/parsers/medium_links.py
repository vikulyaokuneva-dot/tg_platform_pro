from bs4 import BeautifulSoup


def extract_medium_links(soup: BeautifulSoup) -> list[str]:
    """
    Извлекает ссылки на статьи из Towards Data Science (Medium)
    Работает с /tagged/automation и /tagged/artificial-intelligence
    """

    links = []
    seen = set()

    # Medium использует <a> с href вида /@user/title-xxxx
    for a in soup.find_all("a", href=True):
        href = a["href"]

        if (
            href.startswith("https://towardsdatascience.com/")
            and "-" in href
            and "?" not in href
        ):
            if href not in seen:
                links.append(href)
                seen.add(href)

    return links
