# -*- coding: utf-8 -*-
"""case_pipeline.case_model — структурированный CASE.

CASE строится ДЕТЕРМИНИРОВАННО: все поля — цитаты-подстрожки исходного текста.
AI ничего не порождает на этом этапе — только решает lane-вердикт (arbitration)
и опционально пишет пост по готовому CASE.

Логика сборки:
  1) секции: если в тексте есть заголовки типа Задача/Решение/Результат
     (или Problem/Solution/Results/Impact) — поля берутся из своей секции;
  2) fallback: лексический поиск предложения-проблемы/внедрения/результата;
  3) компания: кандидат V2 + имена в кавычках/до двоеточия в заголовке,
     проверяется частотностью в ТЕЛЕ (а не в заголовке) и отсевом платформ;
  4) метрики: число+единица эффекта (+% / x / раз / валюты / время) и рядом
     глагол эффекта; «18 лет» (возраст) отсекается.

Каждое поле имеет evidence{quote} и проходит evidence.validate_case.
"""
import hashlib
import re

from .evidence import quote_in_source
from .utils import domain, extract_numbers, now_iso, ws_norm

SENT_SPLIT_RX = re.compile(r"(?<=[.!?])\s+(?=[\"A-ZА-ЯЁ«0-9])")

# заголовки секций -> роль
SECTION_RX = [
    ("problem", re.compile(r"^\s*(задача|проблем\w*|вызов|context|challenge|background|"
                           r"the situation|before)\b", re.I)),
    ("solution", re.compile(r"^\s*(решени\w*|что сделали|как сделали|подход|внедрени\w*|"
                            r"solution|how (they|it) (did|works)|implementation|approach|"
                            r"the fix)\b", re.I)),
    ("result", re.compile(r"^\s*(результат\w*|итог\w*|эффект\w*|что получилось|"
                          r"result\w*|outcome\w*|impact|business outcomes?)\b", re.I)),
]

PROBLEM_KW = re.compile(
    r"(problem|challenge|pain|before|struggl|manual|slow|fragment|disconnected|"
    r"legacy|overhead|wanted to|needed to|задач|проблем|до внедрения|ручной|ручно|"
    r"тормоз|не хватало|сложност|used to|inefficien|неэффектив|нецелев)", re.I)
IMPL_KW = re.compile(
    r"(implement|integrat|adopt|switch|migrat|deploy|built|automat|connect|use[sd] [A-Z]|"
    r"uses|использ|внедр|подключ|настро|запуск|интегра|перешл|создал|разработ|"
    r"стали |начали |implemented)", re.I)
RESULT_KW = re.compile(
    r"(result|impact|savings?|saved|reduced|reduc|increas|improv|cut|slashed|grew|"
    r"результат|эффект|сэконом|сократил|вырос|повысил|ускор|увеличил|стал[ио]?)", re.I)
EFFECT_VERB_RX = re.compile(
    r"(%|x\b|раз\b|п\.\s?п\.|₽|\$|€|USD|saved|savings|cut|reduc|increas|improv|"
    r"grew|эконом|сэконом|сократ|вырос|повысил|увелич|ускор|снизил|выручк|"
    r"revenue|up time|uptime|time to|per week|в неделю|в месяц)", re.I)

# единицы, без которых числовое значение не является метрикой эффекта
METRIC_UNIT_RX = re.compile(
    r"[-+−]?\d[\d.,]*\s*(%|п\.\s?п\.|x\b|раз\b|млн|млрд|тыс|K\b|M\b|USD|\$|€|₽|"
    r"hours?|hrs?|минут|часов|часа\b|дня\b|дней|days?|weeks?|недель|months?|"
    r"mes\.)", re.I)

# платформенные/продуктовые имена не могут быть «героем» кейса
NON_COMPANY_RX = re.compile(
    r"^(директ\w*|google|yandex|яндекс|mindbox|wunder|facebook|instagram|telegram|whatsapp|"
    r"slack|notion|zapier|salesforce|hubspot|bitrix\w*|n8n|make|chatgpt|gpt\w*|"
    r"gemini|claude|airtable|miro|jira|notion|clickup|trello|gmail|outlook|"
    r"agentforce|watson\w*|bigquery|databricks|power bi|crm|erp|ai|ml|ил|м.и.)\b",
    re.I)

