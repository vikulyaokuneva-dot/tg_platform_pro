# -*- coding: utf-8 -*-
"""PETS 3.2 single-post preview, deliberately isolated from publishing state."""
import json
import re
from pathlib import Path

from . import httpclient, pets_images
from .pets_facts import Fact, validate_fact_set
from .pets_generator import GigaChatPetsGenerator, factual_brief_prompt


POST_DOI = "10.3390/ani16172777"
POST_URL = "https://pmc.ncbi.nlm.nih.gov/articles/PMC13565001/"
POST_TITLE = "Отношения с кошкой и прогулки: почему нет одного правила для всех"
POST_BODY = (
    "Исследование о домашних кошках показало: связь между отношениями владельца с кошкой и "
    "её исследовательским или охотничьим поведением нельзя свести к простой закономерности. "
    "Авторы не нашли подтверждения, что более тесная связь сама по себе объясняет, как кошка ведёт себя на улице.\n\n"
    "При этом поведение, связанное с охотой, заметно различалось между отдельными кошками. "
    "Исследовательские действия оказались более похожими друг на друга, чем охотничьи. "
    "Поэтому полезнее наблюдать за конкретной кошкой и её средой, а не ждать одинаковой реакции от всех животных.\n\n"
    "Это результаты одного опросного исследования в конкретной группе животных. Они показывают связь и различия, "
    "но не устанавливают причинную связь между отношениями с владельцем и определённым поведением."
)


def factual_brief():
    """Return the PETS 3.1.3 brief as structured, source-traceable facts."""
    meta = dict(topic="Отношения владельца с кошкой и поведение кошки на улице", species="cat",
                source_url=POST_URL, source_name="PubMed Central Open Access",
                source_type="primary_research", author_or_body="Schüttler et al.",
                published_at="2026", license="CC_BY", adaptation_allowed=True,
                evidence_level="primary_research", license_source_url="https://creativecommons.org/licenses/by/4.0/",
                attribution_requirements="credit author, source and licence",
                source_section="discussion", fact_kind="study_discussion")
    claims = (
        "The study found no evidence of a negative correlation between the cat-owner relationship and video-evidenced exploration or hunting behaviours.",
        "Individual variability in the frequency of hunting-related behaviours was a significant result in the study.",
        "Exploration patterns were relatively uniform compared with hunting behaviours in the studied cats.",
        "Cats whose owners reported hunting showed higher exploratory behaviour; this is an observed association, not proof of causation.",
    )
    facts = tuple(Fact(claim=claim, **meta) for claim in claims)
    return {
        "topic": meta["topic"], "doi": POST_DOI, "source_url": POST_URL,
        "facts": facts, "limitations": (
            "The selected source is study-specific and is not a universal owner recommendation.",
            "The design is a survey; observed associations do not establish causation.",
        ),
        "allowed_conclusions": (
            "cat behaviour outdoors varies between individuals",
            "the studied association must not be presented as causation",
            "owners should avoid assuming one universal pattern for all cats",
        ),
        "forbidden_conclusions": (
            "a stronger owner-cat bond causes a particular outdoor behaviour",
            "medical, treatment or safety guarantees",
            "new statistics or numerical norms",
        ),
        "attribution_requirements": meta["attribution_requirements"],
    }


def _plain_serializable(brief):
    return dict(brief, facts=[fact.serializable() for fact in brief["facts"]])


def _known_demo_texts():
    # No production SQLite is read: preview uniqueness is a conservative local
    # comparison only and remains subject to manual confirmation.
    from .pets_briefs import DEFAULT_BRIEFS
    return [str(item.get("body") or "") for item in DEFAULT_BRIEFS]


def _similarity(a, b):
    left, right = set(re.findall(r"[а-яёa-z]{4,}", a.lower())), set(re.findall(r"[а-яёa-z]{4,}", b.lower()))
    return len(left & right) / max(1, len(left | right))


def validate_post(title, body, brief, *, origin):
    """Deterministic checks; pass still means *manual* approval is required."""
    full = "%s\n\n%s\n\nИсточник: DOI %s — %s" % (title, body, brief["doi"], brief["source_url"])
    lower = full.lower()
    checks = {
        "title_present": len(title.strip()) >= 12,
        "russian_text": len(re.findall(r"[а-яё]", lower)) >= 80,
        "source_and_doi": brief["doi"] in full and brief["source_url"] in full,
        "no_medical_advice": not any(term in lower for term in ("назнач", "дозиров", "лечит", "препарат", "диагноз")),
        "no_causal_claim": not any(term in lower for term in ("вызывает", "приводит к", "гарантирует")),
        "limitation_stated": "не устанавливают причинную связь" in lower or "не является универсальным" in lower,
        "original_vs_demo": max((_similarity(full, text) for text in _known_demo_texts()), default=0) < .45,
        "source_licence": all(fact.adaptation_allowed and fact.license == "CC_BY" for fact in brief["facts"]),
    }
    return {
        "ok": all(checks.values()), "checks": checks, "text_origin": origin,
        "manual_review_required": True,
        "uniqueness_scope": "bundled PETS demo briefs only; durable publication history requires owner review",
    }


