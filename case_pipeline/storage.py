# -*- coding: utf-8 -*-
"""case_pipeline.storage — единая SQLite: дедуп, материалы, кейсы, публикации.

Единственный путь к БД: config.DB_PATH (env CASE_DB_PATH) — и приложение, и
планировщик читают его из одного места (исторический баг data/bot.db vs
bot_database.db исключён: других путей в коде нет).

Статусы кандидата: new -> fetched -> extracted -> classified -> review /
accepted / rejected -> case_built -> post_ready -> published | failed.
"""
import json
import logging
import os
import sqlite3

from . import config
from .utils import content_hash, norm_url, now_iso

log = logging.getLogger("case_pipeline.storage")

SCHEMA = """
CREATE TABLE IF NOT EXISTS materials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    canonical_url TEXT NOT NULL UNIQUE,
    content_hash TEXT,
    source TEXT,
    status TEXT NOT NULL DEFAULT 'new',
    classification TEXT,
    confidence REAL,
    company TEXT,
    reason TEXT,
    case_json TEXT,
    post_text TEXT,
    telegram_message_id INTEGER,
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_materials_hash ON materials(content_hash);
CREATE INDEX IF NOT EXISTS idx_materials_status ON materials(status);
CREATE TABLE IF NOT EXISTS publications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    material_id INTEGER NOT NULL,
    case_id TEXT NOT NULL,
    source_url TEXT NOT NULL,
    telegram_message_id INTEGER,
    chat_id TEXT,
    published_at TEXT NOT NULL,
    ok INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    hashtags TEXT DEFAULT '',
    content_type TEXT DEFAULT 'case',
    company TEXT,
    canonical_url TEXT,
    content_hash TEXT,
    status TEXT DEFAULT 'ok'
);
"""

# мягкая миграция старых БД: недостающие колонки publication history
_PUB_COLS = (("hashtags", "TEXT DEFAULT ''"), ("content_type", "TEXT DEFAULT 'case'"),
             ("company", "TEXT"), ("canonical_url", "TEXT"),
             ("content_hash", "TEXT"), ("status", "TEXT DEFAULT 'ok'"))