QUOTE_TITLE_RX = re.compile(r"[«\"']([A-ZА-ЯЁ][^»\"']{2,40})[»\"']")
NUM_RX = re.compile(r"[-+−]?\d[\d.,]*")
STRONG_RESULT_RX = re.compile(
    r"(saved|saving|savings|cut\b|reducing|reduced|decreas|increased|increas|"
    r"improved|improve|grew|uplift|boost|эконом|сэконом|сократ|вырос|увелич|"
    r"повысил|ускор|снизил|удалось|\+ ?%|\- ?%|\+\d|\-\d|в \d+ раз|на \d+%)", re.I)

# body-mining: имена в середине предложения (не на старте), частотные
CAP_SEQ_RX = re.compile(r"(?<=[ \n\"«“(])([A-ZА-ЯЁ][\wA-ZА-ЯЁ.\-']{2,29}(?: [A-ZА-ЯЁ][\wA-ZА-ЯЁ.\-']{2,29}){0,2})")
STOP_NAMES = {
    "это", "он", "она", "оно", "они", "мы", "вы", "they", "this", "that", "there",
    "when", "after", "before", "but", "and", "for", "with", "from", "what", "how",
    "who", "why", "all", "some", "many", "more", "most", "new", "now", "also",
    "как", "если", "когда", "после", "до", "но", "и", "а", "также", "важно",
    "сегодня", "раньше", "сейчас", "кстати", "например", "конечно", "уже",
    "команда", "продукт", "проект", "рынок", "время", "компания", "бизнес",
    "статья", "кейс", "клиент", "пользователь", "сотрудник", "данные",
    "the", "a", "our", "your", "their", "its", "his", "her", "out", "about",
    "yandex", "google", "mindbox", "ibm", "sales", "however", "meanwhile",
}


def _sentences(text):
    parts = []
    for para in re.split(r"\n+", text):
        parts.extend(SENT_SPLIT_RX.split(para.strip()))
    return [p.strip() for p in parts if p and 30 <= len(p.strip()) <= 480]


def _sec_sentences(chunk):
    """Предложения секции: склеиваем bullet-обрывки (<45 симв. без финальной точки)
    со следующей строкой, потом стандартная сегментация."""
    if not chunk:
        return []
    lines = [l.strip() for l in chunk.splitlines() if l.strip()]
    merged, buf = [], ""
    for l in lines:
        l = re.sub(r"^[-•\u2022.\s]+", "", l)
        cand = (buf + " " + l).strip() if buf else l
        if len(cand) < 45 and cand and cand[-1] not in ".!?;:":
            buf = cand
            continue
        merged.append(cand)
        buf = ""
    if buf:
        merged.append(buf)
    parts = []
    for m in merged:
        parts.extend(SENT_SPLIT_RX.split(m))
    return [p.strip() for p in parts if p and 15 <= len(p.strip()) <= 480]


def _sections(text):
    """Разбивка по заголовкам секций -> {role: 'текст секции...'}.
    Сопоставляем только короткие строки (заголовки), чтобы не схлопнуть статью."""
    lines = text.split("\n")
    marks = []  # (line_idx, role)
    for i, ln in enumerate(lines):
        s = ln.strip()
        if 0 < len(s) <= 60:
            for role, rx in SECTION_RX:
                if rx.match(s):
                    marks.append((i, role))
                    break
    out = {}
    for j, (i, role) in enumerate(marks):
        end = marks[j + 1][0] if j + 1 < len(marks) else min(i + 40, len(lines))
        chunk = "\n".join(lines[i + 1:end]).strip()
        if len(chunk) > 40 and (role not in out or len(chunk) > len(out[role])):
            out[role] = chunk
    return out


def _pick(sents, rx, prefer=None, limit=2, skip_rx=None, exclude=(), text=None):
    """prefer — предложения из своей секции сначала. text — исходник:
    самопроверка дословности цитаты (merge-артефакты отсекаются)."""
    out = []
    pool = (prefer or []) + [s for s in sents if s not in (prefer or [])]
    for s in pool:
        if s in exclude:
            continue
        if skip_rx and skip_rx.match(s):
            continue
        if text is not None and not quote_in_source(s, text):
            continue
        if rx.search(s):
            out.append(s)
            if len(out) >= limit:
                break
    return out


