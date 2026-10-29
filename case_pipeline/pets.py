# -*- coding: utf-8 -*-
"""PETS lane for the educational channel «Азбука питомца».

The lane deliberately fails closed: no default sources, no source images without
rights metadata, no machine translation/paid editor by default and no real send
without a durable state backend.  It reuses the platform's HTTP, extraction,
SQLite lifecycle and Telegram publisher without changing AGRO behaviour.
"""
import logging
import json
import re
from datetime import datetime, timedelta, timezone

from . import ai as ai_mod
from . import case_model, config, editorial_profiles, extraction, httpclient, pets_editor, postformat
from . import pets_briefs, pets_images, pets_storage, telegram, utils
from .pets_facts import validate_fact_set, validate_generated_text
from .pets_generator import (MockPetsGenerator, PETS_READER_POST_MAX_CHARS,
                             PETS_READER_POST_MIN_CHARS, reader_post_length,
                             validate_editorial_post)
from .pets_planner import Topic, choose_topics

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


def process_evergreen_brief(st, brief, *, publish=False, dry_run=True, checkpoint=None):
    """Prepare or publish one vetted fallback item, never a demo row."""
    approved_ids = {item["id"] for item in pets_briefs.EVERGREEN_BRIEFS}
    if str((brief or {}).get("id") or "") not in approved_ids:
        return {"source": "curated_original", "status": "rejected",
                "reason": "evergreen_not_allowlisted"}
    prepared = process_original_brief(st, brief)
    url = prepared.get("url", "")
    if prepared.get("status") not in {"demo_ready", "skipped"}:
        return prepared
    row = st.seen_url(url) or {}
    if row.get("status") == "published":
        return dict(prepared, status="skipped", reason="already published")
    if row.get("status") == "demo_ready":
        st.update(row["id"], status="post_ready", reason="pets_evergreen:verified_original")
        row = st.get(row["id"]) or row
    if not (publish and not dry_run):
        return dict(prepared, status="post_ready", material_id=row.get("id"))
    if config.PETS_REQUIRE_DURABLE_STATE and config.PETS_STATE_BACKEND != "github":
        return dict(prepared, status="review", reason="durable_state_required")
    image = brief["image"]
    if row.get("image_url") != image.get("url"):
        st.update(row["id"], status="review", reason="image_metadata_mismatch")
        return dict(prepared, status="review", reason="image_metadata_mismatch")
    photo, diagnostic = pets_images.download_preview_image(image, max_attempts=3)
    log.info("pets evergreen image material_id=%s diagnostic=%s", row["id"],
             json.dumps(diagnostic, ensure_ascii=True, sort_keys=True))
    if photo is None:
        st.update(row["id"], status="review", reason="image_download_failed")
        return dict(prepared, status="review", reason="image_download_failed", image_download=diagnostic)
    if not st.claim_for_publish(row["id"]):
        return dict(prepared, status="review", reason="publish_claim_lost")
    try:
        if checkpoint:
            checkpoint("claimed")
    except Exception:
        st.release_claim(row["id"], "review", "durable_state_checkpoint_failed_before_send")
        return dict(prepared, status="review", reason="durable_state_checkpoint_failed_before_send")
    try:
        sent = telegram.publish_post(row.get("post_text") or "", dry_run=False,
                                      channel="pets", image=photo)
    except Exception:
        st.release_claim(row["id"], "review", "telegram_delivery_uncertain")
        return dict(prepared, status="review", reason="telegram_delivery_uncertain")
    if not sent.ok:
        st.release_claim(row["id"], "review", "telegram_delivery_uncertain")
        return dict(prepared, status="review", reason="telegram_delivery_uncertain")

    # The message now exists remotely.  Never release this claim back into an
    # automatic queue: a post-send persistence failure must block retries,
    # not create a duplicate publication.
    st.mark_pets_published(row["id"], sent.message_id,
                           case_model.case_id_for(url, row.get("post_text", "")[:2000]))
    st.publish_topic(row["id"])
    try:
        if checkpoint:
            checkpoint("published")
    except Exception:
        return dict(prepared, status="published", telegram_message_id=sent.message_id,
                    durable_state="checkpoint_failed_after_send")
    return dict(prepared, status="published", telegram_message_id=sent.message_id)