class Storage:
    def __init__(self, path=None):
        path = path or config.DB_PATH
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self._migrate()
        self.db.commit()
        self.path = path

    def _migrate(self):
        cols = {r["name"] for r in self.db.execute("PRAGMA table_info(publications)")}
        for name, ddl in _PUB_COLS:
            if name not in cols:
                self.db.execute("ALTER TABLE publications ADD COLUMN %s %s" % (name, ddl))
        self.db.execute("UPDATE publications SET content_type='case' WHERE content_type IS NULL")

    # ---------- dedup ----------
    def seen_url(self, url):
        row = self.db.execute("SELECT id,status FROM materials WHERE canonical_url=?",
                              (norm_url(url),)).fetchone()
        return dict(row) if row else None

    def seen_hash(self, h):
        row = self.db.execute("SELECT id FROM materials WHERE content_hash=? LIMIT 1",
                              (h,)).fetchone()
        return dict(row) if row else None

    def content_duplicated(self, text, exclude_id=None):
        h = content_hash(text)
        row = self.db.execute(
            "SELECT id FROM materials WHERE content_hash=? AND id!=?",
            (h, exclude_id or -1)).fetchone()
        return bool(row)

    # ---------- lifecycle ----------
    def add(self, url, source):
        cu = norm_url(url)
        self.db.execute(
            "INSERT OR IGNORE INTO materials(url,canonical_url,source,status,created_at,updated_at)"
            " VALUES(?,?,?,'new',?,?)", (url, cu, source, now_iso(), now_iso()))
        self.db.commit()
        row = self.db.execute("SELECT id FROM materials WHERE canonical_url=?", (cu,)).fetchone()
        return row["id"]

    def update(self, mid, **fields):
        fields["updated_at"] = now_iso()
        cols = ", ".join("%s=?" % k for k in fields if k != "id")
        vals = list(fields.values()) + [mid]
        self.db.execute("UPDATE materials SET %s WHERE id=?" % cols, vals)
        self.db.commit()

    def set_case(self, mid, case, status="case_built"):
        self.update(mid, case_json=json.dumps(case, ensure_ascii=False), status=status,
                    reason=case.get("classification_reason", "")[:500])

    def get(self, mid):
        row = self.db.execute("SELECT * FROM materials WHERE id=?", (mid,)).fetchone()
        return dict(row) if row else None

    def by_status(self, *statuses):
        q = "SELECT * FROM materials WHERE status IN (%s) ORDER BY " \
            "confidence DESC NULLS LAST, id" % ",".join("?" * len(statuses))
        return [dict(r) for r in self.db.execute(q, statuses)]

    def mark_published(self, mid, message_id, chat_id, case_id,
                       hashtags="", content_type="case"):
        """Единственная точка фиксации публикации: material -> published +
        строка редакционного журнала publications (hard-dedup источник)."""
        self.update(mid, status="published", telegram_message_id=message_id)
        m = self.get(mid) or {}
        self.db.execute(
            "INSERT INTO publications(material_id,case_id,source_url,telegram_message_id,"
            "chat_id,published_at,ok,hashtags,content_type,company,canonical_url,"
            "content_hash,status) VALUES(?,?,?,?,?,?,1,?,?,?,?,?,'ok')",
            (mid, case_id, m.get("url"), message_id, chat_id, now_iso(),
             hashtags, content_type, m.get("company"), m.get("canonical_url"),
             m.get("content_hash")))
        self.db.commit()

    # ---------- publication history / hard & soft dedup ----------
    def case_published(self, case_id):
        """Hard dedup по case_id/news_id (переживает перезапуск процесса)."""
        if not case_id:
            return False
        row = self.db.execute(
            "SELECT 1 FROM publications WHERE case_id=? AND ok=1 LIMIT 1", (case_id,)).fetchone()
        return row is not None

    def published_case_ids(self):
        return {r["case_id"] for r in self.db.execute(
            "SELECT case_id FROM publications WHERE ok=1")}

    def recent_companies(self, days=None):
        """Soft dedup: компании, публиковавшиеся в окне (default SOFT_DEDUP_DAYS).
        -> {company_lower: published_at}. Не запрет, а понижение приоритета."""
        from datetime import datetime, timedelta, timezone
        days = days if days is not None else config.SOFT_DEDUP_DAYS
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
        out = {}
        for r in self.db.execute(
                "SELECT LOWER(company) c, MAX(published_at) t FROM publications "
                "WHERE ok=1 AND company IS NOT NULL AND published_at>=? GROUP BY c",
                (cutoff,)):
            out[r["c"]] = r["t"]
        return out

    def count_cases_since_last_news(self):
        """Счётчик «Новость дня»: только УСПЕШНЫЕ реальные CASE-публикации
        после последней новости (dry-run/review/rejected/ошибки не считаются)."""
        row = self.db.execute(
            "SELECT COUNT(*) c FROM publications WHERE ok=1 AND content_type='case' "
            "AND id > COALESCE((SELECT MAX(id) FROM publications "
            "                   WHERE ok=1 AND content_type='news'), 0)").fetchone()
        return row["c"]

    # ---------- race safety (SQLite claim) ----------
    def claim_for_publish(self, mid):
        """Атомарный захват post_ready -> publishing. Второй параллельный
        процесс rowcount=0 и не опубликует. True = захватили."""
        cur = self.db.execute(
            "UPDATE materials SET status='publishing', updated_at=? "
            "WHERE id=? AND status='post_ready'", (now_iso(), mid))
        self.db.commit()
        return cur.rowcount == 1

    def release_claim(self, mid, status="post_ready", reason=""):
        self.db.execute(
            "UPDATE materials SET status=?, reason=?, updated_at=? "
            "WHERE id=? AND status='publishing'", (status, reason[:300], now_iso(), mid))
        self.db.commit()

    def recover_stale_claims(self, minutes=60):
        """Упавший процесс не должен навечно блокировать материал."""
        from datetime import datetime, timedelta, timezone
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
        cur = self.db.execute(
            "UPDATE materials SET status='post_ready', updated_at=? "
            "WHERE status='publishing' AND updated_at<?", (now_iso(), cutoff))
        self.db.commit()
        return cur.rowcount

    def close(self):
        self.db.close()
