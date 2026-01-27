import asyncio
import logging
import os
import sys
import sqlite3
from html import escape
from urllib.parse import urljoin

import aiohttp
from aiogram import Bot
from aiogram.enums import ParseMode
from bs4 import BeautifulSoup
import trafilatura

# ------------------------------------------------------------
# 0) Чтобы локальные импорты работали в GitHub Actions
# ------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# ------------------------------------------------------------
# 1) Импорт ваших модулей (без database.py / bot_database.py)
# ------------------------------------------------------------
try:
    from config import CHANNEL_IDS, HTML_SOURCES, HEADERS
except ImportError as e:
    print(f"CRITICAL ERROR: Import failed. Make sure config.py exists. Details: {e}")
    sys.exit(1)

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
# 4) Встроенная база (чтобы не зависеть от database.py)
# ------------------------------------------------------------
class Database:
    def __init__(self, db_file: str = "bot_database.db"):
        self.connection = sqlite3.connect(db_file)
        self.cursor = self.connection.cursor()
        self._create_table()

    def _create_table(self) -> None:
        with self.connection:
            self.cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS posted_urls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT UNIQUE NOT NULL,
                    category TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def url_exists(self, url: str) -> bool:
        with self.connection:
            row = self.cursor.execute(
                "SELECT id FROM posted_urls WHERE url = ?",
                (url,),
            ).fetchone()
            return bool(row)

    def add_url(self, url: str, category: str) -> bool:
        try:
            with self.connection:
                self.cursor.execute(
                    "INSERT INTO posted_urls (url, category) VALUES (?, ?)",
                    (url, category),
                )
            return True
        except sqlite3.IntegrityError:
            return False
        except Exception as e:
            logger.error(f"Database error: {e}")
            return False

    def close(self) -> None:
        self.connection.close()


# ------------------------------------------------------------
# 5) Утилиты: картинка превью + аккуратные ограничения длины
# ------------------------------------------------------------
def extract_preview_image_url(html: str, page_url: str) -> str | None:
    """
    Пытаемся достать картинку статьи:
      1) og:image:secure_url
      2) og:image
      3) twitter:image
      4) fallback: первая <img>
    """
    try:
        soup = BeautifulSoup(html, "html.parser")

        def meta(attr_name: str, attr_value: str) -> str | None:
            m = soup.find("meta", attrs={attr_name: attr_value})
            if m and m.get("content"):
                return str(m.get("content")).strip()
            return None

        candidates = [
            meta("property", "og:image:secure_url"),
            meta("property", "og:image"),
            meta("name", "twitter:image"),
        ]

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
    return s[: max(0, limit - 1)].rstrip() + "…"


def build_post_text(post: dict) -> str:
    """
    Превращаем результат ai_writer.generate_post() в текст.
    Ожидаем: title, summary, hashtags(list)
    """
    title = (post.get("title") or "").strip()
    summary = (post.get("summary") or "").strip()
    hashtags = post.get("hashtags") or []
    if not isinstance(hashtags, list):
        hashtags = []

    tags = " ".join([t.strip() for t in hashtags if isinstance(t, str) and t.strip()])
    parts = []
    if title:
        parts.append(f"<b>{escape(title)}</b>")
    if summary:
        parts.append(escape(summary))
    if tags:
        parts.append(escape(tags))
    return "\n\n".join(parts).strip()


# ------------------------------------------------------------
# 6) Основной класс
# ------------------------------------------------------------
class NewsPoster:
    def __init__(self) -> None:
        if not BOT_TOKEN:
            logger.critical("POSTER_BOT_TOKEN is missing in env vars! Exiting.")
            sys.exit(1)

        self.bot = Bot(token=BOT_TOKEN)
        self.db = Database("bot_database.db")

        self.ai = AIWriter(GIGACHAT_KEY)
        if not GIGACHAT_KEY:
            logger.warning("GIGACHAT_API_KEY not found. AI generation is DISABLED.")

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

        links: list[str] = []
        for el in elements:
            href = el.get("href")
            if not href:
                continue
            base_url = source_conf.get("base_url", source_conf["url"])
            links.append(urljoin(base_url, href))

        return list(dict.fromkeys(links))[:5]

    async def process_article(self, session: aiohttp.ClientSession, link: str, category: str, channel_id: str) -> bool:
        if self.db.url_exists(link):
            return False

        logger.info(f"⚡ Processing new article: {link}")

        html = await self.fetch_html(session, link)
        if not html:
            return False

        image_url = extract_preview_image_url(html, link)

        try:
            article_text = trafilatura.extract(
                html,
                include_comments=False,
                include_tables=False,
                no_fallback=True,
            )
        except Exception as e:
            logger.error(f"Trafilatura error on {link}: {e}")
            article_text = None

        if not article_text or len(article_text) < 100:
            logger.warning(f"Skipping {link}: Content too short or extraction failed.")
            return False

        # Генерация поста (синхронная) — чтобы не блокировать event loop, делаем в отдельном потоке
        logger.info("   🤖 Generating post with GigaChat...")
        post = await asyncio.to_thread(self.ai.generate_post, article_text, category)

        text_body = build_post_text(post)

        # маленькая ссылка (без огромной карточки)
        source_line = f"Источник: <a href='{link}'>читать</a>"

        try:
            # --- если есть картинка -> фото сверху ---
            if image_url:
                # caption максимум 1024 символа
                caption_limit = 1024
                reserved = len("\n\n" + source_line)
                body_limit = max(0, caption_limit - reserved)

                caption_body = trim_text(text_body, body_limit)
                caption = f"{caption_body}\n\n{source_line}".strip()

                await self.bot.send_photo(
                    chat_id=channel_id,
                    photo=image_url,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                )

                # если текст большой — докидываем хвост вторым сообщением (без превью)
                if len(text_body) > body_limit:
                    tail = text_body[body_limit:].strip()
                    if tail:
                        await self.bot.send_message(
                            chat_id=channel_id,
                            text=tail,
                            parse_mode=ParseMode.HTML,
                            disable_web_page_preview=True,
                        )
            else:
                # --- картинки нет -> обычное сообщение, но без превью ---
                message = f"{text_body}\n\n{source_line}".strip()
                await self.bot.send_message(
                    chat_id=channel_id,
                    text=message,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )

            logger.info(f"   ✅ SUCCESS: Posted to {category}")
            self.db.add_url(link, category)
            return True

        except Exception as e:
            logger.error(f"   ❌ Telegram Error ({category}): {e}")
            return False

    async def run(self) -> None:
        logger.info("Starting single run (all channels)")

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

                posted = False
                for source in sources:
                    logger.info(f"Scanning source: {source['name']}")
                    links = await self.get_article_links(session, source)
                    if not links:
                        continue

                    for link in links:
                        ok = await self.process_article(session, link, category, channel_id)
                        if ok:
                            posted = True
                            break

                    if posted:
                        break

                if not posted:
                    logger.info(f"No fresh new posts for {category}")

        await self.bot.session.close()
        self.db.close()
        logger.info("Job finished successfully.")


if __name__ == "__main__":
    poster = NewsPoster()
    try:
        asyncio.run(poster.run())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped manually.")
