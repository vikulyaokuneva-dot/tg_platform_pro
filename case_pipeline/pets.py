# -*- coding: utf-8 -*-
"""PETS lane for the educational channel «Азбука питомца».

The lane deliberately fails closed: no default sources, no source images without
rights metadata, no machine translation/paid editor by default and no real send
without a durable state backend.  It reuses the platform's HTTP, extraction,
SQLite lifecycle and Telegram publisher without changing AGRO behaviour.
"""
import logging
import re
from datetime import datetime, timedelta, timezone

from . import case_model, config, editorial_profiles, extraction, httpclient
from . import pets_images, pets_storage, telegram, utils

log = logging.getLogger("case.pets")
MIN_BODY_CHARS = 350
MAX_POST_CHARS = 3000


def _news_age_ok(value, days=7):
    if not value:
        return False
    raw = str(value).replace("Z", "+00:00")
    try:
        date = datetime.fromisoformat(raw[:25])
    except ValueError:
        found = re.search(r"(\d{4})-(\d{2})-(\d{2})", raw)
        if not found:
            return False
        date = datetime(int(found.group(1)), int(found.group(2)), int(found.group(3)), tzinfo=timezone.utc)
    date = date.replace(tzinfo=timezone.utc) if date.tzinfo is None else date
    return date >= datetime.now(timezone.utc) - timedelta(days=days)


def _paragraphs(text, maximum=3):
    out = []
    for part in re.split(r"\n\s*\n", text or ""):
        part = re.sub(r"\s+", " ", part).strip()
        if len(part) >= 90 and not re.match(r"^(реклама|подпис|copyright|источник)", part, re.I):
            out.append(part)
        if len(out) >= maximum:
            break
    if not out and len((text or "").strip()) >= 90:
        out = [re.sub(r"\s+", " ", text).strip()[:900]]
    return out


def build_post(title, text, url):
    """Deterministic Russian draft; it only rearranges source sentences."""
    clean_title = re.sub(r"\s+", " ", (title or "Советы владельцам питомцев")).strip()[:120]
    parts = _paragraphs(text)
    body = "\n\n".join(parts[:2])
    conclusion = parts[2] if len(parts) > 2 else (parts[-1] if parts else "")
    post = "🐾 %s\n\n%s" % (clean_title, body)
    if conclusion:
        post += "\n\nПрактический вывод: %s" % conclusion
    post += "\n\nИсточник: %s" % url
    return post[:MAX_POST_CHARS].rstrip()


def _known_status(status):
    return status in {"published", "rejected", "review", "post_ready", "publishing"}


def _normalize_image(candidate, ext, resolver):
    if resolver is None:
        return None
    image = resolver(candidate, ext)
    return image if isinstance(image, dict) else None


