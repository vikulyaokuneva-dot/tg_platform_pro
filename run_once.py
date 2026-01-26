import asyncio
import logging
import sys
import os
from urllib.parse import urljoin
from html import escape

import aiohttp
from bs4 import BeautifulSoup
import trafilatura
from aiogram import Bot
from aiogram.enums import ParseMode

# --- ИМПОРТЫ ЛОКАЛЬНЫХ МОДУЛЕЙ ---
try:
    from config import CHANNEL_IDS, HTML_SOURCES, HEADERS
    from bot_database import Database
    from ai_writer import AIWriter
except ImportError as e:
    print(f"CRITICAL ERROR: Import failed. Make sure config.py, bot_database.py and ai_writer.py exist. Details: {e}")
    sys.exit(1)

# --- НАСТРОЙКА ЛОГИРОВАНИЯ ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# --- ПОЛУЧЕНИЕ СЕКРЕТОВ ---
# Используем имя POSTER_BOT_TOKEN, как договаривались
BOT_TOKEN = os.getenv("POSTER_BOT_TOKEN")
GIGACHAT_KEY = os.getenv("GIGACHAT_API_KEY")

class NewsPoster:
    def __init__(self):
        if not BOT_TOKEN:
            logger.critical("POSTER_BOT_TOKEN is missing in env vars! Exiting.")
            sys.exit(1)
        
        self.bot = Bot(token=BOT_TOKEN)
        self.db = Database("bot_database.db")
        
        # Инициализация AI (если ключа нет, будет работать в режиме обрезки текста)
        self.ai = AIWriter(GIGACHAT_KEY)
        if not GIGACHAT_KEY:
            logger.warning("GIGACHAT_API_KEY not found. AI summarization is DISABLED.")

    async def fetch_html(self, session, url):
        """Скачивает HTML страницы с защитой от ошибок и таймаутом"""
        try:
            async with session.get(url, headers=HEADERS, timeout=20) as response:
                if response.status == 200:
                    return await response.text()
                else:
                    logger.warning(f"Failed to fetch {url}: Status {response.status}")
                    return None
        except asyncio.TimeoutError:
            logger.error(f"Timeout fetching {url}")
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
        try:
            elements = soup.select(source_conf['link_selector'])
        except Exception as e:
            logger.error(f"Invalid selector for {source_conf['name']}: {e}")
            return []
        
        logger.info(f"Source {source_conf['name']}: Found {len(elements)} raw elements")

        for el in elements:
            href = el.get('href')
            if not href:
                continue
            
            # Превращаем относительные ссылки (/post/1) в абсолютные
            base_url = source_conf.get('base_url', source_conf['url'])
            full_link = urljoin(base_url, href)
            links.append(full_link)
        
        # Убираем дубликаты, сохраняя порядок, и берем последние 5
        unique_links = list(dict.fromkeys(links))[:5]
        return unique_links

    async def process_article(self, session, link, category, channel_id):
        """Полный цикл: проверка -> скачивание -> AI -> постинг -> сохранение"""
        
        # 1. Проверка в базе данных (чтобы не постить старое)
        if self.db.url_exists(link):
            return False

        logger.info(f"⚡ Processing new article: {link}")
        
        # 2. Скачивание контента статьи
        html = await self.fetch_html(session, link)
        if not html:
            return False

        # 3. Trafilatura: Извлечение чистого текста
        try:
            downloaded_text = trafilatura.extract(
                html, 
                include_comments=False, 
                include_tables=False, 
                no_fallback=True
            )
        except Exception as e:
            logger.error(f"Trafilatura error on {link}: {e}")
            downloaded_text = None

        if not downloaded_text or len(downloaded_text) < 100:
            logger.warning(f"Skipping {link}: Content too short or extraction failed.")
            # Можно пометить как 'skipped' в БД, чтобы не мучать снова, но пока просто пропускаем
            return False

        # 4. GigaChat: Генерация саммари
        logger.info("   🤖 Asking GigaChat to summarize...")
        ai_summary = await self.ai.summarize(downloaded_text, category)
        
        # 5. Формирование сообщения
        # Экранируем теги, чтобы AI не сломал HTML-разметку Telegram
        safe_text = escape(ai_summary)
        
        # Жирный заголовок AI делает сам (или мы его просим), но для надежности
        # форматируем текст. GigaChat может вернуть маркдаун (**bold**), 
        # но мы используем HTML ParseMode. Простой escape безопаснее.
        
        message = (
            f"{safe_text}\n\n"
            f"🔗 <a href='{link}'>Читать оригинал</a>"
        )

        # 6. Отправка в Telegram
        try:
            # Пытаемся отправить
            await self.bot.send_message(
                chat_id=channel_id,
                text=message,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=False 
            )
            logger.info(f"   ✅ SUCCESS: Posted to {category}")
            
            # 7. Сохранение в БД (фиксируем успех)
            self.db.add_url(link, category)
            return True
            
        except Exception as e:
            logger.error(f"   ❌ Telegram Error ({category}): {e}")
            return False

    async def run(self):
        logger.info("🚀 Starting News Poster Bot (Single Run)...")
        
        async with aiohttp.ClientSession() as session:
            for category, sources in HTML_SOURCES.items():
                
                # Получаем ID канала
                channel_id = CHANNEL_IDS.get(category)
                if not channel_id:
                    logger.debug(f"Skipping category {category}: No Channel ID configured.")
                    continue
                
                logger.info(f"--- 📂 Category: {category} ---")
                
                for source in sources:
                    logger.info(f"🔍 Scanning source: {source['name']}")
                    
                    # Получаем свежие ссылки
                    links = await self.get_article_links(session, source)
                    
                    if not links:
      
