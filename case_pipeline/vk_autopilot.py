# -*- coding: utf-8 -*-
"""VK queue orchestration and a conservative VK-specific AGRO editor.

Only a post that has already passed AGRO classification, evidence and
editorial gates is eligible.  Telegram status/history is deliberately never
modified here.
"""
import logging
import re

from . import ai, config, httpclient, storage as storage_mod
from .utils import digits_of, extract_numbers
from .vk_publisher import VkPublisher

log = logging.getLogger("case_pipeline.vk_autopilot")
_SOURCE_RX = re.compile(r"^Источник\s*:\s*(\S+)", re.I)
_TAGS_RX = re.compile(r"^(?:#\S+\s*)+$")
_EMOJI_RX = re.compile(r"^[\U0001F000-\U0001FAFF\u2600-\u27bf\u2b00-\u2bff\ufe0f\s]+")
_WORD_RX = re.compile(r"[А-Яа-яЁёA-Za-z]{4,}")
_MD_BOLD_RX = re.compile(r"\*\*([^*]+)\*\*")
_MD_ITALIC_RX = re.compile(r"(?<!\w)_([^_\n]+)_(?!\w)")
# A source-grounded recommendation is copied verbatim into VK; these are
# deliberately narrow cues for an instruction, warning or concrete action.
_ACTION_STEM_RX = (r"убир|убра|собир|сохра|мульч|провер|выбир|использ|саж|полив|"
                   r"укры|обрез|просуш|хран|внос|перевод|звон|обработ|очищ|"
                   r"сним|избег|ориентир")
_RECOMMENDATION_RX = re.compile(
    r"\bне\s+(?:нужно|стоит|следует)\b|\b(?:лучше|следует|"
    r"рекомендуется|совету(?:ет|ют))\b|\b(?:можно|достаточно|важно)\b"
    r"[^.!?]{0,140}\b(?:" + _ACTION_STEM_RX + r")\w*\b|"
    r"\b(?:" + _ACTION_STEM_RX + r")\w*\s+(?:можно|стоит)\b|"
    r"\b(?:" + _ACTION_STEM_RX + r")\w*(?:йте|йте?сь)\b", re.I)
_AI_IMPERATIVE_RX = re.compile(r"\b[А-Яа-яЁё]{4,}(?:айте|яйте|уйте|ите|ьте)(?:сь)?\b", re.I)
# Informative, but not necessarily imperative, statements that can still make
# a source post useful (scenario C).  One vague topical word is not enough.
_PRACTICAL_FACT_RX = re.compile(
    r"\b(?:посад|пересад|полив|подкорм|обрез|укры|мульч|хран|просуш|"
    r"почв|грунт|корн|листь|луковиц|семян|рассад|вредител|болезн|"
    r"температур|мороз|замороз|цветен|кормлен|сено|ветеринар|чеснок|"
    r"землян|пион|гиппеаструм|белокрылк|таракан|листв|черв)\w*\b",
    re.I)
_CONDITION_RX = re.compile(r"\b(?:если|когда|при|до|после|перед|пока|чтобы|"
                           r"сначала|затем|раньше|позже|обычно|"
                           r"недел|месяц|дн(?:я|ей)|°C)\b", re.I)
_LEADING_EMOJI_RX = re.compile(r"^[\U0001F000-\U0001FAFF\u2600-\u27bf\u2b00-\u2bff\ufe0f\s]+")
_TECHNICAL_RUBRICS = tuple(sorted((
    "Технологии выращивания", "Болезни и вредители", "Растения и сорта",
    "Агроавтоматизация", "Погода и сезон", "Сад и огород", "Фермерство",
    "Агробизнес", "Экономика", "Огород", "Техника",
), key=len, reverse=True))
_VK_EMOJI_RULES = (
    (re.compile(r"вредител|тарак|белокрыл|мыш", re.I), "🛡️"),
    (re.compile(r"обрез|секатор", re.I), "✂️"),
    (re.compile(r"полив|влажн|вод", re.I), "💧"),
    (re.compile(r"подкорм|удобрен|фосфор", re.I), "🌿"),
    (re.compile(r"просуш|суш|проветр|хран", re.I), "🌬️"),
    (re.compile(r"осен|зим|листопад|листв|замороз", re.I), "🍂"),
    (re.compile(r"не\s+(?:нужно|стоит|следует)|предупреж|опас|вред", re.I), "⚠️"),
    (re.compile(r"болезн", re.I), "🛡️"),
    (re.compile(r"посад|семян|луков|рассад|выращ|цветен|гиппеастр", re.I), "🌱"),
)

