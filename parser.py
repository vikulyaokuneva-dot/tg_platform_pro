import asyncio
import logging
import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import hashlib

logger = logging.getLogger(__name__)

class ArticleParser:
    """
    Класс для парсинга статей с сайтов
    """
    def __init__(self):
        self.session = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def fetch_page(self, url):
        """
        Получение HTML-страницы по URL
        """
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    return await response.text()
                else:
                    logger.warning(f"Ошибка при получении страницы {url}: {response.status}")
                    return None
        except Exception as e:
            logger.error(f"Исключение при получении страницы {url}: {e}")
            return None
    
    async def parse_article(self, url):
        """
        Парсинг статьи по URL
        """
        html = await self.fetch_page(url)
        if not html:
            return None
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Попробуем найти заголовок статьи
        title_elem = soup.find(['h1', 'h2', 'h3'])
        title = title_elem.get_text().strip() if title_elem else "Без заголовка"
        
        # Попробуем найти основной текст статьи
        # Обычно это элементы с классами типа 'content', 'article', 'post', 'entry-content'
        content_selectors = [
            'article',
            '.content',
            '.article',
            '.post',
            '.entry-content',
            '.main-content',
            '[role="main"]',
            '.story-body'
        ]
        
        content = ""
        for selector in content_selectors:
            content_elem = soup.select_one(selector)
            if content_elem:
                # Удаляем вложенные элементы, которые не являются частью контента
                for elem in content_elem.find_all(['script', 'style', 'nav', 'aside', 'header', 'footer']):
                    elem.decompose()
                
                content = content_elem.get_text(separator=' ', strip=True)
                if content:
                    break
        
        # Если не удалось найти контент с помощью селекторов, берем весь текст body
        if not content:
            body_elem = soup.find('body')
            if body_elem:
                for elem in body_elem.find_all(['script', 'style', 'nav', 'aside', 'header', 'footer']):
                    elem.decompose()
                content = body_elem.get_text(separator=' ', strip=True)
        
        if content:
            # Ограничиваем длину контента
            max_length = 500
            if len(content) > max_length:
                content = content[:max_length] + "..."
            
            # Создаем уникальный ID статьи на основе URL
            article_id = hashlib.md5(url.encode()).hexdigest()
            
            return {
                'id': article_id,
                'title': title,
                'url': url,
                'content': content,
                'source_domain': urlparse(url).netloc
            }
        
        return None
    
    async def get_articles_from_source(self, source_url, keywords=None):
        """
        Получение статей из указанного источника
        """
        articles = []
        
        # Получаем главную страницу сайта
        html = await self.fetch_page(source_url)
        if not html:
            return articles
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Находим ссылки на статьи на главной странице или в категориях
        link_selectors = [
            'a[href*="/article/"]',
            'a[href*="/post/"]',
            'a[href*="/news/"]',
            'a[href*="/blog/"]',
            '.post-title a',
            '.article-title a',
            'h2 a',
            'h3 a'
        ]
        
        found_urls = set()
        
        for selector in link_selectors:
            links = soup.select(selector)
            for link in links:
                href = link.get('href')
                if href:
                    full_url = urljoin(source_url, href)
                    # Проверяем, что URL принадлежит тому же домену
                    if urlparse(full_url).netloc == urlparse(source_url).netloc:
                        found_urls.add(full_url)
        
        # Если не нашли ссылки через селекторы, пробуем найти все ссылки на странице
        if not found_urls:
            all_links = soup.find_all('a', href=True)
            for link in all_links:
                href = link.get('href')
                if href:
                    full_url = urljoin(source_url, href)
                    if urlparse(full_url).netloc == urlparse(source_url).netloc:
                        # Проверяем, содержит ли URL признаки статьи
                        if any(keyword in full_url.lower() for keyword in ['article', 'post', 'news', 'blog']):
                            found_urls.add(full_url)
        
        # Парсим каждую найденную статью
        for url in found_urls:
            article = await self.parse_article(url)
            if article:
                # Если заданы ключевые слова, проверяем, содержатся ли они в статье
                if keywords:
                    content_lower = article['content'].lower()
                    title_lower = article['title'].lower()
                    
                    if any(keyword.lower() in content_lower or keyword.lower() in title_lower for keyword in keywords):
                        articles.append(article)
                else:
                    articles.append(article)
        
        return articles