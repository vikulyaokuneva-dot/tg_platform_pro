import asyncio
import json
import logging
import os
import re
import sqlite3
from datetime import datetime
from html import escape
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import aiohttp
from bs4 import BeautifulSoup

from config import (
    BOT_TOKEN,
    GIGACHAT_API_KEY,
    GIGACHAT_MODEL,
    HTTP_TIMEOUT,
    MAX_LINKS_PER_SOURCE,
    SOURCES,
    CHANNEL_IDS,
    CHANNEL_BASE_HASHTAGS,
    CHANNEL_META,
)

# =========================
# Logging
# =========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

DB_PATH = os.getenv("SQLITE_PATH", "data/bot_cache.sqlite3")


# =========================
# SQLite cache
# =========================
class CacheDB:
    def __init__(self, path: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS posted (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel TEXT NOT NULL,
                url TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_posted_channel_url ON posted(channel, url)")
        self.conn.commit()

    def url_exists(self, channel: str, url: str) -> bool:
        cur = self.conn.execute(
            "SELECT 1 FROM posted WHERE channel = ? AND url = ? LIMIT 1",
            (channel, url),
        )
        return cur.fetchone() is not None

    def mark_posted(self, channel: str, url: str):
        self.conn.execute(
            "INSERT INTO posted(channel, url, created_at) VALUES (?, ?, ?)",
            (channel, url, datetime.utcnow().isoformat()),
        )
        self.conn.commit()


# =========================
# Telegram sender (HTTP API)
# =========================
async def tg_send_message(session: aiohttp.ClientSession, chat_id: str, html_text: str) -> bool:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": html_text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    try:
        async with session.post(url, json=payload, timeout=HTTP_TIMEOUT) as r:
            data = await r.json(content_type=None)
            if r.status == 200 and data.get("ok"):
                return True
            logger.warning(f"Telegram sendMessage failed: status={r.status}, resp={data}")
            return False
    except Exception as e:
        logger.error(f"Telegram sendMessage error: {e}")
        return False


# =========================
# Helpers
# =========================
def normalize_url(u: str) -> str:
    return (u or "").strip()

def uniq_keep_order(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for x in items:
        if not x:
            continue
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out

def short_source_line(article_url: str) -> str:
    try:
        d = urlparse(article_url).netloc.replace("www.", "")
    except Exception:
        d = "source"
    return f"Источник: {escape(d)}"

def merge_hashtags(category: str, gigachat_tags: Any) -> List[str]:
    tags: List[str] = []
    base = CHANNEL_BASE_HASHTAGS.get(category, [])
    if isinstance(base, list):
        tags.extend([t for t in base if isinstance(t, str)])

    if isinstance(gigachat_tags, list):
        tags.extend([t for t in gigachat_tags if isinstance(t, str)])

    # чистка + уникализация
    cleaned = []
    seen = set()
    for t in tags:
        t = t.strip()
        if not t:
            continue
        if not t.startswith("#"):
            t = "#" + t
        if t.lower() in seen:
            continue
        seen.add(t.lower())
        cleaned.append(t)

    # добавим бренд-тег (уникальный на канал)
    meta = CHANNEL_META.get(category, {})
    brand = meta.get("brand_tag")
    if isinstance(brand, str) and brand.strip():
        b = brand.strip()
        if not b.startswith("#"):
            b = "#" + b
        if b.lower() not in seen:
            cleaned.append(b)

    return cleaned


def build_post_text(post: Dict[str, Any], category: str, article_url: str) -> str:
    """
    Превращаем результат ai_writer.generate_post() в текст.
    Ожидаем: title, summary, hashtags(list)
    + добавляем: emoji, бренд-тег, базовые хэштеги, компактный источник.
    """
    meta = CHANNEL_META.get(category, {})
    title_emoji = (meta.get("title_emoji") or "").strip()

    title = (post.get("title") or "").strip()
    summary = (post.get("summary") or "").strip()
    hashtags = merge_hashtags(category, post.get("hashtags"))

    parts: List[str] = []

    if title:
        if title_emoji:
            parts.append(f"<b>{escape(title_emoji)} {escape(title)}</b>")
        else:
            parts.append(f"<b>{escape(title)}</b>")

    if summary:
        parts.append(escape(summary))

    if hashtags:
        parts.append(escape(" ".join(hashtags)))

    # компактная строка источника (без огромной голой ссылки)
    parts.append(short_source_line(article_url))

    return "\n\n".join([p for p in parts if p]).strip()


def fallback_post_from_text(text: str, category: str, article_url: str, title_hint: str = "") -> Dict[str, Any]:
    """
    Если GigaChat умер — делаем аккуратный "ручной" пост.
    """
    meta = CHANNEL_META.get(category, {})
    emoji = (meta.get("title_emoji") or "").strip()

    # берём первые 600-900 символов текста
    plain = re.sub(r"\s+", " ", (text or "").strip())
    summary = plain[:850].strip()
    if len(plain) > 850:
        summary += "…"

    title = title_hint.strip() or "Свежий материал"
    if emoji and not title.startswith(emoji):
        title = f"{emoji} {title}"

    return {
        "title": title,
        "summary": summary,
        "hashtags": merge_hashtags(category, []),
        "url": article_url,
    }


# =========================
# Fetching links (HTML/RSS)
# =========================
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
}

async def fetch_text(session: aiohttp.ClientSession, url: str) -> Optional[str]:
    try:
        async with session.get(url, headers=DEFAULT_HEADERS, timeout=HTTP_TIMEOUT) as r:
            if r.status != 200:
                logger.warning(f"HTTP {r.status} for {url}")
                return None
            return await r.text()
    except asyncio.TimeoutError:
        logger.error(f"Timeout fetching {url}")
        return None
    except Exception as e:
        logger.error(f"Error fetching {url}: {e}")
        return None


async def get_links_from_source(session: aiohttp.ClientSession, source: Dict[str, Any]) -> List[str]:
    url = source["url"]
    link_selector = source["link_selector"]
    base_url = source.get("base_url") or url

    raw = await fetch_text(session, url)
    if not raw:
        return []

    soup = BeautifulSoup(raw, "xml" if source.get("type") == "rss" else "html.parser")

    links: List[str] = []
    for el in soup.select(link_selector):
        # RSS: <link>text</link>
        if el.name == "link" and el.get_text(strip=True):
            links.append(el.get_text(strip=True))
            continue

        href = el.get("href")
        if not href:
            continue
        href = href.strip()

        # относительные -> абсолютные
        if href.startswith("/"):
            href = urljoin(base_url, href)

        links.append(href)

    links = uniq_keep_order(links)

    # ограничение
    return links[:MAX_LINKS_PER_SOURCE]


# =========================
# Article text extraction (simple)
# =========================
def extract_title_and_text(html: str) -> (str, str):
    soup = BeautifulSoup(html, "html.parser")

    title = ""
    if soup.title and soup.title.get_text(strip=True):
        title = soup.title.get_text(strip=True)

    # максимально простой "текст"
    # (это не идеально, но достаточно как fallback)
    text = soup.get_text("\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return title, text


# =========================
# GigaChat integration (через ваш ai_writer.py)
# =========================
# где-то рядом с импортами/глобально:
from ai_writer import AIWriter

_AI: AIWriter | None = None

def generate_post_with_ai(article_text: str, category: str) -> dict:
    """
    Корректный вызов AIWriter.
    """
    global _AI
    if _AI is None:
        _AI = AIWriter(api_key=GIGACHAT_API_KEY, model_name=GIGACHAT_MODEL)

    try:
        return _AI.generate_post(article_text, category)
    except Exception as e:
        logger.error(f"AIWriter.generate_post error: {e}")
        return {}

    try:
        # предполагаем, что у вас функция называется generate_post(text)
        return ai_writer.generate_post(article_text)  # type: ignore
    except Exception as e:
        logger.error(f"ai_writer.generate_post error: {e}")
        return {}


# =========================
# Main runner
# =========================
class Runner:
    def __init__(self):
        self.db = CacheDB(DB_PATH)

async def process_one_article(
    self,
    session: aiohttp.ClientSession,
    category: str,
    channel_id: str,
    article_url: str,
) -> bool:
    article_url = normalize_url(article_url)
    if not article_url:
        return False

    if self.db.url_exists(category, article_url):
        return False

    logger.info(f"⚡ Processing new article: {article_url}")

    # --- 1. Загружаем HTML ---
    html = await fetch_text(session, article_url)
    if not html:
        return False

    # --- 2. Извлекаем текст ---
    title_hint, text = extract_title_and_text(html)
    if not text or len(text.strip()) < 50:
        logger.warning(f"Skipping {article_url}: empty article text")
        return False

    # --- 3. Генерация поста ---
    if category == "ANEKDOTY":
        # анекдоты всегда без ИИ
        post = fallback_post_from_text(
            text=text,
            category=category,
            article_url=article_url,
            title_hint="Анекдот дня",
        )
    else:
        logger.info("   🤖 Generating post with GigaChat...")
        post = generate_post_with_ai(text, category) or {}

        # fallback если ИИ вернул мусор
        if not post.get("title") or not post.get("summary"):
            post = fallback_post_from_text(
                text=text,
                category=category,
                article_url=article_url,
                title_hint=title_hint,
            )

    # --- 4. Собираем текст ---
    html_text = build_post_text(post, category, article_url)

    # --- 5. Отправляем ---
    ok = await tg_send_message(session, channel_id, html_text)
    if ok:
        self.db.mark_posted(category, article_url)
        logger.info(f"   ✅ SUCCESS: Posted to {category}")
        return True

    return False


    async def run(self):
        logger.info("Starting single run (all channels)")

        async with aiohttp.ClientSession() as session:
            for category, channel_id in CHANNEL_IDS.items():
                try:
                    if not channel_id:
                        logger.info(f"Skip {category}: no CHAT_ID")
                        continue

                    logger.info(f"=== Channel {category} ===")

                    sources = SOURCES.get(category, [])
                    if not sources:
                        logger.info(f"Skip {category}: no sources")
                        continue

                    posted_any = False

                    for source in sources:
                        logger.info(f"Scanning source: {source.get('name','(no name)')}")
                        links = await get_links_from_source(session, source)

                        if not links:
                            continue

                        # ищем первую НЕ posted ссылку
                        for link in links:
                            if self.db.url_exists(category, link):
                                continue
                            ok = await self.process_one_article(session, category, channel_id, link)
                            if ok:
                                posted_any = True
                                break

                        if posted_any:
                            break

                    if not posted_any:
                        logger.info(f"No fresh new posts for {category}")

                except Exception as e:
                    # критично: ошибки не роняют процесс
                    logger.error(f"Channel {category} failed: {e}")

        logger.info("Job finished successfully.")


if __name__ == "__main__":
    runner = Runner()
    asyncio.run(runner.run())