VK_EDITOR_SYSTEM = (
    "Ты — редактор сообщества VK «Сад без хлопот». На основе только "
    "проверенного AGRO-поста подготовь отдельную версию для VK. Не добавляй "
    "никаких фактов, дозировок, сроков, чисел, результатов, личного опыта "
    "или рекомендаций, которых нет во входном тексте. Формат: интересный "
    "заголовок, короткое вступление, 2–4 коротких полезных смысловых блока "
    "с уместными эмодзи. Если в исходнике есть подтверждённый практический "
    "вывод или совет, используй его; если его нет — не придумывай вывод ради "
    "шаблона. Без HTML и Markdown Telegram, "
    "без хэштегов, без вымышленных ссылок. Верни только готовый текст."
)


def _plain(block):
    block = _MD_BOLD_RX.sub(r"\1", block or "")
    block = _MD_ITALIC_RX.sub(r"\1", block)
    return re.sub(r"\s+", " ", block).strip()


def _split_verified_post(post_text):
    source_url = ""
    blocks = []
    for block in (post_text or "").split("\n\n"):
        value = block.strip()
        if not value:
            continue
        source = _SOURCE_RX.match(value)
        if source:
            source_url = source.group(1)
            continue
        if _TAGS_RX.fullmatch(value):
            continue
        blocks.append(_plain(value))
    return blocks, source_url


def _sentences(blocks):
    """Source sentences only; sentence text is never paraphrased into advice."""
    result = []
    for block in blocks:
        start = 0
        quote_depth = 0
        for index, char in enumerate(block):
            if char in "«“":
                quote_depth += 1
            elif char in "»”" and quote_depth:
                quote_depth -= 1
            if (char in ".!?…" and not quote_depth
                    and (index + 1 == len(block) or block[index + 1].isspace())):
                sentence = block[start:index + 1].strip()
                if sentence:
                    result.append(sentence)
                start = index + 1
        tail = block[start:].strip()
        if tail:
            result.append(tail)
    return result


def _normalize_for_match(value):
    value = _plain(value or "")
    value = re.sub(r"[\U0001F000-\U0001FAFF\u2600-\u27bf\u2b00-\u2bff\ufe0f]", "", value)
    return re.sub(r"\s+", " ", value).strip().lower()


def _topic_emoji(text):
    for rx, emoji in _VK_EMOJI_RULES:
        if rx.search(text or ""):
            return emoji
    return "🌿"


def _headline_for_vk(blocks):
    headline = _LEADING_EMOJI_RX.sub("", blocks[0] if blocks else "").strip()
    for rubric in _TECHNICAL_RUBRICS:
        if headline.lower().startswith(rubric.lower()):
            headline = headline[len(rubric):].lstrip(" —–-:.")
            break
    return "%s %s" % (_topic_emoji(headline), headline[:180])


def _remove_duplicate_terminal_advice(parts):
    """Drop an already stated final recommendation; never invent a replacement."""
    content_indexes = [i for i, part in enumerate(parts)
                       if not part.startswith(("Источник:", "Больше практических советов"))]
    if len(content_indexes) < 3:
        return parts
    terminal_index = content_indexes[-1]
    terminal = re.sub(r"^(?:Вывод\s*:\s*)", "",
                      _LEADING_EMOJI_RX.sub("", parts[terminal_index]).strip(), flags=re.I)
    terminal_norm = _normalize_for_match(terminal)
    previous = _normalize_for_match("\n".join(parts[i] for i in content_indexes[:-1]))
    if terminal_norm and terminal_norm in previous:
        return parts[:terminal_index] + parts[terminal_index + 1:]
    return parts


