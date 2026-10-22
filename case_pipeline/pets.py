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

from . import ai as ai_mod
from . import case_model, config, editorial_profiles, extraction, httpclient, pets_editor
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


def build_original_post(title, body, fact_sources, practical_steps=()):
    """Format an owner-reviewed original text without adapting source prose."""
    clean_title = re.sub(r"\s+", " ", (title or "Памятка владельцу")).strip()[:120]
    clean_body = "\n\n".join(
        re.sub(r"\s+", " ", part).strip() for part in (body or "").split("\n\n")
        if part.strip())
    sources = [str(item).strip() for item in (fact_sources or ()) if str(item).strip()]
    if not clean_body or not sources:
        return ""
    steps = [str(step).strip() for step in practical_steps if str(step).strip()]
    practical = ""
    if steps:
        practical = "\n\nЧто можно сделать сегодня:\n" + "\n".join(
            "• " + step for step in steps[:3])
    links = "\n".join("- " + item for item in sources)
    return ("🐾 %s\n\n%s%s\n\nПроверка фактов:\n%s" %
            (clean_title, clean_body, practical, links))[:MAX_POST_CHARS].rstrip()


def _known_status(status):
    return status in {"published", "rejected", "review", "post_ready", "demo_ready", "publishing"}


def _normalize_image(candidate, ext, resolver):
    if resolver is None:
        return None
    image = resolver(candidate, ext)
    return image if isinstance(image, dict) else None


def process_url(st, url, source, publish=False, dry_run=True, provider=None,
                image_resolver=None, fetcher=None, checkpoint=None):
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
    # Translation/rewrite is opt-in and reuses only the existing GigaChat
    # provider. Any unavailable or unverifiable edit remains in manual review.
    if ext.get("language") != "ru":
        provider = provider if provider is not None else ai_mod.get_provider()
        edited = pets_editor.edit(title, text, url, provider) if config.PETS_AI_ENABLED else None
        if not edited:
            st.update(mid, status="review", reason="translation requires approved editor")
            out.update(status="review", reason="translation_requires_editor")
            return out
        title, text = edited["title"], edited["text"]
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
    if config.PETS_REQUIRE_DURABLE_STATE and config.PETS_STATE_BACKEND != "github":
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
    # Durable checkpoint BEFORE Telegram.  A crash after a response must leave
    # at least ``publishing`` remotely, never an apparently new material that
    # a later run could post again.
    if checkpoint is not None:
        try:
            checkpoint("claimed")
        except Exception as exc:
            st.release_claim(mid, "review", "durable state checkpoint failed before send")
            out.update(status="review", reason="durable_state_checkpoint")
            return out
    result = telegram.publish_post(post, dry_run=False, channel="pets", image=photo)
    if result.ok:
        st.mark_pets_published(mid, result.message_id,
                               case_model.case_id_for(url, text[:2000]))
        st.publish_topic(mid)
        if checkpoint is not None:
            try:
                checkpoint("published")
            except Exception:
                # Telegram already accepted the post. The remote record still
                # says ``publishing`` and will be quarantined, never retried.
                out.update(status="review", reason="durable_state_after_send")
                return out
        out.update(status="published", telegram_message_id=result.message_id)
        return out
    # A timeout/lost response may still have reached Telegram. Never retry it automatically.
    st.release_claim(mid, "review", "telegram delivery uncertain: %s" % (result.error or "unknown"))
    out.update(status="review", reason="telegram_delivery_uncertain")
    return out


