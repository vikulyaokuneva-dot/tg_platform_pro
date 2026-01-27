import asyncio
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html import escape
from typing import List, Optional, Tuple
from urllib.parse import urljoin

import aiohttp
from aiogram import Bot
from aiogram.enums import ParseMode
from bs4 import BeautifulSoup
from dateutil import parser as dtparser
import trafilatura

from config import (
    BOT_TOKEN,
    GIGACHAT_API_KEY,
    CHANNEL_IDS,
    HTML_SOURCES,
    HEADERS,
    CHANNEL_BASE_HASHTAGS,
)
from ai_writer import AIWriter
from platform_db import PlatformDB, PublicationResult


# --- НАСТРОЙКИ ---
DB_PATH = os.getenv("PLATFORM_DB_PATH", "data/bot.db")
FRESH_TTL_HOURS = int(os.getenv("FRESH_TTL_HOURS", "12"))
MAX_LINKS_PER_SOURCE = int(os.getenv("MAX_LINKS_PER_SOURCE", "30"))


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@dataclass
class ArticleData:
    url: str
    title_raw: Optional[str]
    published_at: Optional[datetime]
    image_url: Optional[str]
    text: str
    lang: str


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _is_english(text: str) -> bool:
    if not text:
        return False
    # грубо: если кириллицы мало, считаем EN
    cyr = len(re.findall(r"[А-Яа-яЁё]", text))
    lat = len(re.findall(r"[A-Za-z]", text))
    return lat > max(50, cyr * 2)


def _parse_datetime(value: str) -> Optional[datetime]:
    try:
        dt = dtparser.parse(value)
        if dt.tzinfo is None:
            # если TZ нет — считаем UTC
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _extract_published_at(soup: BeautifulSoup) -> Optional[datetime]:
    # 1) meta-теги
    meta_props = [
        ("property", "article:published_time"),
        ("property", "og:published_time"),
        ("name", "article:published_time"),
        ("name", "pubdate"),
        ("name", "publishdate"),
        ("name", "date"),
        ("itemprop", "datePublished"),
    ]
    for attr, key in meta_props:
        tag = soup.find("meta", attrs={attr: key})
        if tag and tag.get("content"):
            dt = _parse_datetime(tag["content"])
            if dt:
                return dt

    # 2) <time datetime="...">
    time_tag = soup.find("time")
    if time_tag and time_tag.get("datetime"):
        dt = _parse_datetime(time_tag["datetime"])
        if dt:
            return dt

    # 3) JSON-LD (часто NewsArticle)
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = (script.string or "").strip()
        if not raw:
            continue
        # JSON-LD может быть массивом/объектом
        try:
            import json

            data = json.loads(raw)
            candidates = data if isinstance(data, list) else [data]
            for obj in candidates:
                if not isinstance(obj, dict):
                    continue
                for k in ("datePublished", "dateCreated", "uploadDate"):
                    if k in obj and isinstance(obj[k], str):
                        dt = _parse_datetime(obj[k])
                        if dt:
                            return dt
        except Exception:
            continue

    return None


def _extract_og_image(soup: BeautifulSoup, base_url: str) -> Optional[str]:
    tag = soup.find("meta", attrs={"property": "og:image"})
    if tag and tag.get("content"):
        return urljoin(base_url, tag["content"].strip())
    tag = soup.find("meta", attrs={"name": "og:image"})
    if tag and tag.get("content"):
        return urljoin(base_url, tag["content"].strip())
    # fallback: первая картинка
    img = soup.find("img")
    if img and img.get("src"):
        return urljoin(base_url, img["src"].strip())
    return None


def _make_message(title: str, summary: str, hashtags: List[str], source_url: str) -> str:
    tags_line = " ".join(hashtags).strip()
    if tags_line:
        tags_line = "\n\n" + escape(tags_line)
    return (
        f"<b>{escape(title)}</b>\n\n"
        f"{escape(summary)}"
        f"{tags_line}\n\n"
        f"Источник: <a href='{escape(source_url)}'>ссылка</a>"
    )