def process_fact_material(st, topic, facts, source_id, generator=None, image_resolver=None):
    """Prepare one external-source draft, with no Telegram side effect.

    A mock generator is deliberately returned as ``review``: test content must
    never be mistaken for a new publishable material.  A real GigaChat result
    remains subject to the same fact, rights, duplicate and image gates.
    """
    out = {"source": source_id, "topic": topic.key, "status": "review", "reason": ""}
    facts = list(facts or ())
    ok, reason = validate_fact_set(facts)
    if not ok:
        return dict(out, reason=reason)
    canonical_url = facts[0].source_url
    mid = st.add(canonical_url, source_id)
    row = st.get(mid) or {}
    if _known_status(row.get("status")):
        return dict(out, status="skipped", reason="already " + str(row.get("status")))
    if st.topic_seen(topic.key) or st.similar_topic_seen(topic.key):
        st.update(mid, status="rejected", reason="duplicate semantic topic")
        return dict(out, status="rejected", reason="duplicate_topic")
    allowed, diversity_reason = st.diversity_allows(topic.category, topic.species)
    if not allowed:
        st.update(mid, status="review", reason=diversity_reason)
        return dict(out, reason=diversity_reason)
    generator = generator or MockPetsGenerator()
    generated = generator.generate(topic, facts)
    if not generated:
        st.update(mid, status="review", reason="ai_generation_failed")
        return dict(out, reason="ai_generation_failed")
    if generated.get("mode") == "mock":
        st.record_facts(mid, facts)
        st.update(mid, status="review", post_text=generated.get("text", ""),
                  classification="pets:mock:%s:%s" % (topic.category, topic.species),
                  reason="mock_generation_requires_real_ai_opt_in")
        return dict(out, reason="mock_generation_requires_real_ai_opt_in")
    title = generated.get("title") or topic.title
    text = generated.get("text", "")
    if not PETS_READER_POST_MIN_CHARS <= reader_post_length(title, text) <= PETS_READER_POST_MAX_CHARS:
        st.update(mid, status="review", reason="generated_text_length_invalid")
        return dict(out, reason="generated_text_length_invalid")
    generated_ok, generated_reason = validate_generated_text(
        title + "\n" + text, facts,
        citation_text="\n".join(fact.source_url for fact in facts),
        allowed_source_urls=tuple(fact.source_url for fact in facts),
    )
    if not generated_ok:
        st.update(mid, status="review", reason=generated_reason)
        return dict(out, reason=generated_reason)
    editorial_ok, editorial_reason = validate_editorial_post(title, text)
    if not editorial_ok:
        st.update(mid, status="review", reason=editorial_reason)
        return dict(out, reason=editorial_reason)
    image_resolver = image_resolver or (pets_images.resolve_wikimedia_commons if config.PETS_IMAGE_PROVIDER == "wikimedia" else None)
    image = _normalize_image(canonical_url, {"title": title, "text": text,
                                              "visual_tags": topic.visual_tags}, image_resolver)
    if isinstance(image, dict):
        # The material defines the visual contract; a resolver may provide
        # evidence tags, but it must not choose its own weaker requirements.
        image = dict(image)
        image["required_tags"] = tuple(topic.visual_tags)
    image_ok, image_reason = pets_images.validate_image(image, title)
    if not image_ok:
        st.record_facts(mid, facts)
        st.update(mid, status="review", reason="image_review:" + image_reason)
        return dict(out, reason="image_review:" + image_reason)
    if not st.reserve_topic(mid, topic.key, topic.category, topic.species):
        st.update(mid, status="rejected", reason="duplicate semantic topic")
        return dict(out, status="rejected", reason="duplicate_topic")
    st.plan_topic(topic)
    st.record_facts(mid, facts)
    st.record_image_rights(mid, image)
    attribution = "\n\nИсточники: " + "; ".join(dict.fromkeys(fact.source_url for fact in facts))
    attribution += "\nФото: %s — %s. %s" % (image["author"], image["license"], image["source_url"])
    rendered = "%s\n\n%s%s" % (title, text, attribution)
    formatted = postformat.format_post(rendered)
    telegram_text = postformat.to_markdownv2(formatted)
    if len(telegram_text) > telegram.CAPTION_LIMIT:
        caption, continuation = postformat.split_for_photo(
            formatted, caption_limit=telegram.CAPTION_LIMIT,
            message_limit=telegram.MESSAGE_SAFE_LIMIT, render=postformat.to_markdownv2,
        )
        if caption is None or continuation is None:
            st.record_facts(mid, facts)
            st.record_image_rights(mid, image)
            st.update(mid, status="review", reason="telegram_layout_invalid")
            return dict(out, reason="telegram_layout_invalid")
    st.update(mid, status="post_ready", post_text=rendered, image_url=image["url"],
              classification="pets:%s:%s" % (topic.category, topic.species),
              reason="pets_expert:external_facts")
    st.enqueue_verified_material(mid)
    return dict(out, status="post_ready", material_id=mid, category=topic.category, species=topic.species)


def topic_from_candidate(candidate):
    """Build a topic only from the candidate's audited editorial metadata."""
    species = candidate.get("species")
    if species not in {"cat", "dog"}:
        return None
    category = str(candidate.get("category") or "facts").strip() or "facts"
    key = str(candidate.get("topic_key") or candidate.get("source_key") or "").strip()
    title = str(candidate.get("title") or "Проверенный факт для владельцев").strip()
    if not key:
        return None
    return Topic(key, title, category, species, (species, "home", "owner"))


def replenish_verified_queue(st, candidates, generator=None, image_resolver=None,
                             target_ready=7, replenish_below=5):
    """Turn editorially-ready factual briefs into queued drafts.

    It has no Telegram side effect.  Real production still needs the separate
    publisher gate, durable state and PETS_PUBLISH=1.  Mock text remains
    ``review`` and can never enter the queue.
    """
    before = st.queued_count()
    result = {"queue_before": before, "queue_after": before, "target_ready": target_ready,
              "replenish_below": replenish_below, "checked": 0, "post_ready": 0,
              "review": 0, "rejected": 0, "skipped": 0, "blocked": ""}
    if before >= replenish_below:
        result["blocked"] = "queue_above_replenish_threshold"
        return result
    for candidate in candidates or ():
        if st.queued_count() >= target_ready:
            break
        result["checked"] += 1
        if candidate.get("editorial_status") != "editorially_ready":
            result["review"] += 1
            continue
        topic = topic_from_candidate(candidate)
        if topic is None:
            result["review"] += 1
            continue
        item = process_fact_material(st, topic, candidate.get("facts", ()), candidate.get("source_id", ""),
                                     generator=generator, image_resolver=image_resolver)
        status = item.get("status", "review")
        result[status if status in result else "review"] += 1
    result["queue_after"] = st.queued_count()
    if result["queue_after"] < target_ready and not result["blocked"]:
        result["blocked"] = "insufficient_verified_factual_briefs"
    return result


def process_queued_material(st, row, *, publish=False, dry_run=True, checkpoint=None):
    """Deliver one database-approved factual draft without a Python id allowlist.

    ``pets_publication_queue`` is the authority.  Demo/curated rows never
    appear in it, and all durable-state and exactly-once protections remain
    identical to the established evergreen sender.
    """
    mid = row.get("id")
    out = {"source": row.get("source"), "material_id": mid, "status": "post_ready", "reason": ""}
    if not mid or row.get("queue_status") != "ready" or row.get("source") == "curated_original":
        return dict(out, status="rejected", reason="queue_entry_not_publishable")
    if not (publish and not dry_run):
        return out
    if config.PETS_REQUIRE_DURABLE_STATE and config.PETS_STATE_BACKEND != "github":
        st.queue_mark(mid, "review", "durable_state_required")
        return dict(out, status="review", reason="durable_state_required")
    try:
        photo = httpclient.fetch_bytes(row.get("image_url") or "")
    except Exception:
        st.queue_mark(mid, "review", "image_download_failed")
        return dict(out, status="review", reason="image_download_failed")
    if not st.claim_for_publish(mid):
        st.queue_mark(mid, "review", "publish_claim_lost")
        return dict(out, status="review", reason="publish_claim_lost")
    st.queue_mark(mid, "claimed")
    try:
        if checkpoint:
            checkpoint("claimed")
    except Exception:
        st.release_claim(mid, "review", "durable_state_checkpoint_failed_before_send")
        st.queue_mark(mid, "review", "durable_state_checkpoint_failed_before_send")
        return dict(out, status="review", reason="durable_state_checkpoint_failed_before_send")
    try:
        sent = telegram.publish_post(row.get("post_text") or "", dry_run=False,
                                      channel="pets", image=photo)
    except Exception:
        sent = None
    if not sent or not sent.ok:
        st.release_claim(mid, "review", "telegram_delivery_uncertain")
        st.queue_mark(mid, "review", "telegram_delivery_uncertain")
        return dict(out, status="review", reason="telegram_delivery_uncertain")
    st.mark_pets_published(mid, sent.message_id,
                           case_model.case_id_for(row.get("url") or "", row.get("post_text", "")[:2000]))
    st.publish_topic(mid)
    st.queue_mark(mid, "published")
    try:
        if checkpoint:
            checkpoint("published")
    except Exception:
        return dict(out, status="published", telegram_message_id=sent.message_id,
                    durable_state="checkpoint_failed_after_send")
    return dict(out, status="published", telegram_message_id=sent.message_id)


def run_autonomous_dry_run(st, adapters, generator=None, image_resolver=None, limit=10):
    """Offline-friendly PETS 3.1 orchestrator; it can never send Telegram."""
    summary = {"planned": 0, "checked": 0, "post_ready": 0, "review": 0, "rejected": 0,
               "skipped": 0, "published": 0, "dry_run": True, "source_errors": {},
               "source_report": {}, "generator_mode": getattr(generator or MockPetsGenerator(), "mode", "unknown")}
    topics = choose_topics(st, limit=limit)
    summary["planned"] = len(topics)
    for source_id, adapter in (adapters or {}).items():
        try:
            gathered = list(adapter.collect())
            summary["source_report"][source_id] = {"status": "ok", "facts": len(gathered)}
        except Exception as exc:
            summary["source_errors"][source_id] = type(exc).__name__
            summary["source_report"][source_id] = {"status": "error", "error": type(exc).__name__}
            continue
        for facts in gathered:
            if not topics:
                break
            topic = topics.pop(0)
            result = process_fact_material(st, topic, facts, source_id, generator=generator,
                                           image_resolver=image_resolver)
            summary["checked"] += 1
            status = result.get("status", "review")
            if status in summary:
                summary[status] += 1
    return summary


def run(dry_run=True, publish=False, sources=None, st=None, adapters=None,
        image_resolver=None, provider=None, checkpoint=None, briefs=(), evergreen_briefs=()):
    st = st or pets_storage.PetsStorage(config.PETS_DB_PATH)
    st.quarantine_stale_claims()
    source_ids = sources if sources is not None else config.PETS_SOURCES
    adapters = adapters or {}
    if image_resolver is None and config.PETS_IMAGE_PROVIDER == "wikimedia":
        image_resolver = pets_images.resolve_wikimedia_commons
    published_today = st.pets_published_today()
    allow_publish = publish and config.PETS_PUBLISH and published_today < 1
    summary = {"checked": 0, "post_ready": 0, "published": 0, "rejected": 0,
               "review": 0, "failed": 0, "skipped": 0,
               "dry_run": dry_run or not allow_publish, "sources": list(source_ids),
               "reason_counts": {}, "ready_material_ids": [], "demo_ready": 0,
               "published_today": published_today,
               "daily_publish_blocked": bool(publish and config.PETS_PUBLISH and published_today >= 1)}
    published = 0
    for brief in evergreen_briefs or ():
        result = process_evergreen_brief(st, brief, publish=allow_publish and published < config.PETS_PUBLISH_LIMIT,
                                         dry_run=dry_run, checkpoint=checkpoint)
        summary["checked"] += 1
        status = result.get("status", "skipped")
        if status in summary:
            summary[status] += 1
        if status == "published":
            published += 1
    # Factual drafts use a SQLite production gate, not a hard-coded Python
    # allowlist.  They are considered only when all normal publication flags
    # were explicitly enabled by the owner.
    for row in st.queued_materials(limit=max(config.PETS_PUBLISH_LIMIT - published, 0)):
        if published >= config.PETS_PUBLISH_LIMIT:
            break
        result = process_queued_material(st, row,
                                         publish=allow_publish and published < config.PETS_PUBLISH_LIMIT,
                                         dry_run=dry_run, checkpoint=checkpoint)
        summary["checked"] += 1
        status = result.get("status", "skipped")
        if status in summary:
            summary[status] += 1
        if status == "published":
            published += 1
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
