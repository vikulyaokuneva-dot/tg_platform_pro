import asyncio
import aiohttp
from bs4 import BeautifulSoup
import trafilatura
from config import HTML_SOURCES

class HTMLParser:
    def __init__(self):
        # Притворяемся обычным браузером, чтобы нас не банили
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

    async def fetch_html(self, session, url):
        try:
            async with session.get(url, headers=self.headers, timeout=15) as response:
                if response.status == 200:
                    return await response.text()
                else:
                    print(f"Error {response.status} fetching {url}")
                    return None
        except Exception as e:
            print(f"Exception fetching {url}: {e}")
            return None

    async def get_new_links(self, session, source_config):
        """Собирает ссылки на статьи с главной страницы рубрики"""
        html = await self.fetch_html(session, source_config['url'])
        if not html:
            return []

        soup = BeautifulSoup(html, 'html.parser')
        links = []
        
        # Находим все элементы по селектору
        elements = soup.select(source_config['link_selector'])
        
        for el in elements:
            link = el.get('href')
            if not link:
                continue
            
            # Обработка относительных ссылок (/news/123 -> https://site.com/news/123)
            if link.startswith('/'):
                from urllib.parse import urljoin
                link = urljoin(source_config['url'], link)
                
            links.append(link)
            
        # Возвращаем уникальные ссылки (set), чтобы не дублировать
        return list(set(links))

    def extract_article_content(self, html_content, url):
        """
        Магия Trafilatura: вытаскивает заголовок и текст статьи, 
        игнорируя меню, рекламу и футеры.
        """
        downloaded = trafilatura.extract(
            html_content,
            include_comments=False,
            include_tables=False,
            no_fallback=True,
            url=url # Помогает резолвить относительные пути картинок
        )
        
        if downloaded:
            # Trafilatura возвращает чистый текст или XML. 
            # Иногда удобнее получить JSON-структуру metadata
            # Но для простоты вернем текст.
            return downloaded
        return None

    # Дополнительно: Если нужно получить заголовок отдельно
    def extract_metadata(self, html_content):
        return trafilatura.bare_extraction(html_content)

