import sqlite3
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


logger = logging.getLogger(__name__)


@dataclass
class PublicationResult:
    status: str
    error: Optional[str] = None
    tg_message_id: Optional[int] = None


class PlatformDB:
    """SQLite-хранилище для продакшн-автопостинга."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        # check_same_thread=False — чтобы было безопаснее при возможных будущих to_thread
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self.conn:
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS articles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL UNIQUE,
                    title_raw TEXT,
                    published_at TEXT,
                    lang TEXT,
                    image_url TEXT,
                    extracted_text TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS publications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_key TEXT NOT NULL,
                    url TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error TEXT,
                    tg_message_id INTEGER,
                    posted_at TEXT NOT NULL,
                    UNIQUE(channel_key, url)
                )
                """
            )
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_pub_channel_status ON publications(channel_key, status)")

    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def is_published(self, channel_key: str, url: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM publications WHERE channel_key = ? AND url = ? LIMIT 1",
            (channel_key, url),
        ).fetchone()
        return row is not None

    def upsert_article(
        self,
        url: str,
        title_raw: Optional[str] = None,
        published_at: Optional[str] = None,
        lang: Optional[str] = None,
        image_url: Optional[str] = None,
        extracted_text: Optional[str] = None,
    ) -> None:
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO articles (url, title_raw, published_at, lang, image_url, extracted_text, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    title_raw=COALESCE(excluded.title_raw, articles.title_raw),
                    published_at=COALESCE(excluded.published_at, articles.published_at),
                    lang=COALESCE(excluded.lang, articles.lang),
                    image_url=COALESCE(excluded.image_url, articles.image_url),
                    extracted_text=COALESCE(excluded.extracted_text, articles.extracted_text)
                """,
                (url, title_raw, published_at, lang, image_url, extracted_text, self._now_iso()),
            )

    def record_publication(
        self,
        channel_key: str,
        url: str,
        result: PublicationResult,
    ) -> None:
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO publications (channel_key, url, status, error, tg_message_id, posted_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(channel_key, url) DO UPDATE SET
                    status=excluded.status,
                    error=excluded.error,
                    tg_message_id=COALESCE(excluded.tg_message_id, publications.tg_message_id),
                    posted_at=excluded.posted_at
                """,
                (
                    channel_key,
                    url,
                    result.status,
                    result.error,
                    result.tg_message_id,
                    self._now_iso(),
                ),
            )
