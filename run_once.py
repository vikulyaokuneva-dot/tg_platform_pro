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
BOT_TOKEN = os.getenv("POSTER_BOT_TOKEN")
GIGACHAT_KEY = os.getenv("GIGACHAT_API_KEY")

class NewsPoster:
    def __init__(self):
        if not BOT_TOKEN:
            logger.critical("POSTER_BOT_TOKEN is missing in env vars! Exiting.")
            sys.exit(1)
        
        self.bot = Bot(token=BOT_TOKEN)
        self.db = Database("bot_database.db")
        
        # Инициализация AI
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
            
            base_url = source_conf.get('base_url', source_conf['url'])
            full_link = urljoin(base_url, href)
            links.append(full_link)
        
        unique_links = list(dict.fromkeys(links))[:5]
        return unique_links

    async def process_article(self, session, link, category, channel_id):
        """Полный цикл: проверка -> скачивание -> AI -> постинг -> сохранение"""
        
        if self.db.url_exists(link):
            return False

        logger.info(f"⚡ Processing new article: {link}")
        
        html = await self.fetch_html(session, link)
        if not html:
            return False

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
            return False

        logger.info("   🤖 Asking GigaChat to summarize...")
        ai_summary = await self.ai.summarize(downloaded_text, category)
        
        safe_text = escape(ai_summary)
        
        message = (
            f"{safe_text}\n\n"
            f"🔗 <a href='{link}'>Читать оригинал</a>"
        )

        try:
            await self.bot.send_message(
                chat_id=channel_id,
                text=message,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=False 
            )
            logger.info(f"   ✅ SUCCESS: Posted to {category}")
            self.db.add_url(link, category)
            return True
            
        except Exception as e:
            logger.error(f"   ❌ Telegram Error ({category}): {e}")
            return False

    async def run(self):
        logger.info("🚀 Starting News Poster Bot (Single Run)...")
        
        async with aiohttp.ClientSession() as session:
            for category, sources in HTML_SOURCES.items():
                
                channel_id = CHANNEL_IDS.get(category)
                if not channel_id:
                    logger.debug(f"Skipping category {category}: No Channel ID configured.")
                    continue
                
                logger.info(f"--- 📂 Category: {category} ---")
                
                for source in sources:
                    logger.info(f"🔍 Scanning source: {source['name']}")
                    
                    links = await self.get_article_links(session, source)
                    
                    if not links:
                        logger.info(f"   No links found in {source['name']} (check selectors?)")
                        continue

                    new_posts_count = 0
                    for link in links:
                        is_posted = await self.process_article(session, link, category, channel_id)
                        
                        if is_posted:
                            new_posts_count += 1
                            await asyncio.sleep(8) 
                    
                    if new_posts_count == 0:
                        logger.info("   No new articles to post.")

        await self.bot.session.close()
        self.db.close()
        logger.info("🏁 Job finished successfully.")

if __name__ == "__main__":
    poster = NewsPoster()
    try:
        asyncio.run(poster.run())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped manually.")
