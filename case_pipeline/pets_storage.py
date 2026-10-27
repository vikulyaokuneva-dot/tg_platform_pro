# -*- coding: utf-8 -*-
"""PETS-only metadata layered over the shared SQLite Storage schema."""
from datetime import datetime, timedelta, timezone
import re
import json

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
CREATE TABLE IF NOT EXISTS pets_facts (
    id INTEGER PRIMARY KEY,
    material_id INTEGER NOT NULL,
    claim TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_type TEXT NOT NULL,
    author_or_body TEXT NOT NULL,
    published_at TEXT,
    accessed_at TEXT NOT NULL,
    license TEXT NOT NULL,
    license_source_url TEXT NOT NULL DEFAULT '',
    attribution_requirements TEXT NOT NULL DEFAULT '',
    license_verified_at TEXT NOT NULL DEFAULT '',
    adaptation_allowed INTEGER NOT NULL,
    evidence_level TEXT NOT NULL,
    source_section TEXT NOT NULL DEFAULT '',
    fact_kind TEXT NOT NULL DEFAULT 'unknown',
    UNIQUE(material_id, claim, source_url)
);
CREATE TABLE IF NOT EXISTS pets_topic_plans (
    topic_key TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    species TEXT NOT NULL,
    planned_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pets_source_candidates (
    source_key TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    title TEXT NOT NULL,
    species TEXT NOT NULL,
    doi TEXT NOT NULL DEFAULT '',
    source_url TEXT NOT NULL,
    authors TEXT NOT NULL DEFAULT '',
    published_at TEXT,
    license TEXT NOT NULL,
    license_source_url TEXT NOT NULL DEFAULT '',
    attribution_requirements TEXT NOT NULL DEFAULT '',
    adaptation_allowed INTEGER NOT NULL,
    facts_json TEXT NOT NULL,
    safety_status TEXT NOT NULL,
    technical_status TEXT NOT NULL DEFAULT '',
    editorial_status TEXT NOT NULL DEFAULT '',
    topic_key TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '',
    pmcid TEXT NOT NULL DEFAULT '',
    study_json TEXT NOT NULL DEFAULT '{}',
    image_search_feasible INTEGER NOT NULL DEFAULT 0,
    image_verified INTEGER NOT NULL DEFAULT 0,
    editorial_json TEXT NOT NULL DEFAULT '',
    limitations_json TEXT NOT NULL DEFAULT '[]',
    checked_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pets_source_candidate_history (
    identity_key TEXT PRIMARY KEY,
    decision TEXT NOT NULL,
    reason_category TEXT NOT NULL,
    checked_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pets_publication_queue (
    material_id INTEGER NOT NULL UNIQUE,
    queue_status TEXT NOT NULL CHECK(queue_status IN ('ready', 'claimed', 'published', 'review', 'rejected')),
    origin TEXT NOT NULL,
    queued_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS pets_ai_usage (
    moscow_date TEXT PRIMARY KEY,
    gigachat_calls INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
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
        fact_cols = {r["name"] for r in self.db.execute("PRAGMA table_info(pets_facts)")}
        for name in ("license_source_url", "attribution_requirements", "license_verified_at",
                     "source_section", "fact_kind"):
            if name not in fact_cols:
                self.db.execute("ALTER TABLE pets_facts ADD COLUMN %s TEXT NOT NULL DEFAULT ''" % name)
        candidate_cols = {r["name"] for r in self.db.execute("PRAGMA table_info(pets_source_candidates)")}
        for name, default in (("technical_status", "''"), ("editorial_status", "''"),
                              ("topic_key", "''"), ("category", "''"), ("pmcid", "''"),
                              ("study_json", "'{}'"), ("image_search_feasible", "0"),
                              ("image_verified", "0"),
                              ("editorial_json", "''"), ("limitations_json", "'[]'")):
            if name not in candidate_cols:
                self.db.execute("ALTER TABLE pets_source_candidates ADD COLUMN %s TEXT NOT NULL DEFAULT %s" %
                                (name, default))
        self.db.commit()

    def topic_seen(self, key):
        return self.db.execute("SELECT material_id,status FROM pets_topic_history WHERE topic_key=?", (key,)).fetchone()

    def similar_topic_seen(self, key):
        """A small transparent semantic guard: token overlap, never an AI guess."""
        tokens = {x for x in re.split(r"[^a-zа-яё0-9]+", str(key).lower()) if len(x) > 2}
        if not tokens:
            return None
        rows = self.db.execute("SELECT topic_key,material_id FROM pets_topic_history").fetchall()
        for row in rows:
            other = {x for x in re.split(r"[^a-zа-яё0-9]+", row["topic_key"].lower()) if len(x) > 2}
            if other and len(tokens & other) / max(len(tokens), len(other)) >= .75:
                return row
        return None

    def plan_topic(self, topic):
        self.db.execute(
            "INSERT OR IGNORE INTO pets_topic_plans(topic_key,category,species,planned_at) VALUES(?,?,?,?)",
            (topic.key, topic.category, topic.species, now_iso()))
        self.db.commit()

    def record_facts(self, material_id, facts):
        for fact in facts:
            value = fact.serializable()
            self.db.execute(
                "INSERT OR IGNORE INTO pets_facts(material_id,claim,source_url,source_name,source_type,author_or_body,"
                "published_at,accessed_at,license,license_source_url,attribution_requirements,license_verified_at,"
                "adaptation_allowed,evidence_level,source_section,fact_kind) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (material_id, value["claim"], value["source_url"], value["source_name"], value["source_type"],
                 value["author_or_body"], value["published_at"], value["accessed_at"], value["license"],
                 value.get("license_source_url", ""), value.get("attribution_requirements", ""),
                 value.get("license_verified_at", ""), int(bool(value["adaptation_allowed"])), value["evidence_level"],
                 value.get("source_section", ""), value.get("fact_kind", "unknown")))
        self.db.commit()

    def facts_for(self, material_id):
        return [dict(row) for row in self.db.execute(
            "SELECT claim,source_url,source_name,source_type,author_or_body,published_at,accessed_at,license,"
            "license_source_url,attribution_requirements,license_verified_at,adaptation_allowed,evidence_level,source_section,fact_kind "
            "FROM pets_facts WHERE material_id=? ORDER BY id", (material_id,))]

    def save_source_candidate(self, candidate):
        facts = [fact.serializable() for fact in candidate.get("facts", ())]
        self.db.execute(
            "INSERT OR REPLACE INTO pets_source_candidates(source_key,source_id,title,species,doi,source_url,authors,"
            "published_at,license,license_source_url,attribution_requirements,adaptation_allowed,facts_json,safety_status,"
            "technical_status,editorial_status,topic_key,category,pmcid,study_json,image_search_feasible,image_verified,"
            "editorial_json,limitations_json,checked_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (candidate["source_key"], candidate["source_id"], candidate["title"], candidate["species"],
             candidate.get("doi", ""), candidate["source_url"], candidate.get("authors", ""),
             candidate.get("published_at"), candidate["license"], candidate.get("license_source_url", ""),
             candidate.get("attribution_requirements", ""), int(bool(candidate.get("adaptation_allowed"))),
             json.dumps(facts, ensure_ascii=False, sort_keys=True), candidate["safety_status"],
             candidate.get("technical_status", ""), candidate.get("editorial_status", ""),
             candidate.get("topic_key", ""), candidate.get("category", ""), candidate.get("pmcid", ""),
             json.dumps(candidate.get("study", {}), ensure_ascii=False, sort_keys=True),
             int(bool(candidate.get("image_search_feasible"))), int(bool(candidate.get("image_verified"))),
             json.dumps(candidate.get("editorial", {}), ensure_ascii=False, sort_keys=True),
             json.dumps(candidate.get("limitations", ()), ensure_ascii=False), now_iso()))
        self.db.commit()

    def source_candidate_rejected(self, identities):
        values = tuple(sorted(identities or ()))
        if not values:
            return False
        marks = ",".join("?" for _ in values)
        return bool(self.db.execute(
            "SELECT 1 FROM pets_source_candidate_history WHERE decision='needs_editorial_review' AND identity_key IN (%s)" % marks,
            values).fetchone())

    def record_source_candidate_rejection(self, identities, reason_category):
        for identity in sorted(identities or ()):
            self.db.execute(
                "INSERT OR REPLACE INTO pets_source_candidate_history(identity_key,decision,reason_category,checked_at) VALUES(?,?,?,?)",
                (identity, "needs_editorial_review", reason_category, now_iso()))
        self.db.commit()

    def source_rejection_statistics(self):
        return {row["reason_category"]: row["count"] for row in self.db.execute(
            "SELECT reason_category,COUNT(*) AS count FROM pets_source_candidate_history "
            "WHERE decision='needs_editorial_review' GROUP BY reason_category ORDER BY reason_category")}

    def source_candidates(self):
        return [dict(row) for row in self.db.execute(
            "SELECT * FROM pets_source_candidates ORDER BY checked_at DESC, source_key")]

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

    def pets_published_today(self, now=None):
        """Count PETS deliveries since the current Moscow calendar day began.

        The durable publication ledger is the authority here, not the current
        Actions run.  This blocks a second manual or scheduled execution on the
        same Moscow day as well as multiple messages in one run.
        """
        moscow = timezone(timedelta(hours=3))
        current = now or datetime.now(timezone.utc)
        current = current.replace(tzinfo=timezone.utc) if current.tzinfo is None else current
        local = current.astimezone(moscow)
        start = local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
        cutoff = start.strftime("%Y-%m-%dT%H:%M:%SZ")
        return int(self.db.execute(
            "SELECT COUNT(*) AS count FROM publications "
            "WHERE content_type='pets' AND ok=1 AND published_at>=?", (cutoff,)
        ).fetchone()["count"])

    def reserve_gigachat_generation(self, now=None):
        """Atomically reserve PETS' sole paid generation for the Moscow day.

        The reservation is made before the provider request and committed to the
        durable database.  A failed or ambiguous provider response therefore
        cannot trigger paid automatic retries later the same day.
        """
        moscow = timezone(timedelta(hours=3))
        current = now or datetime.now(timezone.utc)
        current = current.replace(tzinfo=timezone.utc) if current.tzinfo is None else current
        day = current.astimezone(moscow).date().isoformat()
        self.db.execute(
            "INSERT OR IGNORE INTO pets_ai_usage(moscow_date,gigachat_calls,updated_at) VALUES(?,?,?)",
            (day, 0, now_iso()),
        )
        cur = self.db.execute(
            "UPDATE pets_ai_usage SET gigachat_calls=gigachat_calls+1,updated_at=? "
            "WHERE moscow_date=? AND gigachat_calls<1",
            (now_iso(), day),
        )
        self.db.commit()
        return cur.rowcount == 1

    def migrate_demo_materials(self, allowed_evergreen_urls=()):
        """Quarantine old curated drafts outside the explicit automatic allowlist.

        A historical ``curated_original`` row is never sufficient authority for
        automatic delivery. Published history is intentionally preserved.
        """
        allowed = tuple(str(url) for url in (allowed_evergreen_urls or ()) if url)
        query = (
            "UPDATE materials SET status='demo_ready', reason='pets_expert:not_in_evergreen_allowlist', "
            "updated_at=? WHERE source='curated_original' AND status='post_ready'"
        )
        params = [now_iso()]
        if allowed:
            query += " AND url NOT IN (%s)" % ",".join("?" for _ in allowed)
            params.extend(allowed)
        cur = self.db.execute(query, tuple(params))
        self.db.commit()
        return cur.rowcount

    def enqueue_verified_material(self, material_id, origin="verified_factual"):
        """Make a fully checked factual draft eligible for the PETS queue.

        This is an explicit, database-backed production gate.  It is never
        inferred from a fixture or from the legacy curated/demo source.
        """
        row = self.get(material_id) or {}
        if row.get("status") != "post_ready" or row.get("source") == "curated_original":
            return False
        now = now_iso()
        self.db.execute(
            "INSERT OR IGNORE INTO pets_publication_queue(material_id,queue_status,origin,queued_at,updated_at,reason) "
            "VALUES(?, 'ready', ?, ?, ?, '')", (material_id, origin, now, now))
        self.db.commit()
        return bool(self.db.execute(
            "SELECT 1 FROM pets_publication_queue WHERE material_id=? AND queue_status='ready'", (material_id,)).fetchone())

    def queued_materials(self, limit=10):
        return [dict(row) for row in self.db.execute(
            "SELECT m.*,q.queue_status,q.origin,q.queued_at,q.reason AS queue_reason "
            "FROM pets_publication_queue q JOIN materials m ON m.id=q.material_id "
            "WHERE q.queue_status='ready' AND m.status='post_ready' AND m.source!='curated_original' "
            "ORDER BY q.queued_at,m.id LIMIT ?", (int(limit),))]

    def queued_count(self):
        return int(self.db.execute(
            "SELECT COUNT(*) AS count FROM pets_publication_queue q JOIN materials m ON m.id=q.material_id "
            "WHERE q.queue_status='ready' AND m.status='post_ready' AND m.source!='curated_original'").fetchone()["count"])

    def queue_mark(self, material_id, status, reason=""):
        if status not in {"ready", "claimed", "published", "review", "rejected"}:
            raise ValueError("invalid PETS queue status")
        self.db.execute("UPDATE pets_publication_queue SET queue_status=?,reason=?,updated_at=? WHERE material_id=?",
                        (status, reason, now_iso(), material_id))
        self.db.commit()

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
