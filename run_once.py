import asyncio
import logging
import sys
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup
import trafilatura
from aiogram import Bot
from aiogram.enums import ParseMode

# Импорт конфигурации и базы данных
# Предполагается, что bot_database.py лежит рядом и имеет класс Database
try:
    from config import BOT_TOKEN, CHANNEL_IDS, HTML_SOURCES, HEADERS
    from bot_database import Database 
except ImportError as e:
    print(f"CRITICAL ERROR: Import failed. {e}")
    sys.exit(1)

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class NewsPoster:
    def __init__(self):
        if not BOT_TOKEN:
            logger.error("BOT_TOKEN is missing in env vars!")
            sys.exit(1)
        
        self.bot = Bot(token=BOT_TOKEN)
        self.db = Database("bot_database.db")

    async def fetch_html(self, session, url):
        """Скачивает HTML страницы с защитой от ошибок"""
        try:
            async with session.get(url, headers=HEADERS, timeout=15) as response:
                if response.status == 200:
                    return await response.text()
                else:
                    logger.warning(f"Failed to fetch {url}: Status {response.status}")
                    return None
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            return None

    async def get_article_links(self, session, source_conf):
        """Парсит страницу рубрики и собирает ссылки на новые статьи"""
        html = await self.fetch_html(session, source_conf['url'])
        if not html:
            return []

        soup = BeautifulSoup(html, 'html.parser')
        links = []
        
        # Ищем элементы по CSS-селектору из конфига
        elements = soup.select(source_conf['link_selector'])
        
        for el in elements:
            href = el.get('href')
            if not href:
                continue
            
            # Превращаем относительные ссылки (/post/1) в абсолютные (https://site.com/post/1)
            full_link = urljoin(source_conf.get('base_url', source_conf['url']), href)
            links.append(full_link)
        
        # Убираем дубликаты и возвращаем список (ограничим 5 последними, чтобы не спамить)
        return list(set(links))[:5]

    async def process_article(self, session, link, category, channel_id):
        """Скачивает статью, вытаскивает текст и постит"""
        
        # 1. Проверка в базе данных
        if self.db.url_exists(link):
            return False

        logger.info(f"Processing new article: {link}")
        
        # 2. Скачивание контента
        html = await self.fetch_html(session, link)
        if not html:
            return False

        # 3. Магия Trafilatura (извлечение "мяса")
        # include_images=False, так как мы пока только текст постим
        downloaded = trafilatura.extract(html, include_comments=False, include_tables=False)
        
        if not downloaded:
            logger.warning(f"Trafilatura could not extract text from {link}")
            return False

        # Получаем метаданные (заголовок) отдельно, если нужно
        # Но trafilatura часто возвращает просто текст. 
        # Попробуем найти заголовок через BS4 для надежности
        soup_article = BeautifulSoup(html, 'html.parser')
        title_tag = soup_article.find('h1')
        title = title_tag.get_text().strip() if title_tag else "New Article"

        # 4. Формирование поста
        # Обрезаем текст до 800 символов + ссылка
        preview_text = downloaded[:800] + "..." if len(downloaded) > 800 else downloaded
        
        # Экранирование HTML тегов в тексте, чтобы не сломать разметку Telegram
        from html import escape
        safe_title = escape(title)
        safe_preview = escape(preview_text)

        message = (
            f"<b>{safe_title}</b>\n\n"
            f"{safe_preview}\n\n"
            f"👉 <a href='{link}'>Читать полностью</a>"
        )

        # 5. Отправка в Telegram
        try:
            await self.bot.send_message(
                chat_id=channel_id,
                text=message,
                parse_mode=ParseMode.HTML
            )
            logger.info(f"SUCCESS: Posted to {category}")
            
            # 6. Сохранение в БД
            self.db.add_url(link, category)
            return True
            
        except Exception as e:
            logger.error(f"Telegram Error ({category}): {e}")
            return False

    async def run(self):
        logger.info("Starting run_once job...")
        
        async with aiohttp.ClientSession() as session:
            for category, sources in HTML_SOURCES.items():
                
                channel_id = CHANNEL_IDS.get(category)
                if not channel_id:
                    logger.warning(f"Skipping {category}: No Channel ID found in env.")
                    continue
                
                logger.info(f"--- Checking category: {category} ---")
                
                for source in sources:
                    logger.info(f"Scanning source: {source['name']}")
                    
                    # Получаем ссылки с главной страницы
                    links = await self.get_article_links(session, source)
                    
                    for link in links:
                        # Обрабатываем статью
                        posted = await self.process_article(session, link, category, channel_id)
                        
                        if posted:
                            # Пауза 5 секунд между постами, чтобы не спамить
                            await asyncio.sleep(5) 
        
        # Закрываем сессию бота
        await self.bot.session.close()
        logger.info("Job finished successfully.")

if __name__ == "__main__":
    poster = NewsPoster()
    try:
        asyncio.run(poster.run())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