def _source_recommendation(blocks):
    """Return one verbatim, concrete recommendation or an empty string."""
    # The headline can contain an imperative-like word, so only inspect body.
    for sentence in _sentences(blocks[1:]):
        if (20 <= len(sentence) <= 420 and not sentence.endswith("?")
                and _RECOMMENDATION_RX.search(sentence)):
            return sentence
    return ""


def _source_contains_sentence(source, candidate):
    source = _normalize_for_match(source)
    candidate = _normalize_for_match(candidate)
    return bool(candidate) and candidate in source


def _recommendations_are_grounded(candidate, verified):
    """An AI may reformat facts, but a recommendation must remain verbatim."""
    for sentence in _sentences(_split_verified_post(candidate)[0][1:]):
        if (_RECOMMENDATION_RX.search(sentence) or _AI_IMPERATIVE_RX.search(sentence)) \
                and not _source_contains_sentence(verified, sentence):
            return False
    return True


def _conclusions_are_grounded(candidate, verified):
    for block in _split_verified_post(candidate)[0]:
        plain = _EMOJI_RX.sub("", block).strip()
        if re.match(r"^Вывод\s*:", plain, re.I) and not _source_contains_sentence(verified, plain):
            return False
    return True


def _has_practical_value(text):
    """Evidence gate for a post that has no safe final recommendation.

    Two independent source sentences must combine a domain operation with a
    condition, limitation or measurable timing.  This keeps descriptive
    lifestyle/news copy from passing merely because it mentions a garden.
    """
    evidence = 0
    for sentence in _sentences(_split_verified_post(text)[0][1:]):
        if _PRACTICAL_FACT_RX.search(sentence) and _CONDITION_RX.search(sentence):
            evidence += 1
    return evidence >= 2


def _fallback_vk_post(post_text, telegram_url=""):
    """Deterministic VK rendering used when GigaChat is absent or rejected."""
    blocks, source_url = _split_verified_post(post_text)
    if not blocks:
        return ""
    headline = _headline_for_vk(blocks)
    rest = blocks[1:]
    conclusion = ""
    useful = []
    for block in rest:
        no_emoji = _EMOJI_RX.sub("", block).strip()
        if re.match(r"^Вывод\s*:", no_emoji, re.I):
            conclusion = re.sub(r"^Вывод\s*:\s*", "", no_emoji, flags=re.I)
        else:
            useful.append(block)
    source_recommendation = "" if conclusion else _source_recommendation(blocks)
    intro = useful.pop(0) if useful else ""
    # Some older, nevertheless editorially accepted posts contain one very
    # long fact-rich paragraph.  Split only on existing sentence boundaries:
    # this creates readable VK blocks without manufacturing a recommendation.
    if not useful and len(intro) > 160:
        sentences = _sentences([intro])
        if len(sentences) >= 3:
            intro = " ".join(sentences[:2])
            tail = sentences[2:]
            useful = [" ".join(tail[i:i + 2]) for i in range(0, len(tail), 2)]
    parts = [headline]
    if intro:
        parts.append(intro)
    # One themed headline plus at most three themed content blocks keeps the
    # post in the requested 2–4 emoji range without a random sequence.
    for block in useful[:3]:
        if _EMOJI_RX.match(block):
            parts.append(block)
        else:
            parts.append(_topic_emoji(block) + " " + block)
    if conclusion:
        parts.append("🌿 Вывод: " + conclusion)
    elif source_recommendation:
        # Scenario B: an existing recommendation becomes a final practical
        # paragraph verbatim.  No dosage, timing or assertion is invented.
        parts.append("🌿 " + source_recommendation)
    parts = _remove_duplicate_terminal_advice(parts)
    if source_url:
        parts.append("Источник: " + source_url)
    url = (telegram_url or "").strip()
    if url.startswith(("https://t.me/", "https://telegram.me/")):
        parts.append("Больше практических советов — в Telegram: " + url)
    return "\n\n".join(parts).strip()


def _numbers_are_grounded(candidate, verified):
    source_numbers = {digits_of(v) for v in extract_numbers(verified) if digits_of(v)}
    candidate_numbers = {digits_of(v) for v in extract_numbers(candidate) if digits_of(v)}
    return candidate_numbers.issubset(source_numbers)


def _blocks_are_grounded(candidate, verified, telegram_url=""):
    """A conservative lexical check: model blocks must retain source anchors."""
    source_words = {w.lower() for w in _WORD_RX.findall(verified)}
    for block in candidate.split("\n\n"):
        clean = _plain(_EMOJI_RX.sub("", block)).lower()
        if not clean or clean.startswith("больше практических советов"):
            continue
        words = {w.lower() for w in _WORD_RX.findall(clean)}
        if len(words & source_words) < 2:
            return False
    return True


def _safe_ai_vk_post(verified_post, provider, telegram_url=""):
    if provider is None or not getattr(provider, "available", False) or \
            not callable(getattr(provider, "complete", None)):
        return ""
    try:
        raw = provider.complete([
            {"role": "system", "content": VK_EDITOR_SYSTEM},
            {"role": "user", "content": "ПРОВЕРЕННЫЙ AGRO-ПОСТ:\n" + verified_post},
        ])
    except Exception as exc:
        log.warning("VK GigaChat editor failed: %s", type(exc).__name__)
        return ""
    candidate = (raw or "").strip()
    if not candidate or len(candidate) > 5000:
        return ""
    if len([b for b in candidate.split("\n\n") if b.strip()]) < 4:
        return ""
    # A model response with a foreign URL, new numeric value or blocks without
    # source anchors is not trusted; deterministic rendering remains available.
    urls = re.findall(r"https?://\S+", candidate)
    allowed_urls = set(re.findall(r"https?://\S+", verified_post or ""))
    if telegram_url:
        allowed_urls.add(telegram_url.strip())
    if any(url.rstrip(".,)") not in {x.rstrip(".,)") for x in allowed_urls} for url in urls):
        return ""
    if not _numbers_are_grounded(candidate, verified_post):
        return ""
    if not _blocks_are_grounded(candidate, verified_post, telegram_url):
        return ""
    if not _recommendations_are_grounded(candidate, verified_post):
        return ""
    if not _conclusions_are_grounded(candidate, verified_post):
        return ""
    return candidate


def build_vk_post(verified_post, provider=None, telegram_url=None):
    """Returns a VK-native plain-text version, never Telegram HTML."""
    telegram_url = config.VK_TELEGRAM_URL if telegram_url is None else telegram_url
    edited = _safe_ai_vk_post(verified_post, provider, telegram_url)
    if edited:
        edited = "\n\n".join(_remove_duplicate_terminal_advice(
            [part for part in edited.split("\n\n") if part.strip()]))
        if telegram_url and telegram_url.strip() not in edited:
            edited += "\n\nБольше практических советов — в Telegram: " + telegram_url.strip()
        return edited
    return _fallback_vk_post(verified_post, telegram_url)


def vk_post_contract_error(text):
    """VK keeps AGRO's practical-usefulness gate without requiring a label."""
    blocks = [b.strip() for b in (text or "").split("\n\n") if b.strip()]
    if len(blocks) < 4:
        return "VK editor: insufficient paragraph structure"
    useful = []
    has_source_conclusion = False
    for block in blocks[1:]:
        plain = _EMOJI_RX.sub("", block).strip()
        if plain.startswith("Источник:") or plain.startswith("Больше практических советов"):
            continue
        if re.match(r"^Вывод\s*:", plain, re.I):
            has_source_conclusion = True
        useful.append(plain)
    if len(useful) < 2:
        return "VK editor: fewer than two useful blocks"
    # A verbatim recommendation (scenario B) and an existing conclusion
    # (scenario A) are sufficient evidence.  Scenario C needs two separate
    # practical facts, but no manufactured final paragraph.
    if not (has_source_conclusion or _source_recommendation(_split_verified_post(text)[0])
            or _has_practical_value(text)):
        return "VK editor: no verified practical value"
    return ""