def _telegram_layout(title, body, brief):
    full = "%s\n\n%s\n\nИсточник: DOI %s — %s" % (title, body, brief["doi"], brief["source_url"])
    if len(full) <= 1024:
        return {"mode": "photo_with_caption", "caption": full, "continuation": "", "caption_length": len(full)}
    caption = "%s\n\nИсточник: DOI %s" % (title, brief["doi"])
    return {"mode": "photo_then_text", "caption": caption[:1024], "continuation": full,
            "caption_length": len(caption[:1024])}


def _render_markdown(payload):
    image = payload.get("image") or {}
    layout = payload["telegram_preview"]
    facts = payload["factual_brief"]["facts"]
    lines = ["# PETS — preview для ручного утверждения", "", "**Статус:** `%s`" % payload["status"], "",
             "## Пост", "", "### %s" % payload["title"], "", payload["body"], "",
             "Источник: DOI [%s](https://doi.org/%s) — [%s](%s)" %
             (payload["factual_brief"]["doi"], payload["factual_brief"]["doi"],
              payload["factual_brief"]["source_url"], payload["factual_brief"]["source_url"]), "",
             "## Фотография", ""]
    if image:
        lines += ["![Проверенная фотография кошки на улице](%s)" % image["url"], "",
                  "Автор: %s  " % image["author"], "Лицензия: [%s](%s)  " % (image["license"], image["license_url"]),
                  "Атрибуция: %s  " % image["attribution"], "Страница файла: %s" % image["source_url"], ""]
    else:
        lines += ["Подходящее изображение не найдено: публикация остаётся на review.", ""]
    lines += ["## Telegram-предпросмотр", "", "Режим: `%s`; caption: %s символов." %
              (layout["mode"], layout["caption_length"]), "", "```text", layout["caption"], "```"]
    if layout["continuation"]:
        lines += ["", "Продолжение отдельным сообщением:", "", "```text", layout["continuation"], "```"]
    lines += ["", "## Проверенные факты", ""]
    for fact in facts:
        lines.append("- %s (%s)" % (fact["claim"], fact["source_section"]))
    lines += ["", "## Ограничения", ""] + ["- " + item for item in payload["factual_brief"]["limitations"]]
    return "\n".join(lines) + "\n"


def build_preview(output_dir, *, use_live_gigachat=False, owner_approved=False, generator=None, image_resolver=None,
                  download_image=False):
    """Create files only. This function contains no Telegram or SQLite calls."""
    brief = factual_brief()
    facts_ok, facts_reason = validate_fact_set(brief["facts"])
    prompt = factual_brief_prompt(brief)
    title, body, origin, gigachat_calls = POST_TITLE, POST_BODY, "offline_factual_draft", 0
    generation_status = "not_requested"
    if use_live_gigachat:
        if not owner_approved:
            generation_status = "awaiting_explicit_owner_approval"
        else:
            result = (generator or GigaChatPetsGenerator(None, enabled=False)).generate_factual_brief(brief)
            gigachat_calls = 1
            if result:
                title, _, body = result["text"].partition("\n")
                body = body.strip()
                origin, generation_status = "gigachat", "completed"
            else:
                generation_status = "generation_failed"
    resolver = image_resolver or pets_images.resolve_wikimedia_commons
    image = resolver("pets-3-2", {"title": title, "text": body, "image_query": "domestic cat outdoors",
                                   "visual_tags": ("cat", "outdoor")})
    image_ok, image_reason = pets_images.validate_image(image, title)
    validation = validate_post(title, body, brief, origin=origin)
    validation.update({"factual_brief_ok": facts_ok, "factual_brief_reason": facts_reason,
                       "image_ok": image_ok, "image_reason": image_reason,
                       "gigachat_generation_status": generation_status, "gigachat_calls": gigachat_calls})
    status = "ready_for_manual_approval" if validation["ok"] and facts_ok and image_ok else "review"
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    image_download = {"status": "not_requested"}
    if image_ok and download_image:
        try:
            target = out / "pets_post_photo.jpg"
            target.write_bytes(httpclient.fetch_bytes(image["url"]))
            image = dict(image, local_file=target.name)
            image_download = {"status": "attached", "file": target.name}
        except Exception:
            image_download = {"status": "not_attached: download_failed"}
    payload = {"status": status, "title": title, "body": body, "factual_brief": _plain_serializable(brief),
               "gigachat": {"calls": gigachat_calls, "max_calls": 1, "owner_approved": bool(owner_approved),
                             "status": generation_status, "prompt": prompt},
               "image": image if image_ok else None, "image_download": image_download,
               "telegram_preview": _telegram_layout(title, body, brief), "validation": validation,
               "telegram_sent": False, "pets_publish": False}
    (out / "pets_post_preview.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    (out / "pets_post_validation.json").write_text(json.dumps(validation, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    (out / "pets_post_preview.md").write_text(_render_markdown(payload), encoding="utf-8")
    diagnostics = {"status": status, "telegram_sent": False, "gigachat_calls": gigachat_calls,
                   "image_url": (payload.get("image") or {}).get("url", ""), "output_dir": str(out)}
    (out / "pets_post_diagnostics.json").write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload
