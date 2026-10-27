# -*- coding: utf-8 -*-
"""Prepare PETS post previews from verified factual-brief artifacts.

This module is intentionally separate from the publishing pipeline: it never
opens ``PetsStorage``, sends Telegram messages, or writes to a PETS SQLite
database.  Publication history, when supplied, is opened through SQLite's
read-only URI mode only.
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from urllib.parse import urlparse

from . import pets_images
from .pets_facts import Fact, validate_fact_set, validate_generated_text
from .pets_generator import GigaChatPetsGenerator, factual_brief_prompt


_DOI_RE = re.compile(r"^10\.\d{4,9}/[-._;()/:a-z0-9]+$", re.I)
_WORD_RE = re.compile(r"[a-zа-яё0-9]{4,}", re.I)
_TOPIC_VISUALS = (
    (("outdoor", "wildlife", "hunting", "explor"), "outdoor"),
    (("play", "enrichment", "toy"), "enrichment"),
    (("groom", "brush", "coat"), "grooming"),
    (("feeding", "food", "diet", "nutrition"), "food"),
    (("walk", "leash", "exercise"), "walk"),
    (("home", "indoor", "household"), "home"),
)


def _as_tuple(value):
    return tuple(str(item).strip() for item in (value or ()) if str(item).strip())


def _fact_from_json(value):
    if not isinstance(value, dict):
        raise ValueError("fact_contract_invalid")
    fields = {name: value.get(name) for name in Fact.__dataclass_fields__}
    return Fact(**fields)


def _candidate_to_brief(candidate):
    """Convert one editorially-ready JSON candidate to the internal contract."""
    if not isinstance(candidate, dict):
        raise ValueError("candidate_not_object")
    if candidate.get("editorial_status") != "editorially_ready":
        raise ValueError("candidate_not_editorially_ready")
    doi = str(candidate.get("doi") or "").strip()
    source_key = str(candidate.get("source_key") or "").strip()
    if doi and not _DOI_RE.fullmatch(doi):
        raise ValueError("candidate_doi_invalid")
    if not doi and not source_key:
        raise ValueError("candidate_identifier_missing")
    source_url = str(candidate.get("source_url") or "").strip()
    parsed = urlparse(source_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("candidate_source_url_invalid")
    if not candidate.get("adaptation_allowed"):
        raise ValueError("candidate_adaptation_not_allowed")
    limitations = _as_tuple(candidate.get("limitations"))
    if not limitations:
        raise ValueError("candidate_limitations_missing")
    facts = tuple(_fact_from_json(value) for value in candidate.get("facts", ()))
    if len(facts) < 3:
        raise ValueError("candidate_insufficient_facts")
    facts_ok, reason = validate_fact_set(facts)
    if not facts_ok:
        raise ValueError("candidate_facts_invalid:%s" % reason)
    topic = str(candidate.get("title") or candidate.get("topic") or "").strip()
    if not topic:
        raise ValueError("candidate_topic_missing")
    return {
        "topic": topic,
        "doi": doi.lower(),
        "source_identity": doi.lower() or source_key.lower(),
        "source_url": source_url,
        "facts": facts,
        "limitations": limitations,
        "allowed_conclusions": _as_tuple(candidate.get("allowed_conclusions")) or (
            "describe only the studied observation", "state that the result is not a universal rule",
        ),
        "forbidden_conclusions": _as_tuple(candidate.get("forbidden_conclusions")) or (
            "causal conclusions", "medical advice", "new numerical norms",
        ),
        "attribution_requirements": str(candidate.get("attribution_requirements") or
                                          facts[0].attribution_requirements or "credit author, source and licence"),
        "species": str(candidate.get("species") or facts[0].species),
        "category": str(candidate.get("category") or ""),
        "source_key": source_key or doi.lower(),
        "image_query": str(candidate.get("image_query") or "").strip(),
        "visual_tags": _as_tuple(candidate.get("visual_tags")),
    }


def load_editorial_briefs(path, *, max_previews=3):
    """Load up to three real editorial briefs and record every rejection.

    The source artifact is never changed.  Invalid or non-editorial material is
    rejected rather than promoted or supplemented with demo content.
    """
    if not 1 <= int(max_previews) <= 3:
        raise ValueError("max_previews must be in 1..3")
    source = Path(path)
    payload = json.loads(source.read_text(encoding="utf-8"))
    candidates = payload.get("candidates") if isinstance(payload, dict) else None
    if not isinstance(candidates, list):
        raise ValueError("factual_brief_artifact_has_no_candidates")
    accepted, rejected, seen = [], [], set()
    for raw in candidates:
        identity = str((raw or {}).get("doi") or (raw or {}).get("source_key") or "unknown")
        try:
            brief = _candidate_to_brief(raw)
            if brief["source_identity"] in seen:
                raise ValueError("candidate_duplicate_source")
            seen.add(brief["source_identity"])
            if len(accepted) < int(max_previews):
                accepted.append(brief)
            else:
                rejected.append({"identity": identity, "reason": "preview_limit_reached"})
        except (TypeError, ValueError) as exc:
            rejected.append({"identity": identity, "reason": str(exc)})
    return accepted, rejected, {"artifact": str(source), "input_candidates": len(candidates),
                                 "accepted": len(accepted), "rejected": len(rejected)}


def _read_only_connection(path):
    resolved = Path(path).resolve()
    return sqlite3.connect(resolved.as_uri() + "?mode=ro", uri=True)


def read_published_history(path):
    """Read known PETS publications without creating, migrating, or writing a DB."""
    if not path:
        return {"status": "not_configured", "urls": (), "texts": (), "dois": ()}
    db_path = Path(path)
    if not db_path.exists():
        return {"status": "missing", "urls": (), "texts": (), "dois": ()}
    try:
        with _read_only_connection(db_path) as db:
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            urls, texts = [], []
            if "materials" in tables:
                cols = {row[1] for row in db.execute("PRAGMA table_info(materials)")}
                if {"canonical_url", "post_text", "status"}.issubset(cols):
                    rows = db.execute("SELECT canonical_url,post_text FROM materials WHERE status='published'").fetchall()
                    urls.extend(row[0] for row in rows if row[0])
                    texts.extend(row[1] for row in rows if row[1])
            if "publications" in tables:
                cols = {row[1] for row in db.execute("PRAGMA table_info(publications)")}
                if "source_url" in cols:
                    urls.extend(row[0] for row in db.execute("SELECT source_url FROM publications WHERE ok=1") if row[0])
        all_text = "\n".join(texts + urls)
        return {"status": "read_only", "urls": tuple(sorted(set(urls))), "texts": tuple(texts),
                "dois": tuple(sorted(set(re.findall(r"10\.\d{4,9}/[-._;()/:a-z0-9]+", all_text, re.I))))}
    except sqlite3.Error as exc:
        return {"status": "unavailable", "reason": "sqlite_read_error:%s" % type(exc).__name__,
                "urls": (), "texts": (), "dois": ()}


def _similarity(left, right):
    a, b = set(_WORD_RE.findall((left or "").lower())), set(_WORD_RE.findall((right or "").lower()))
    return len(a & b) / max(1, len(a | b))


def duplicate_check(brief, text, history):
    if history.get("status") != "read_only":
        return False, "history_%s" % history.get("status", "unavailable")
    if brief.get("doi") and brief["doi"].lower() in {value.lower() for value in history.get("dois", ())}:
        return True, "published_doi"
    if brief["source_url"] in set(history.get("urls", ())):
        return True, "published_source_url"
    if any(_similarity(text, prior) >= .72 for prior in history.get("texts", ())):
        return True, "published_text_similarity"
    return False, "not_duplicate"


def visual_contract(brief):
    explicit_tags = _as_tuple(brief.get("visual_tags"))
    if explicit_tags:
        return {"image_query": str(brief.get("image_query") or brief["topic"]), "visual_tags": explicit_tags}
    combined = (brief["topic"] + " " + " ".join(f.claim for f in brief["facts"])).lower()
    species = "cat" if brief.get("species") == "cat" else "dog" if brief.get("species") == "dog" else ""
    for words, tag in _TOPIC_VISUALS:
        if any(word in combined for word in words) and species:
            return {"image_query": "domestic %s %s" % (species, tag.replace("_", " ")),
                    "visual_tags": (species, tag)}
    return {"image_query": "", "visual_tags": ()}


def _offline_outline(brief):
    """Safe, source-visible outline; it is never presented as a finished post."""
    facts = "\n".join("• " + fact.claim for fact in brief["facts"])
    title = "Черновик по factual brief: %s" % brief["topic"]
    body = (
        "Офлайн-предпросмотр не переводит и не перефразирует научные утверждения автоматически. "
        "Перед публикацией нужен оригинальный русскоязычный текст и ручная редакционная проверка.\n\n"
        "Проверенные утверждения исходного материала:\n%s\n\n"
        "Ограничения: %s"
    ) % (facts, "; ".join(brief["limitations"]))
    return title, body, "offline_factual_outline"


def _serializable_brief(brief):
    value = dict(brief)
    value["facts"] = [fact.serializable() for fact in brief["facts"]]
    return value


def _source_label(brief):
    return "DOI %s" % brief["doi"] if brief.get("doi") else "Источник без DOI"


def _layout(title, body, brief):
    full = "%s\n\n%s\n\nИсточник: %s — %s" % (title, body, _source_label(brief), brief["source_url"])
    if len(full) <= 1024:
        return {"mode": "photo_with_caption", "caption": full, "continuation": "", "caption_length": len(full)}
    caption = ("%s\n\nИсточник: %s" % (title, _source_label(brief)))[:1024]
    return {"mode": "photo_then_text", "caption": caption, "continuation": full, "caption_length": len(caption)}


def _markdown(payload):
    image = payload.get("image") or {}
    lines = ["# PETS — предпросмотр для ручного утверждения", "",
             "**Статус:** `%s`" % payload["status"], "", "## Пост", "",
             "### %s" % payload["title"], "", payload["body"], "",
             "Источник: %s — [%s](%s)" %
             (_source_label(payload["factual_brief"]), payload["factual_brief"]["source_url"],
              payload["factual_brief"]["source_url"]), "",
             "## Фото", ""]
    if image:
        lines += ["![Проверенное изображение](%s)" % image["url"], "",
                  "Автор: %s  " % image["author"], "Лицензия: [%s](%s)  " %
                  (image["license"], image["license_url"]), "Атрибуция: %s  " % image["attribution"],
                  "Страница файла: %s" % image["source_url"], ""]
        if payload["image_download"].get("status") != "attached":
            lines += ["Локальный файл не прикреплён; ссылка на изображение не считается вложением.", ""]
    else:
        lines += ["Подходящая фотография не подтверждена; материал остаётся на review.", ""]
    lines += ["## Telegram-предпросмотр", "", "Режим: `%s`; caption: %s символов." %
              (payload["telegram_preview"]["mode"], payload["telegram_preview"]["caption_length"]), "",
              "```text", payload["telegram_preview"]["caption"], "```"]
    if payload["telegram_preview"]["continuation"]:
        lines += ["", "Продолжение отдельным сообщением:", "", "```text",
                  payload["telegram_preview"]["continuation"], "```"]
    lines += ["", "## Причины статуса", ""] + ["- " + reason for reason in payload["review_reasons"]]
    return "\n".join(lines) + "\n"


def _cached_text(precomputed_texts, brief):
    value = (precomputed_texts or {}).get(brief["source_identity"])
    if not isinstance(value, dict):
        return None
    title = str(value.get("title") or "").strip().lstrip("#").strip()
    body = str(value.get("body") or "").strip()
    return (title, body) if title and body else None


def build_previews(candidates_path, output_dir, *, history_db_path=None, max_previews=3,
                   use_live_gigachat=False, owner_approved=False, max_gigachat_calls=1,
                   generator=None, image_resolver=None, image_downloader=None, download_images=False,
                   precomputed_texts=None, image_overrides=None):
    """Create up to three isolated preview artifacts from real factual briefs."""
    if not 0 <= int(max_gigachat_calls) <= 3:
        raise ValueError("max_gigachat_calls must be in 0..3")
    briefs, rejected, loading = load_editorial_briefs(candidates_path, max_previews=max_previews)
    history = read_published_history(history_db_path)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    resolver = image_resolver or pets_images.resolve_wikimedia_commons
    generated, calls = [], 0
    for index, brief in enumerate(briefs, 1):
        facts_ok, facts_reason = validate_fact_set(brief["facts"])
        title, body, origin = _offline_outline(brief)
        generation_status = "offline_outline"
        cached = _cached_text(precomputed_texts, brief)
        if cached:
            title, body = cached
            origin, generation_status = "gigachat_cached", "reused_verified_prior_result"
        elif use_live_gigachat and owner_approved and calls < int(max_gigachat_calls):
            result = (generator or GigaChatPetsGenerator(None, enabled=False)).generate_factual_brief(brief)
            calls += 1
            if result:
                title, _, body = result["text"].partition("\n")
                body, origin, generation_status = body.strip(), "gigachat", "completed"
            else:
                generation_status = "generation_failed"
        elif use_live_gigachat and not owner_approved:
            generation_status = "awaiting_explicit_owner_approval"
        elif use_live_gigachat:
            generation_status = "gigachat_call_limit_reached"
        contract = visual_contract(brief)
        override = (image_overrides or {}).get(brief["source_identity"])
        image = override if isinstance(override, dict) else (
            resolver("pets-3-3:%s" % brief["source_identity"], {"title": title, "text": body, **contract})
            if contract["visual_tags"] else None)
        image_ok, image_reason = pets_images.validate_image(image, title)
        text_ok, text_reason = (
            validate_generated_text("%s\n%s" % (title, body), brief["facts"], citation_text=brief["source_url"],
                                    allowed_source_urls=(brief["source_url"],))
            if origin in {"gigachat", "gigachat_cached"} else (False, "offline_outline_requires_editorial_text"))
        duplicate, duplicate_reason = duplicate_check(brief, "%s\n%s" % (title, body), history)
        post_dir = out / ("%02d_%s" % (index, re.sub(r"[^a-z0-9]+", "-", brief["source_identity"].lower()).strip("-")))
        post_dir.mkdir(parents=True, exist_ok=True)
        image_download = {"status": "not_requested"}
        if image_ok and download_images:
            bytes_value, image_download = (image_downloader or pets_images.download_preview_image)(image)
            if bytes_value:
                selected_url = image_download.get("url") or image.get("url")
                suffix = Path(urlparse(selected_url).path).suffix or ".jpg"
                target = post_dir / ("photo" + suffix)
                target.write_bytes(bytes_value)
                image, image_download = dict(image, local_file=target.name), dict(image_download, file=target.name)
        review_reasons = []
        if not facts_ok:
            review_reasons.append("factual_brief:%s" % facts_reason)
        if not text_ok:
            review_reasons.append("text:%s" % text_reason)
        if not image_ok:
            review_reasons.append("image:%s" % image_reason)
        if download_images and image_download.get("status") != "attached":
            review_reasons.append("image:%s" % image_download.get("status"))
        if duplicate:
            review_reasons.append("duplicate:%s" % duplicate_reason)
        if history.get("status") != "read_only":
            review_reasons.append("history:%s" % duplicate_reason)
        status = "ready_for_manual_approval" if not review_reasons else "review"
        validation = {"factual_brief_ok": facts_ok, "factual_brief_reason": facts_reason,
                      "text_ok": text_ok, "text_reason": text_reason, "image_ok": image_ok,
                      "image_reason": image_reason, "image_download_status": image_download.get("status"),
                      "image_local_file": bool(image and image.get("local_file")),
                      "duplicate": duplicate, "duplicate_reason": duplicate_reason,
                      "manual_review_required": True, "history_mode": history.get("status")}
        payload = {"status": status, "title": title.strip(), "body": body.strip(),
                   "factual_brief": _serializable_brief(brief), "text_origin": origin,
                   "gigachat": {"calls": 1 if origin == "gigachat" else 0, "owner_approved": bool(owner_approved),
                                "status": generation_status, "max_calls": int(max_gigachat_calls),
                                "prompt": factual_brief_prompt(brief)}, "image": image if image_ok else None,
                   "image_download": image_download, "validation": validation, "review_reasons": review_reasons,
                   "telegram_preview": _layout(title, body, brief), "telegram_sent": False, "pets_publish": False}
        (post_dir / "pets_post_preview.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        (post_dir / "pets_post_validation.json").write_text(json.dumps(validation, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        (post_dir / "pets_post_preview.md").write_text(_markdown(payload), encoding="utf-8")
        generated.append({"doi": brief.get("doi") or None, "source_key": brief["source_key"], "status": status, "directory": post_dir.name,
                          "review_reasons": review_reasons})
    manifest = {"mode": "universal_factual_brief_preview", "loading": loading, "history": {"status": history.get("status")},
                "posts": generated, "rejected_briefs": rejected, "gigachat_calls": calls,
                "telegram_sent": False, "pets_publish": False}
    (out / "pets_universal_preview.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    (out / "pets_universal_preview_diagnostics.json").write_text(json.dumps({"history": history.get("status"),
        "gigachat_calls": calls, "posts": len(generated), "rejected_briefs": rejected, "telegram_sent": False},
        ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return manifest