def eligible_materials(st):
    """AGRO material is eligible independently of its Telegram result."""
    rows = st.db.execute(
        "SELECT m.* FROM materials m LEFT JOIN vk_publications v ON v.material_id=m.id "
        "WHERE v.id IS NULL AND m.post_text IS NOT NULL AND m.post_text != '' "
        "AND m.status IN ('post_ready', 'published') ORDER BY m.id").fetchall()
    return [dict(row) for row in rows]


def prepared_materials(st):
    """All previously editorially approved AGRO posts, without changing them.

    Telegram may already have published a material: this is intentional.  VK
    has an independent history and can use that verified text once, while a
    pre-existing VK row remains visible to diagnostics and is never queued
    again.
    """
    rows = st.db.execute(
        "SELECT m.*, v.id AS vk_queue_id, v.status AS vk_status, v.error AS vk_error "
        "FROM materials m LEFT JOIN vk_publications v ON v.material_id=m.id "
        "WHERE m.post_text IS NOT NULL AND m.post_text != '' "
        "AND m.status IN ('post_ready', 'published') ORDER BY m.id").fetchall()
    return [dict(row) for row in rows]


def analyze_prepared_materials(st, provider=None):
    """Non-mutating, all-material VK dry-run diagnostic.

    The returned per-item preview is for an operator.  Callers that log it
    should use :func:`aggregate_diagnostics`, which intentionally contains no
    post text, URLs, tokens, or VK API replies.
    """
    report = {"found": 0, "suitable": 0, "rejected": 0,
              "already_queued": 0, "reason_counts": {}, "items": []}
    for row in prepared_materials(st):
        report["found"] += 1
        item = {"material_id": row["id"], "telegram_status": row["status"],
                "source_url": row.get("url") or "", "ready": False,
                "reason": "", "text": "", "image_included": False,
                "image_mode": "image" if config.VK_SOURCE_IMAGES_ALLOWED and row.get("image_url")
                else "text"}
        if row.get("vk_queue_id"):
            item["reason"] = "already in VK queue: %s" % (row.get("vk_status") or "unknown")
            if row.get("vk_error"):
                item["reason"] = row["vk_error"]
            report["already_queued"] += 1
        else:
            item["text"] = build_vk_post(row["post_text"], provider=provider)
            item["reason"] = vk_post_contract_error(item["text"])
            item["ready"] = not bool(item["reason"])
            if item["ready"]:
                report["suitable"] += 1
            else:
                report["rejected"] += 1
        if item["reason"]:
            report["reason_counts"][item["reason"]] = (
                report["reason_counts"].get(item["reason"], 0) + 1)
        report["items"].append(item)
    return report


def aggregate_diagnostics(report):
    """Safe log payload: aggregate decisions only, never content or secrets."""
    return {key: report[key] for key in
            ("found", "suitable", "rejected", "already_queued", "reason_counts")}


def self_check(publisher=None):
    """Read-only credentials/group check.  It never calls upload or wall.post."""
    client = publisher or VkPublisher()
    if not client.configured():
        return {"configured": False, "ok": False, "error_code": None,
                "http_status": None, "error_kind": "credentials_not_configured",
                "response_shape": {"response_present": False, "error_present": False,
                                   "response_type": None, "expected_response_types": ["dict", "list"],
                                   "expected_group_fields": ["id"],
                                   "group_container": None, "direct_id_present": False,
                                   "nested_structure_present": None,
                                   "community_id_match": None,
                                   "response_object_fields": [],
                                   "groups_container": {"present": False, "type": None,
                                                        "first_item_type": None,
                                                        "first_item_has_id": None}}}
    result = client.check_access(require_photo_upload=False)
    shape = {"response_present": False, "error_present": False,
             "response_type": None, "expected_response_types": ["dict", "list"],
             "expected_group_fields": ["id"], "group_container": None,
             "direct_id_present": False, "nested_structure_present": None,
             "community_id_match": None, "response_object_fields": [],
             "groups_container": {"present": False, "type": None,
                                  "first_item_type": None, "first_item_has_id": None}}
    shape.update(result.response_meta or {})
    return {"configured": True, "ok": bool(result.ok),
            "error_code": result.error_code,
            "http_status": result.http_status,
            "error_kind": "ok" if result.ok else (result.error_kind or "unknown"),
            "response_shape": shape}