# заголовокные токены: допускаем неразрывные дефисы (U+2010/U+2011)
TITLE_TOKEN_RX = re.compile(r"([A-ZА-ЯЁ][\wA-ZА-ЯЁ.\-\u2010\u2011']{2,30}(?: [A-ZА-ЯЁ][\wA-ZА-ЯЁ.\-\u2010\u2011']{2,30}){0,2})")
# одиночные ALLCAPS-аббревиатуры (ДРР, ROI, CPC…) — метрики, не компании
ABBREV_RX = re.compile(r"^[A-ZА-ЯЁ]{2,6}$")


def _bcount(body_ws, name_ws):
    return len(re.findall(r"(?<![\w-])" + re.escape(name_ws) + r"(?![\w-])", body_ws))


def _valid_name(name, body_ws, min_count=1):
    w = ws_norm(name)
    if (len(w) < 3 or w in STOP_NAMES or NON_COMPANY_RX.match(w)
            or ABBREV_RX.match(name.strip()) or _bcount(body_ws, w) < min_count):
        return False
    return True


def _body_names(text):
    """Частотные кап-имена внутри предложений (не в началах). -> {name: count}."""
    counts = {}
    for m in CAP_SEQ_RX.finditer(text or ""):
        pre = text[max(0, m.start() - 4):m.start()]
        if re.search(r"[.!?:;»\"“—-][ \n]*$|^[ \n]*$", pre):
            continue
        name = re.sub(r"[.,;:]+$", "", m.group(1)).strip()
        counts[name] = counts.get(name, 0) + 1
    return counts


def resolve_company(text, title, candidates):
    """Компания-герой с приоритетами:
      1) candidates классификатора (валиден + встречается в теле);
      2) имена из заголовка (в кавычках или Case-токены);
      3) body-mining: кап-имена в середине предложений с частотой>=3.
    Платформы/аббревиатуры-метрики/стоп-слова отсекаются. -> (name, method)."""
    body = ws_norm(text)
    for c in candidates or []:
        n = (c.get("name") or "").strip()
        if n and n.upper() != "NOT_FOUND" and _valid_name(n, body):
            return n, "classifier:" + (c.get("kind") or "candidate")
    pool = []
    for m in QUOTE_TITLE_RX.finditer(title or ""):
        pool.append((m.group(1).strip(), "title_quoted"))
    t = (title or "").split(" - ")[0].split(":")[0]
    for m in TITLE_TOKEN_RX.finditer(t):
        pool.append((m.group(1).strip(), "title_case"))
    best, best_f, how = None, 0, ""
    for n, method in pool:
        if not _valid_name(n, body):
            continue
        f = _bcount(body, ws_norm(n))
        if f > best_f:
            best, best_f, how = n, f, method
    if best:
        return best, how
    for n, cnt in sorted(_body_names(text).items(), key=lambda kv: -kv[1]):
        if cnt >= 3 and _valid_name(n, body, min_count=3):
            return n, "body_mined"
    return "NOT_FOUND", "none"


def _metric_items(text, max_items=6):
    items, seen = [], set()
    for m in METRIC_UNIT_RX.finditer(text or ""):
        val = re.sub(r"\s+", " ", m.group(0)).replace("\xa0", " ").strip()
        s = max(0, m.start() - 90)
        quote = re.sub(r"\s+", " ", text[s:m.end() + 90]).replace("\xa0", " ").strip()
        key = val.lower().rstrip(".")
        if key in seen or len(quote) < 25:
            continue
        if not EFFECT_VERB_RX.search(quote):
            continue
        seen.add(key)
        items.append({"value": val, "meaning": "", "evidence": {"quote": quote}})
        if len(items) >= max_items:
            break
    return items


def case_id_for(url, text):
    return "case-" + hashlib.sha1(((url or "") + "|" + (text or "")[:2000]).encode("utf-8")).hexdigest()[:12]


TECH_RX = re.compile(
    r"\b(GPT-\d\w*|ChatGPT|Claude|Gemini|LLaMA|Llama|watsonx\w*|Agentforce|BigQuery|"
    r"Dataflow|Vertex AI|Power BI|Databricks|Salesforce \w+|Zapier\w*|Make|n8n|Airtable|"
    r"Notion|Slack|Teams|Copilot|CRM|ERP|LLM|RAG|NLP|OCR|ML)\b")
TECH_STOP = {"use", "now", "sales", "new", "more", "the", "our"}


