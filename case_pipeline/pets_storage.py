# -*- coding: utf-8 -*-
"""PETS-only metadata layered over the shared SQLite Storage schema."""
from datetime import datetime, timedelta, timezone

from .storage import Storage
from .utils import now_iso


_SCHEMA = """
CREATE TABLE IF NOT EXISTS pets_topic_history (
    material_id INTEGER NOT NULL UNIQUE,
    topic_key TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL,
    species TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('reserved', 'published')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pets_image_rights (
    material_id INTEGER NOT NULL UNIQUE,
    image_url TEXT NOT NULL,
    author TEXT NOT NULL,
    source_url TEXT NOT NULL,
    license TEXT NOT NULL,
    license_url TEXT NOT NULL DEFAULT '',
    attribution TEXT NOT NULL,
    search_query TEXT NOT NULL DEFAULT '',
    topic_match TEXT NOT NULL DEFAULT '',
    semantic_tags TEXT NOT NULL DEFAULT '',
    semantic_evidence TEXT NOT NULL DEFAULT '',
    verified_at TEXT NOT NULL
);
"""


class PetsStorage(Storage):
    def __init__(self, path):
        super().__init__(path)
        self.db.executescript(_SCHEMA)
        cols = {r["name"] for r in self.db.execute("PRAGMA table_info(pets_image_rights)")}
        for name in ("license_url", "search_query", "topic_match", "semantic_tags", "semantic_evidence"):
            if name not in cols:
                self.db.execute("ALTER TABLE pets_image_rights ADD COLUMN %s TEXT NOT NULL DEFAULT ''" % name)
        self.db.commit()

    def topic_seen(self, key):
        return self.db.execute("SELECT material_id,status FROM pets_topic_history WHERE topic_key=?", (key,)).fetchone()

    def reserve_topic(self, material_id, key, category, species):
        now = now_iso()
        cur = self.db.execute(
            "INSERT OR IGNORE INTO pets_topic_history(material_id,topic_key,category,species,status,created_at,updated_at) "
            "VALUES(?,?,?,?, 'reserved', ?, ?)", (material_id, key, category, species, now, now))
        self.db.commit()
        return cur.rowcount == 1

    def publish_topic(self, material_id):
        self.db.execute("UPDATE pets_topic_history SET status='published',updated_at=? WHERE material_id=?",
                        (now_iso(), material_id))
        self.db.commit()

    def mark_pets_published(self, material_id, message_id, case_id):
        """Store a PETS delivery without persisting a recipient chat ID.

        The destination is implied by this isolated lane. The durable SQLite is
        strictly for deduplication/editorial recovery and must remain free of
        owner or audience identifiers.
        """
        self.update(material_id, status="published", telegram_message_id=message_id)
        material = self.get(material_id) or {}
        self.db.execute(
            "INSERT INTO publications(material_id,case_id,source_url,telegram_message_id,"
            "chat_id,published_at,ok,hashtags,content_type,company,canonical_url,"
            "content_hash,status) VALUES(?,?,?,?,?,?,1,?,?,?,?,?,'ok')",
            (material_id, case_id, material.get("url"), message_id, None, now_iso(),
             "", "pets", None, material.get("canonical_url"),
             material.get("content_hash")))
        self.db.commit()

    def record_image_rights(self, material_id, image):
        self.db.execute(
            "INSERT OR REPLACE INTO pets_image_rights(material_id,image_url,author,source_url,license,license_url,attribution,search_query,topic_match,semantic_tags,semantic_evidence,verified_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (material_id, image["url"], image["author"], image["source_url"], image["license"],
             image.get("license_url", ""), image["attribution"], image.get("query", ""),
             image.get("topic_match", ""), ",".join(image.get("semantic_tags", ())),
             image.get("semantic_evidence", ""), now_iso()))
        self.db.commit()

    def migrate_demo_materials(self):
        """Label old seed records so they cannot be mistaken for source pipeline output."""
        cur = self.db.execute(
            "UPDATE materials SET status='demo_ready', reason='pets_expert:demo_manual_review', "
            "updated_at=? WHERE source='curated_original' AND status='post_ready'", (now_iso(),))
        self.db.commit()
        return cur.rowcount

    def diversity_allows(self, category, species):
        rows = self.db.execute(
            "SELECT category,species FROM pets_topic_history WHERE status='published' ORDER BY updated_at DESC LIMIT 8").fetchall()
        latest_species = [r["species"] for r in rows[:2] if r["species"] in {"cat", "dog"}]
        if species in {"cat", "dog"} and len(latest_species) == 2 and all(s == species for s in latest_species):
            return False, "diversity: rotate cat/dog"
        counts = {name: 0 for name in ("care", "breed", "behavior", "nutrition", "science")}
        for row in rows:
            counts[row["category"]] = counts.get(row["category"], 0) + 1
        if len(rows) >= 5 and counts.get(category, 0) / len(rows) > .50:
            return False, "diversity: category overrepresented"
        return True, ""

    def quarantine_stale_claims(self, minutes=60):
        """Never auto-retry a stale Telegram claim: delivery may be unknown."""
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")
        cur = self.db.execute(
            "UPDATE materials SET status='review',reason='telegram delivery uncertain: stale publishing claim',updated_at=? "
            "WHERE status='publishing' AND updated_at<?", (now_iso(), cutoff))
        self.db.commit()
        return cur.rowcount