def enqueue_eligible(st, provider=None):
    created = []
    for row in eligible_materials(st):
        text = build_vk_post(row["post_text"], provider=provider)
        if not text:
            log.warning("vk skip material=%s: cannot build a safe VK post", row["id"])
            continue
        if st.enqueue_vk(row["id"], text, row.get("url") or "", row.get("image_url") or "",
                         image_allowed=config.VK_SOURCE_IMAGES_ALLOWED):
            item = st.vk_by_material(row["id"])
            why = vk_post_contract_error(text)
            if why:
                st.reject_pending_vk(item["id"], why)
                log.warning("vk material=%s rejected: %s", row["id"], why)
            else:
                created.append(item)
    return created


def dry_run_preview(st, provider=None):
    report = analyze_prepared_materials(st, provider=provider)
    return next((item for item in report["items"] if not item["reason"] or item["text"]), None)


def dry_run_all(st, provider=None):
    """Public name for the all-material, status-preserving diagnostic."""
    return analyze_prepared_materials(st, provider=provider)


def run(st=None, dry_run=True, publish=False, provider=None, publisher=None):
    """Processes at most one VK post per UTC date; never raises into AGRO job."""
    st = st or storage_mod.Storage(config.AGRO_DB_PATH)
    provider = provider if provider is not None else ai.get_provider()
    summary = {"enabled": bool(config.VK_PUBLISH), "dry_run": bool(dry_run),
               "queued": 0, "published": 0, "failed": 0, "uncertain": 0,
               "skipped": 0, "preview": None, "error": ""}
    if dry_run or not publish or not config.VK_PUBLISH:
        report = dry_run_all(st, provider)
        summary["diagnostics"] = aggregate_diagnostics(report)
        summary["preview"] = next((item for item in report["items"] if item["ready"]),
                                  report["items"][0] if report["items"] else None)
        return summary

    queued = enqueue_eligible(st, provider)
    summary["queued"] = len(queued)
    if st.vk_published_today() >= config.VK_PUBLISH_LIMIT:
        summary["skipped"] = 1
        summary["error"] = "daily VK publish limit reached"
        return summary
    pending = st.pending_vk(limit=1)
    if not pending:
        summary["skipped"] = 1
        return summary
    item = pending[0]
    client = publisher or VkPublisher()
    access = client.check_access(require_photo_upload=bool(item.get("image_allowed")))
    if not access.ok:
        summary["error"] = access.error
        return summary
    if not st.claim_vk(item["id"]):
        summary["skipped"] = 1
        return summary
    photo = None
    if item.get("image_allowed"):
        try:
            photo = httpclient.fetch_bytes(item.get("image_url") or "")
        except Exception as exc:
            st.fail_vk(item["id"], "image fetch: %s" % type(exc).__name__)
            summary["failed"] = 1
            summary["error"] = "image fetch failed"
            return summary
    result = client.publish(item["vk_text"], photo_bytes=photo, dry_run=False)
    if result.ok:
        st.mark_vk_published(item["id"], result.post_id, result.owner_id)
        summary["published"] = 1
    elif result.uncertain:
        st.keep_vk_uncertain(item["id"], result.error)
        summary["uncertain"] = 1
        summary["error"] = result.error
    else:
        st.fail_vk(item["id"], result.error)
        summary["failed"] = 1
        summary["error"] = result.error
    return summary
