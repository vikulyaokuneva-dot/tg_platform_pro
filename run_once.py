import asyncio
import logging
import os
import sys
from html import escape
from urllib.parse import urljoin

import aiohttp
from aiogram import Bot
from aiogram.enums import ParseMode
from bs4 import BeautifulSoup
import trafilatura

# ------------------------------------------------------------
# 0) Гарантируем, что импорт локальных файлов работает в GitHub Actions
# ------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# ------------------------------------------------------------
# 1) Импорты ваших модулей (без DATABASE_FILE — его нет в config.py)
# ------------------------------------------------------------
try:
    from config import CHANNEL_IDS, HTML_SOURCES, HEADERS
except ImportError as e:
    print(f"CRITICAL ERROR: Import failed. Make sure config.py exists. Details: {e}")
    sys.exit(1)

# Database: у кого-то файл называется bot_database.py, у кого-то database.py
try:
    from bot_database import Database
except ImportError:
    from database import Database  # type: ignore

try:
    from ai_writer import AIWriter
except ImportError as e:
    print(f"CRITICAL ERROR: Import failed. Make sure ai_writer.py exists. Details: {e}")
    sys.exit(1)

# ------------------------------------------------------------
# 2) Логирование
# ------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ------------------------------------------------------------
# 3) Секреты
# ------------------------------------------------------------
BOT_TOKEN = os.getenv("POSTER_BOT_TOKEN")
GIGACHAT_KEY = os.getenv("GIGACHAT_API_KEY")


# ------------------------------------------------------------
# 4) Утилиты: картинка превью + безопасные ограничения длины
# ------------------------------------------------------------
def extract_preview_image_url(html: str, page_url: str) -> str | None:
    """
    Достаём картинку для send_photo:
    - og:image / og:image:secure_url
    - twitter:image
    - fallback: первая <img>
    """
    try:
        soup = BeautifulSoup(html, "html.parser")

        def pick_meta(attr_name: str, attr_value: str) -> str | None:
            m = soup.find("meta", attrs={attr_name: attr_value})
            if m and m.get("content"):
                return str(m.get("content")).strip()
            return None

        candidates = [
            pick_meta("property", "og:image:secure_url"),
            pick_meta("property", "og:image"),
            pick_meta("name", "twitter:image"),
        ]

        # fallback: первая картинка
        img = soup.find("img")
        if img and img.get("src"):
            candidates.append(str(img.get("src")).strip())

        for c in candidates:
            if not c:
                continue
            if c.startswith("data:"):
                continue
            return urljoin(page_url, c)

        return None
    except Exception:
        return None


def trim_text(s: str, limit: int) -> str:
    s = (s or "").strip()
    if len(s) <= limit:
        return s
    # чтобы не резать “впритык”
    return s[: max(0, limit - 1)].rstrip() + "…"