def process_original_brief(st, brief):
    """Queue an original, fact-checked brief for owner review only.

    This route never fetches, translates, or adapts a third-party article and
    never sends a message. It exists for material written specifically for PETS.
    """
    brief = brief or {}
    brief_id = str(brief.get("id") or "").strip()
    url = "draft://pets/" + brief_id
    out = {"url": url, "source": "curated_original", "status": "skipped", "reason": ""}
    required = ("id", "title", "body", "species", "category", "topic_key", "image")
    if not brief_id or any(not brief.get(key) for key in required):
        return dict(out, status="rejected", reason="original_brief_incomplete")
    post = build_original_post(brief["title"], brief["body"], brief.get("fact_sources"),
                               brief.get("practical_steps", ()))
    if len(post) < 250:
        return dict(out, status="rejected", reason="original_brief_insufficient")
    profile = editorial_profiles.get_profile(config.PETS_EDITORIAL_PROFILE)
    if profile.review_reasons(brief["title"], brief["body"]):
        return dict(out, status="review", reason="editorial_safety")
    image_ok, image_reason = pets_images.validate_image(brief["image"], brief["title"])
    if not image_ok:
        return dict(out, status="review", reason="image_rights:" + image_reason)
    mid = st.add(url, "curated_original")
    row = st.get(mid) or {}
    # Demonstrations are versioned with the code. Refreshing one may update its
    # wording/image metadata, but it can never turn it into an automatic post.
    if row.get("status") == "demo_ready":
        st.record_image_rights(mid, brief["image"])
        st.update(mid, content_hash=utils.content_hash(brief["body"]), status="demo_ready",
                  post_text=post, image_url=brief["image"]["url"],
                  classification="pets:%s:%s" % (brief["category"], brief["species"]),
                  reason="pets_expert:demo_manual_review")
        return dict(out, status="demo_ready", category=brief["category"], species=brief["species"],
                    refreshed=True)
    if _known_status(row.get("status")):
        return dict(out, reason="already " + str(row.get("status")))
    if st.topic_seen(brief["topic_key"]):
        st.update(mid, status="rejected", reason="duplicate semantic topic")
        return dict(out, status="rejected", reason="duplicate_topic")
    allowed, why = st.diversity_allows(brief["category"], brief["species"])
    if not allowed:
        st.update(mid, status="review", reason=why)
        return dict(out, status="review", reason=why)
    if not st.reserve_topic(mid, brief["topic_key"], brief["category"], brief["species"]):
        return dict(out, status="rejected", reason="duplicate_topic")
    st.record_image_rights(mid, brief["image"])
    st.update(mid, content_hash=utils.content_hash(brief["body"]), status="demo_ready",
              post_text=post, image_url=brief["image"]["url"],
              classification="pets:%s:%s" % (brief["category"], brief["species"]),
              reason="pets_expert:original_manual_review")
    return dict(out, status="demo_ready", category=brief["category"], species=brief["species"])


def run(dry_run=True, publish=False, sources=None, st=None, adapters=None,
        image_resolver=None, provider=None, checkpoint=None, briefs=()):
    st = st or pets_storage.PetsStorage(config.PETS_DB_PATH)
    st.quarantine_stale_claims()
    source_ids = sources if sources is not None else config.PETS_SOURCES
    adapters = adapters or {}
    if image_resolver is None and config.PETS_IMAGE_PROVIDER == "wikimedia":
        image_resolver = pets_images.resolve_wikimedia_commons
    allow_publish = publish and config.PETS_PUBLISH
    summary = {"checked": 0, "post_ready": 0, "published": 0, "rejected": 0,
               "review": 0, "failed": 0, "skipped": 0,
               "dry_run": dry_run or not allow_publish, "sources": list(source_ids),
               "reason_counts": {}, "ready_material_ids": [], "demo_ready": 0}
    published = 0
    for brief in briefs or ():
        result = process_original_brief(st, brief)
        summary["checked"] += 1
        status = result.get("status", "skipped")
        if status in summary:
            summary[status] += 1
        reason = result.get("reason") or ""
        if reason:
            summary["reason_counts"][reason] = summary["reason_counts"].get(reason, 0) + 1
        if status == "post_ready":
            row = st.seen_url(result["url"]) or {}
            if row.get("id") is not None:
                summary["ready_material_ids"].append(row["id"])
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
                                 provider=provider, image_resolver=image_resolver,
                                 checkpoint=checkpoint)
            summary["checked"] += 1
            status = result.get("status", "skipped")
            if status in summary:
                summary[status] += 1
            reason = result.get("reason") or ""
            if reason:
                summary["reason_counts"][reason] = summary["reason_counts"].get(reason, 0) + 1
            if status == "post_ready":
                row = st.seen_url(url) or {}
                if row.get("id") is not None:
                    summary["ready_material_ids"].append(row["id"])
            if status == "published":
                published += 1
    return summary