def process_url(st, url, source, publish=False, dry_run=True, provider=None,
                image_resolver=None, fetcher=None):
    """Prepare one PETS article; no live request is needed in tests.

    ``provider`` is reserved for an explicitly approved translator/editor. Until
    such provider is implemented and enabled, non-Russian source text goes to
    review rather than being mistranslated or published.
    """
    out = {"url": url, "source": source, "status": "skipped", "reason": ""}
    mid = st.add(url, source)
    row = st.get(mid) or {}
    if _known_status(row.get("status")):
        out["reason"] = "already %s" % row.get("status")
        return out
    fetcher = fetcher or httpclient.fetch
    try:
        _, html = fetcher(url, timeout=config.FETCH_TIMEOUT_SEC)
        ext = extraction.extract_from_html(html, url)
    except Exception as exc:
        st.update(mid, status="failed", reason="fetch: %s" % type(exc).__name__)
        out.update(status="failed", reason="fetch")
        return out
    text, title = ext.get("text") or "", ext.get("title") or ""
    st.update(mid, content_hash=utils.content_hash(text))
    if ext.get("suspect_captcha") or ext.get("quality") == "failed" or len(text) < MIN_BODY_CHARS:
        st.update(mid, status="rejected", reason="thin or blocked content")
        out.update(status="rejected", reason="thin_or_blocked")
        return out
    if config.PETS_CONTENT_MODE == "news" and not _news_age_ok(ext.get("published_at")):
        st.update(mid, status="rejected", reason="stale news or publication date unavailable")
        out.update(status="rejected", reason="stale_news")
        return out
    # Current approved editor is off by default; translating a medical source
    # without an approved factual editor is not a safe fallback.
    if ext.get("language") != "ru" and not (config.PETS_AI_ENABLED and provider):
        st.update(mid, status="review", reason="translation requires approved editor")
        out.update(status="review", reason="translation_requires_editor")
        return out
    profile = editorial_profiles.get_profile(config.PETS_EDITORIAL_PROFILE)
    reasons = profile.review_reasons(title, text)
    if reasons:
        st.update(mid, status="review", reason="; ".join(reasons)[:300])
        out.update(status="review", reason="editorial_safety")
        return out
    facts = profile.classify(title, text)
    if not facts["topic_key"]:
        st.update(mid, status="review", reason="topic cannot be determined")
        out.update(status="review", reason="topic_unknown")
        return out
    if st.topic_seen(facts["topic_key"]):
        st.update(mid, status="rejected", reason="duplicate semantic topic")
        out.update(status="rejected", reason="duplicate_topic")
        return out
    allowed, why = st.diversity_allows(facts["category"], facts["species"])
    if not allowed:
        st.update(mid, status="review", reason=why)
        out.update(status="review", reason=why)
        return out
    image = _normalize_image(url, ext, image_resolver)
    image_ok, image_reason = pets_images.validate_image(image, title)
    if not image_ok:
        st.update(mid, status="review", reason=image_reason)
        out.update(status="review", reason="image_rights")
        return out
    post = build_post(title, text, url)
    if len(post) < 250:
        st.update(mid, status="review", reason="post is too short")
        out.update(status="review", reason="post_too_short")
        return out
    if not st.reserve_topic(mid, facts["topic_key"], facts["category"], facts["species"]):
        st.update(mid, status="rejected", reason="duplicate semantic topic")
        out.update(status="rejected", reason="duplicate_topic")
        return out
    st.record_image_rights(mid, image)
    st.update(mid, status="post_ready", post_text=post, image_url=image["url"],
              classification="pets:%s:%s" % (facts["category"], facts["species"]),
              reason="pets_expert:%s" % config.PETS_CONTENT_MODE)
    out.update(status="post_ready", category=facts["category"], species=facts["species"])
    if not (publish and not dry_run):
        return out
    if config.PETS_REQUIRE_DURABLE_STATE and config.PETS_STATE_BACKEND != "durable":
        st.update(mid, status="review", reason="durable state backend is required before real publishing")
        out.update(status="review", reason="durable_state_required")
        return out
    try:
        photo = httpclient.fetch_bytes(image["url"])
    except Exception as exc:
        st.update(mid, status="review", reason="image fetch: %s" % type(exc).__name__)
        out.update(status="review", reason="image_fetch")
        return out
    if not st.claim_for_publish(mid):
        out["reason"] = "claim lost"
        return out
    result = telegram.publish_post(post, dry_run=False, channel="pets", image=photo)
    if result.ok:
        st.mark_published(mid, result.message_id, config.PETS_CHAT_ID,
                          case_model.case_id_for(url, text[:2000]), content_type="pets")
        st.publish_topic(mid)
        out.update(status="published", telegram_message_id=result.message_id)
        return out
    # A timeout/lost response may still have reached Telegram. Never retry it automatically.
    st.release_claim(mid, "review", "telegram delivery uncertain: %s" % (result.error or "unknown"))
    out.update(status="review", reason="telegram_delivery_uncertain")
    return out


def run(dry_run=True, publish=False, sources=None, st=None, adapters=None,
        image_resolver=None, provider=None):
    st = st or pets_storage.PetsStorage(config.PETS_DB_PATH)
    st.quarantine_stale_claims()
    source_ids = sources if sources is not None else config.PETS_SOURCES
    adapters = adapters or {}
    allow_publish = publish and config.PETS_PUBLISH
    summary = {"checked": 0, "post_ready": 0, "published": 0, "rejected": 0,
               "review": 0, "failed": 0, "skipped": 0,
               "dry_run": dry_run or not allow_publish, "sources": list(source_ids)}
    published = 0
    for source in source_ids:
        adapter = adapters.get(source)
        if adapter is None:
            summary.setdefault("source_errors", {})[source] = "not approved or adapter unavailable"
            continue
        try:
            urls = adapter.discover()
        except Exception as exc:
            summary.setdefault("source_errors", {})[source] = type(exc).__name__
            continue
        for url in urls[:config.PETS_MAX_PER_RUN * 4]:
            if allow_publish and published >= config.PETS_PUBLISH_LIMIT:
                break
            result = process_url(st, url, source, publish=allow_publish, dry_run=dry_run,
                                 provider=provider, image_resolver=image_resolver)
            summary["checked"] += 1
            status = result.get("status", "skipped")
            if status in summary:
                summary[status] += 1
            if status == "published":
                published += 1
    return summary