# ------------------------------------------------------------
# 5) Основной класс
# ------------------------------------------------------------
class NewsPoster:
    def __init__(self) -> None:
        if not BOT_TOKEN:
            logger.critical("POSTER_BOT_TOKEN is missing in env vars! Exiting.")
            sys.exit(1)

        self.bot = Bot(token=BOT_TOKEN)

        # SQLite файл как и раньше
        self.db = Database("bot_database.db")

        # AI
        self.ai = AIWriter(GIGACHAT_KEY)
        if not GIGACHAT_KEY:
            logger.warning("GIGACHAT_API_KEY not found. AI summarization is DISABLED.")

    async def fetch_html(self, session: aiohttp.ClientSession, url: str) -> str | None:
        try:
            async with session.get(url, headers=HEADERS, timeout=20) as response:
                if response.status == 200:
                    return await response.text()
                logger.warning(f"HTTP {response.status} for {url}")
                return None
        except asyncio.TimeoutError:
            logger.error(f"Timeout fetching {url}")
            return None
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            return None

    async def get_article_links(self, session: aiohttp.ClientSession, source_conf: dict) -> list[str]:
        html = await self.fetch_html(session, source_conf["url"])
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")

        try:
            elements = soup.select(source_conf["link_selector"])
        except Exception as e:
            logger.error(f"Invalid selector for {source_conf.get('name', 'unknown')}: {e}")
            return []

        logger.info(f"Source {source_conf['name']}: Found {len(elements)} raw elements")

        links: list[str] = []
        for el in elements:
            href = el.get("href")
            if not href:
                continue

            base_url = source_conf.get("base_url", source_conf["url"])
            full_link = urljoin(base_url, href)
            links.append(full_link)

        # Берём первые 5 уникальных
        return list(dict.fromkeys(links))[:5]

    async def process_article(self, session: aiohttp.ClientSession, link: str, category: str, channel_id: str) -> bool:
        if self.db.url_exists(link):
            return False

        logger.info(f"⚡ Processing new article: {link}")

        html = await self.fetch_html(session, link)
        if not html:
            return False

        # 1) картинка для поста сверху
        image_url = extract_preview_image_url(html, link)

        # 2) извлекаем текст статьи
        try:
            downloaded_text = trafilatura.extract(
                html,
                include_comments=False,
                include_tables=False,
                no_fallback=True,
            )
        except Exception as e:
            logger.error(f"Trafilatura error on {link}: {e}")
            downloaded_text = None

        if not downloaded_text or len(downloaded_text) < 100:
            logger.warning(f"Skipping {link}: Content too short or extraction failed.")
            return False

        # 3) генерим пост
        logger.info("   🤖 Asking GigaChat to summarize...")
        ai_text = await self.ai.summarize(downloaded_text, category)
        ai_text = (ai_text or "").strip()

        # 4) делаем маленькую ссылку (без огромной карточки)
        source_line = f"Источник: <a href='{link}'>читать</a>"

        # Экранируем, чтобы HTML не ломался
        safe_text = escape(ai_text)

        try:
            # -----------------------------------------
            # Вариант А: есть картинка → фото сверху
            # -----------------------------------------
            if image_url:
                # В Telegram caption у фото максимум 1024 символа.
                # Чтобы НЕ было “обрезано без конца” — делаем так:
                # 1) короткий caption под фото (до лимита),
                # 2) если текст длиннее — вторым сообщением отправим остаток (без превью).
                caption_limit = 1024
                reserved = len("\n\n" + source_line)
                body_limit = max(0, caption_limit - reserved)

                caption_body = trim_text(safe_text, body_limit)
                caption = f"{caption_body}\n\n{source_line}".strip()

                await self.bot.send_photo(
                    chat_id=channel_id,
                    photo=image_url,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                )

                # Если текст реально длинный — отправляем “хвост” вторым сообщением
                # (так вы не теряете конец поста).
                if len(safe_text) > body_limit:
                    tail = safe_text[body_limit:].strip()
                    if tail:
                        # хвост без ссылки, чтобы не дублировать
                        await self.bot.send_message(
                            chat_id=channel_id,
                            text=tail,
                            parse_mode=ParseMode.HTML,
                            disable_web_page_preview=True,
                        )

            # -----------------------------------------
            # Вариант B: картинки нет → просто сообщение
            # -----------------------------------------
            else:
                message = f"{safe_text}\n\n{source_line}".strip()
                await self.bot.send_message(
                    chat_id=channel_id,
                    text=message,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,  # ключевое: убираем большую карточку
                )

            logger.info(f"   ✅ SUCCESS: Posted to {category}")
            self.db.add_url(link, category)
            return True

        except Exception as e:
            logger.error(f"   ❌ Telegram Error ({category}): {e}")
            return False

    async def run(self) -> None:
        logger.info("🚀 Starting single run (all channels)")

        async with aiohttp.ClientSession() as session:
            for category, sources in HTML_SOURCES.items():
                channel_id = CHANNEL_IDS.get(category)

                if not channel_id:
                    logger.info(f"Skip {category}: no channel id")
                    continue

                logger.info(f"=== Channel {category} ===")

                if not sources:
                    logger.info(f"Skip {category}: no sources")
                    continue

                posted_any = False

                for source in sources:
                    logger.info(f"Scanning source: {source['name']}")
                    links = await self.get_article_links(session, source)

                    if not links:
                        continue

                    for link in links:
                        ok = await self.process_article(session, link, category, channel_id)
                        if ok:
                            posted_any = True
                            # Важно: один запуск = одна публикация на канал
                            break

                    if posted_any:
                        break

                if not posted_any:
                    logger.info(f"No fresh new posts for {category}")

        await self.bot.session.close()
        self.db.close()
        logger.info("🏁 Job finished successfully.")


if __name__ == "__main__":
    poster = NewsPoster()
    try:
        asyncio.run(poster.run())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped manually.")