class NewsPoster:
    def __init__(self):
        if not BOT_TOKEN:
            raise RuntimeError("POSTER_BOT_TOKEN is missing")

        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

        self.bot = Bot(token=BOT_TOKEN)
        self.db = PlatformDB(DB_PATH)
        self.ai = AIWriter(GIGACHAT_API_KEY)
        self.ttl = timedelta(hours=FRESH_TTL_HOURS)

    async def close(self):
        try:
            await self.bot.session.close()
        except Exception:
            pass
        self.db.close()

    async def fetch_html(self, session: aiohttp.ClientSession, url: str) -> Optional[str]:
        for attempt in range(2):
            try:
                async with session.get(url, headers=HEADERS, timeout=25) as resp:
                    if resp.status == 200:
                        return await resp.text()
                    logger.warning(f"HTTP {resp.status} for {url}")
                    return None
            except asyncio.TimeoutError:
                logger.warning(f"Timeout fetching {url} (attempt {attempt + 1})")
            except Exception as e:
                logger.warning(f"Fetch error {url}: {e} (attempt {attempt + 1})")
            await asyncio.sleep(1)
        return None

    async def get_links(self, session: aiohttp.ClientSession, source_conf: dict) -> List[str]:
        html = await self.fetch_html(session, source_conf["url"])
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        try:
            elements = soup.select(source_conf["link_selector"])
        except Exception as e:
            logger.error(f"Bad selector for {source_conf.get('name')}: {e}")
            return []

        links: List[str] = []
        base_url = source_conf.get("base_url", source_conf["url"])
        for el in elements:
            href = el.get("href")
            if not href:
                continue
            links.append(urljoin(base_url, href))

        # уникально, сохраняя порядок
        uniq = list(dict.fromkeys(links))
        return uniq[:MAX_LINKS_PER_SOURCE]

    async def parse_article(self, session: aiohttp.ClientSession, url: str) -> Optional[ArticleData]:
        html = await self.fetch_html(session, url)
        if not html:
            return None

        soup = BeautifulSoup(html, "html.parser")
        published_at = _extract_published_at(soup)
        image_url = _extract_og_image(soup, url)
        title_raw = None
        if soup.title and soup.title.string:
            title_raw = soup.title.string.strip()[:200]

        try:
            text = trafilatura.extract(
                html,
                include_comments=False,
                include_tables=False,
                no_fallback=True,
                url=url,
            )
        except Exception:
            text = None

        if not text or len(text.strip()) < 200:
            return None

        lang = "en" if _is_english(text) else "ru"
        return ArticleData(
            url=url,
            title_raw=title_raw,
            published_at=published_at,
            image_url=image_url,
            text=text.strip(),
            lang=lang,
        )

    def is_fresh(self, published_at: Optional[datetime]) -> bool:
        # Если дата неизвестна — не режем по TTL (но всё равно ограничиваем top-N на уровне ссылок)
        if not published_at:
            return True
        return (_now_utc() - published_at) <= self.ttl

    async def publish(self, channel_key: str, channel_id: str, article: ArticleData) -> PublicationResult:
        # AI генерация (в thread, чтобы не блокировать event loop)
        post = await asyncio.to_thread(self.ai.generate_post, article.text, channel_key)
        title = str(post.get("title", "")) or (article.title_raw or "Коротко о главном")
        summary = str(post.get("summary", "")) or article.text[:900]
        hashtags = list(post.get("hashtags", []) or [])

        # добавляем базовые хэштеги канала
        base_tags = CHANNEL_BASE_HASHTAGS.get(channel_key, [])
        merged = list(dict.fromkeys(base_tags + hashtags))
        merged = merged[:15]

        msg = _make_message(title, summary, merged, article.url)

        # Telegram ограничения: caption у photo ограничен (часто 1024)
        async def _send_message_only():
            sent = await self.bot.send_message(
                chat_id=channel_id,
                text=msg,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=False,
            )
            return sent

        try:
            if article.image_url:
                caption = msg
                if len(caption) > 1000:
                    caption = caption[:990] + "…"
                sent = await self.bot.send_photo(
                    chat_id=channel_id,
                    photo=article.image_url,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                )
            else:
                sent = await _send_message_only()

            return PublicationResult(status="POSTED", tg_message_id=getattr(sent, "message_id", None))
        except Exception as e:
            # fallback: если фото не прошло — пробуем текстом
            if article.image_url:
                try:
                    sent = await _send_message_only()
                    return PublicationResult(status="POSTED", tg_message_id=getattr(sent, "message_id", None))
                except Exception as e2:
                    return PublicationResult(status="TG_FAIL", error=str(e2))
            return PublicationResult(status="TG_FAIL", error=str(e))

    async def process_channel(self, session: aiohttp.ClientSession, channel_key: str) -> None:
        channel_id = CHANNEL_IDS.get(channel_key)
        if not channel_id:
            logger.info(f"Skip {channel_key}: no CHANNEL_IDS entry")
            return

        sources = HTML_SOURCES.get(channel_key) or []
        if not sources:
            logger.info(f"Skip {channel_key}: no sources")
            return

        logger.info(f"=== Channel {channel_key} ===")

        # Требование: 1 пост за запуск
        posted = False

        for source in sources:
            if posted:
                break
            try:
                logger.info(f"Scanning source: {source.get('name', source.get('url'))}")
                links = await self.get_links(session, source)
                if not links:
                    continue

                for url in links:
                    if posted:
                        break
                    if self.db.is_published(channel_key, url):
                        continue

                    try:
                        article = await self.parse_article(session, url)
                        if not article:
                            self.db.record_publication(channel_key, url, PublicationResult(status="PARSE_FAIL"))
                            continue

                        if not self.is_fresh(article.published_at):
                            # отмечать не будем как публикацию, чтобы не блокировать навсегда (вдруг на сайте кривая дата)
                            continue

                        # сохраняем статью (для дебага и метрик)
                        self.db.upsert_article(
                            url=url,
                            title_raw=article.title_raw,
                            published_at=article.published_at.isoformat() if article.published_at else None,
                            lang=article.lang,
                            image_url=article.image_url,
                            extracted_text=article.text[:20000],
                        )

                        result = await self.publish(channel_key, channel_id, article)
                        self.db.record_publication(channel_key, url, result)

                        if result.status == "POSTED":
                            logger.info(f"Posted for {channel_key}: {url}")
                            posted = True
                            # небольшая пауза, чтобы не спамить Telegram API
                            await asyncio.sleep(2)
                        else:
                            logger.warning(f"Publish failed {channel_key}: {result.error}")
                    except Exception as e:
                        logger.error(f"Error processing url {url} in {channel_key}: {e}")
                        self.db.record_publication(channel_key, url, PublicationResult(status="PROCESS_FAIL", error=str(e)))
                        continue

            except Exception as e:
                logger.error(f"Source error in {channel_key}: {e}")
                continue

        if not posted:
            logger.info(f"No fresh new posts for {channel_key}")

    async def run(self) -> None:
        logger.info("Starting single run (all channels)")
        async with aiohttp.ClientSession() as session:
            for channel_key in HTML_SOURCES.keys():
                try:
                    await self.process_channel(session, channel_key)
                except Exception as e:
                    logger.error(f"Channel crash {channel_key}: {e}")
                    continue


async def main():
    poster = NewsPoster()
    try:
        await poster.run()
    finally:
        await poster.close()


if __name__ == "__main__":
    asyncio.run(main())