def _technologies(text):
    found = []
    for m in TECH_RX.finditer(text or ""):
        t = m.group(0)
        if t.lower() in TECH_STOP or len(t) < 2 or t not in found:
            continue
        found.append(t)
        if len(found) >= 6:
            break
    return found


def build_case(url, ext, classification, source=""):
    text = ext.get("text") or ""
    title = ext.get("title") or ""
    sec = _sections(text)
    sents = _sentences(text)
    s_problem = _sec_sentences(sec.get("problem", ""))
    s_solution = _sec_sentences(sec.get("solution", ""))
    s_result = _sec_sentences(sec.get("result", ""))

    company, method = resolve_company(text, title,
                                      (classification.get("features") or {}).get("company_candidates"))
    if company == "NOT_FOUND" and (classification.get("company") or "NOT_FOUND") != "NOT_FOUND":
        cand = classification["company"]
        if ws_norm(cand) in ws_norm(text) and not NON_COMPANY_RX.match(ws_norm(cand)):
            company, method = cand, "classifier_company_field"

    problems = _pick(sents, PROBLEM_KW, s_problem, 2, text=text)
    impls = _pick(sents, IMPL_KW, s_solution, 2, exclude=tuple(problems), text=text)
    # результат: сначала из секции; сильные результативные формулировки,
    # «проблемные» предложения (неэффективно/нецелевые) не считаются итогом
    res_pool = _pick(sents, RESULT_KW, s_result, 3, exclude=tuple(problems), text=text)
    strong = [r for r in res_pool if STRONG_RESULT_RX.search(r)]
    numbered = [r for r in (strong or res_pool) if NUM_RX.search(r)]
    sec_numbered = [s for s in s_result if NUM_RX.search(s) and s not in problems
                    and quote_in_source(s, text)]
    results = sec_numbered[:2] or numbered or strong or res_pool[:2]

    metrics = _metric_items(text)
    f = classification.get("features") or {}

    return {
        "case_id": case_id_for(url, text),
        "source_url": url,
        "source_domain": domain(url),
        "source_title": title,
        "source_published_at": ext.get("published_at", ""),
        "source": source,
        "language": ext.get("language", ""),
        "company_name": "" if company == "NOT_FOUND" else company,
        "company_detection_method": method,
        "case_type": classification.get("type", ""),
        "problem": problems[0] if problems else "",
        "implementation": impls[0] if impls else "",
        "solution": (impls[1] if len(impls) > 1 else impls[0]) if impls else "",
        "technology": _technologies(text),
        "results": results[:2],
        "metrics": metrics,
        "economic_effect": "",
        "evidence": {
            "problem": {"quote": problems[0]} if problems else {},
            "implementation": {"quote": impls[0]} if impls else {},
            "results": [{"quote": r} for r in results],
            "metrics": [m["evidence"]["quote"] for m in metrics],
        },
        "source_excerpt": re.sub(r"\s+", " ", text[:600]).replace("\xa0", " ").strip(),
        "confidence": float(classification.get("confidence") or 0.0),
        "classification": classification.get("type", ""),
        "classification_reason": "; ".join(classification.get("rationale") or [])[:400],
        "extraction_quality": ext.get("quality", ""),
        "case_sections": f.get("case_sections", []),
        "sections_detected": sorted(sec.keys()),
        "is_vendor_self_promo": bool(f.get("is_vendor_self_promo")),
        "created_at": now_iso(),
    }


REQUIRED_FIELDS = ("case_id", "source_url", "company_name", "problem",
                   "implementation", "evidence")


def validate_case_shape(case):
    """Структурная валидность CASE (до evidence-проверки). -> (ok, errors)."""
    errors = []
    for k in REQUIRED_FIELDS:
        if not case.get(k):
            errors.append("missing required field: %s" % k)
    if case.get("classification") != "business_case":
        errors.append("classification != business_case")
    ev = case.get("evidence") or {}
    if not (ev.get("problem") or {}).get("quote"):
        errors.append("no evidence for problem")
    if not (ev.get("implementation") or {}).get("quote"):
        errors.append("no evidence for implementation")
    # позиционирование канала требует экономический эффект: нужна оцифровка
    numeric = bool(case.get("metrics")) or any(NUM_RX.search(r or "") for r in case.get("results") or [])
    if not numeric:
        errors.append("no numeric result (metrics/results empty of numbers)")
    return (not errors), errors
