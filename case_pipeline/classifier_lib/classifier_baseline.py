# -*- coding: utf-8 -*-
"""
Экспериментальный классификатор типа материала (ИЗУЧЕЧЕСКИЙ ПРОТОТИП).

Вход: очищенный текст статьи (cleaned.txt) + базовые metadata (title/description/url).
Выход: JSON с type, confidence, булевыми фичами, evidence-цитатами и rationale.

НЕ подключать к pipeline TG Platform. Только stdlib.

Два варианта:
  Variant A: classify(...)  -- rule-based, исполняемый.
  Variant B: build_ai_request(...) -- подготовка запроса к AI (GigaChat) со схемой;
           не исполняется здесь (нет ключей в окружении), схема/промпт документируются.

Политики решения business_case (для эксперимента #12):
  strict: real_company AND real_implementation AND real_problem (metrics -> только confidence)
  soft:   real_company AND real_implementation AND (real_problem OR has_result OR has_metrics)
"""
import json
import re

NF = "NOT_FOUND"

# ----------------------------------------------------------------------
# Лексикон
# ----------------------------------------------------------------------

# вендоры/продукты: не могут быть "реальной компанией-клиентом"
VENDOR_LEXICON = {
    "bitrix24", "битрикс24", "zapier", "salesforce", "ibm", "mindbox",
    "майнбокс", "agentforce", "terraform", "servicenow", "aws", "gcp",
    "hashicorp", "vault", "sentinel", "1c", "1с", "1с:предприятие",
    "яндекс директ", "яндекс метрика", "яндекс", "openai", "gpt-4",
    "gpt-4o", "gigachat", "notion", "n8n", "gmail", "google", "microsoft",
    "chatgpt",
}

STOPWORD_STARTS = {
    "The", "This", "That", "What", "How", "We", "They", "You", "It", "He",
    "She", "One", "Now", "For", "But", "And", "If", "When", "Learn", "Our",
    "His", "Her", "Its", "After", "Before", "Explore", "Company", "Компания",
    "Система", "Маршрут", "Процесс", "Документ", "Договор", "AI", "ML", "AB",
}

GENERIC_COMPANY_RE = re.compile(
    r"\b(оптов|рознич|крупн|небольш|известн|одной из|наш[а-яё]* |условн|"
    r"компани[а-яё]* |клиент)", re.IGNORECASE)

# одиночные юр-суффиксы сами по себе именем не считаются
SUFFIX_ONLY = {
    "inc", "llc", "ltd", "corp", "group", "bank", "holdings",
    "university", "foundation", "co", "компания",
}

# ----------------------------------------------------------------------
# Паттерны фичей
# ----------------------------------------------------------------------

COMPANY_PATTERNS = [
    # (kind, regex, rank)
    ("ru_legal_quoted", r"(?:ГК|ОАО|ЗАО|ПАО|АО|ООО|Банк)\s*«([^»]{2,60})»", 2),
    ("ru_verb_narrative",
     r"((?:[A-ZА-ЯЁ][\wА-ЯЁ«».:-]{1,38})(?:\s+[A-ZА-ЯЁ][\wА-ЯЁ«».:-]{1,20}){0,3})\s+"
     r"(?:внедри|использу|использовал|запустил|подключил|сэкономил|переш|создал|начал|стал|выбрал|добав)", 3),
    ("en_legal_suffix",
     r"((?:[A-Z][A-Za-z0-9&.'-]+\s+){0,4}(?:Inc\.?|LLC|Ltd\.?|Corp\.?|Group|Bank|Holdings|University|Foundation))\b", 2),
    ("en_verb_narrative",
     r"([A-Z][A-Za-z0-9&.'\- ]{2,40}?)\s+(?:uses|used|automates?|automated|adopted|"
     r"implemented|built|introduced|saved|saves|reduces?|reduced|increases?|increased|"
     r"streamlin\w+|delivers?|delivered|switched)\b", 3),
    ("role_affiliation_at",
     r"(?m)(?:Director|Manager|Engineer|Leader|Head|Officer|President|CEO|CTO|CIO|Specialist|Analyst|VP)"
     r"[^.\n]{0,60}?(?:at|of|,)\s+([A-Z][A-Za-z0-9&'\- ]{2,35}?)(?:[,.]|\s*$)", 4),
    ("en_possessive", r"([A-Z][A-Za-z0-9&'\- ]{3,38}?)'s\s", 1),
]

PROBLEM_RE = re.compile(
    r"(задач|проблем|roadblock|challenge|pain\s*point|bottleneck|t\w*ormoz"
    r"|нужно было|нужно было|хотели|wanted to|needed (?:a|to|an)|"
    r"не должен превышать|устаревш|несоответств|риск|risks?\b|ошибк|delays?"
    r"|back-and-forth|lead times?|manual\w*\s|вручную|unsustainable|прост[оо]и|"
    r"neither|no one knows|не знает|тормозит|не хватает|adding headcount)",
    re.IGNORECASE)

IMPL_RE = re.compile(
    r"(внедрил[аи]?|внедряет|внедрени|использу(?:ет|ю|ем)|использовал|"
    r"подключили|запустили|перешли|создали|разверну|развернули|разработали|добавили"
    r"|adopted|implemented|uses|used|built|integrated|introduce[ds]?|deployed"
    r"|switched|migrated|streamlin\w+|has reduced|reduced the|automated)"
    , re.IGNORECASE)

RESULT_RE = re.compile(
    r"(результат|итог[аи]?|эффект|сократил|ускор|вырос|повысил|сни[зил]|сэконом|"
    r"|получили|стал[ои]? быстрее|saved|reduced|increased|improved|speed(?:ed|up)"
    r"|resolved|result)", re.IGNORECASE)

METRICS_PATTERNS = [
    (r"\d+(?:[.,]\d+)?\s*(?:%|п\.\s?п\.)", "percent/pp"),
    (r"\$\s?[\d,.]+\s?[KMB]?\b", "money_usd"),
    (r"\b\d[\d,.]*\s?(?:K|M|млн|млрд|тыс)\b", "scale_units"),
    (r"\b(?:в|на)\s+\d+\s+раз\b", "multiples"),
    (r"\d[\d,.]*\s*(?:минут|часов|часа|дней|недель|месяц|лет\s|стран|обращени|агент|пользовател|заяво|сотрудник|segment|сегмент)", "quant_ops"),
    (r"\b(?:ROMI|ROI)\b", "roi"),
    (r"\d{1,3}(?:[\ \u00a0,]\d{3})+\b", "thousands"),
    (r"[−+\-]\s?\d+(?:[.,]\d+)?", "delta"),
    (r"(?:one|two|three|four|five|six|seven|eight|nine|ten|twelve|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand)\s+(?:minutes?|hours?|days?|weeks?|times?|years?)", "word_quant_en"),
    (r"\b\d[\d,.]*\s*(?:руб|₽|USD|EUR)", "money_rub"),
]

ILLUSTRATIVE_RE = re.compile(
    r"(как это может выглядеть на практике|например[,.]?\s+(?:раньше\s+)?"
    r"(?:в|у)\s+(?:\S+\s+){1,3}(?:компани|магаз|торгов|клиент|организаци)|"
    r"одного из наших клиентов|наш клиент|условно|представим|допустим|"
    r"for example, a (?:typical|small|mid)|hypothetically)",
    re.IGNORECASE)

PRESCRIPTIVE_RE = re.compile(
    r"(в статье разбер|разберём|разберем|расскажем|рассмотрим|чек-?лист|"
    r"шаг\s*\d|шаги|пошагов|проведите|определите|составьте|запустите пилот|"
    r"масштабиру|проверьте|нажмите|откройте|выберите|сделайте|помните|"
    r"как (?:настроить|автоматизировать|выбрать|внедрить|сделать|измерить|снизить)|"
    r"в статье|в этом руководстве|in this guide|tutorial|best practices|"
    r"tips for|how to )",
    re.IGNORECASE)

NEWS_RE = re.compile(
    r"(выпустил[аи]?|анонсир|объявил|представил|релиз|теперь доступен|"
    r"now available|announcing|we(?:’|')re launching|new feature|"
    r"запустил новый|представил новый|объявил о запуске|updates?\b)",
    re.IGNORECASE)

QUOTE_ROLE_RE = re.compile(
    r"(?:Director|Manager|Engineer|Leader|Head|Officer|President|CEO|CTO|CIO|"
    r"Specialist|Analyst)[^.\n]{2,80}?(?:at|of|,)\s+[A-ZА-ЯЁ][\wА-ЯЁ«». -]{2,40}",
    )

VENDOR_SELF_RE = re.compile(
    r"(мы строили|мы сделали|мы внедрили|мы используем|our platform|"
    r"в битрикс24|в zapier|в salesforce)", re.IGNORECASE)


def _snippet(text, span, width=90):
    start = max(0, span[0] - width)
    end = min(len(text), span[1] + width)
    s = re.sub(r"\s+", " ", text[start:end]).strip()
    return ("..." + s + "...") if start > 0 else (s + ("..." if end < len(text) else ""))


def _proper_noun_ok(name):
    """Кандидат похож на имя собственные («Premiere Property Group», «АВТОРУСЬ»),
    а не на обрывок предложения («A loan status agent», «Решили», «ML-ретаргетинг»)."""
    stripped = name.strip("«»\" ")
    quoted = stripped != name.strip()
    if not stripped:
        return False
    if stripped.lower().rstrip(".") in SUFFIX_ONLY:
        return False
    for t in re.split(r"\s+", stripped):
        t = t.strip("«».,;")
        if not t:
            continue
        if t.lower().rstrip(".") in SUFFIX_ONLY:
            continue
        if not t[0].isupper():
            return False
        has_cyr = any("а" <= ch.lower() <= "я" or ch.lower() == "ё" for ch in t)
        if has_cyr and not t.isupper() and not quoted:
            return False
    return True


def _find_candidates(text, meta):
    """Возвращает отсортированный список кандидатов в реальную компанию."""
    pub = (meta.get("publisher") or "").lower().strip()
    sitename = (meta.get("sitename") or "").lower().strip()
    exclude = set(VENDOR_LEXICON)
    if pub:
        exclude.add(pub)
    if sitename:
        exclude.add(sitename)
    candidates = {}
    hay = text + "\n" + (meta.get("title") or "") + "\n" + (meta.get("description") or "")
    for kind, rx, rank in COMPANY_PATTERNS:
        for m in re.finditer(rx, hay):
            raw = m.group(1)
            name = re.sub(r"\s+", " ", raw).strip(" .«»,'-")
            if len(name) < 2:
                continue
            low = name.lower().strip("«» ")
            if low in exclude or name in STOPWORD_STARTS:
                continue
            if pub and (low == pub or low.split(" ")[0] == pub):
                continue  # "IBM Corp" при publisher=IBM — это вендор, не клиент
            if name.split()[0] in STOPWORD_STARTS:
                continue
            if GENERIC_COMPANY_RE.search(name):  # "оптовой компании" и т.п.
                continue
            if re.fullmatch(r"[0-9А-ЯA-Z]{1,3}", name):  # шум 1С, КЭП, AB
                continue
            if not _proper_noun_ok(raw):
                continue
            pos = candidates.get(name)
            if pos is None or pos[1] < rank:
                candidates[name] = (m.span(), rank, kind, _snippet(hay, m.span()))
    ordered = sorted(candidates.items(), key=lambda kv: -kv[1][1])
    return ordered


def classify(cleaned_text, metadata=None, policy="strict"):
    """main entry: cleaned_text: str, metadata: dict{title, description, url, publisher, sitename, date}"""
    meta = metadata or {}
    ev = {}
    out = {
        "type": NF, "confidence": 0.0, "policy": policy,
        "company": NF,
        "features": {}, "evidence": ev, "rationale": [],
    }
    text = cleaned_text or ""
    norm = text.replace("\u2019", "'").replace("\u00ab", "«").replace("\u00bb", "»")
    F = out["features"]

    # -- size gate -----------------------------------------------------
    n = len(re.sub(r"\s+", " ", norm))
    F["text_length"] = n
    if n < 700:
        out["type"] = "other"
        out["confidence"] = 0.9
        out["rationale"].append(f"слишком мало содержания ({n} симв) -> other")
        return out

    # -- candidates for the real company -------------------------------
    cand = _find_candidates(norm, meta)
    F["company_candidates"] = [{"name": k, "kind": v[2], "rank": v[1], "evidence": v[3]} for k, v in cand[:5]]
    best_company = cand[0][0] if cand and cand[0][1][1] >= 2 else None
    F["has_real_company"] = bool(best_company)
    if best_company:
        out["company"] = best_company
        ev["company"] = cand[0][1][3]
        out["rationale"].append(f"найдена названная компания: '{best_company}' ({cand[0][1][2]})")
    else:
        out["rationale"].append("названной компании-клиента не найдено (только вендоры/generic)")

    # -- problem --------------------------------------------------------
    m = PROBLEM_RE.search(norm)
    F["has_real_problem"] = bool(m)
    if m:
        ev["problem"] = _snippet(norm, m.span())

    # -- implementation (subject must not be vendor-self only) ----------
    impl_hits = [x for x in IMPL_RE.finditer(norm) if len(x.group(0)) > 0]
    vendor_self = bool(VENDOR_SELF_RE.search(norm))
    F["vendor_self_voice"] = vendor_self
    if impl_hits:
        hit = impl_hits[0]
        s = max(0, hit.start() - 140)
        ctx = norm[s: hit.end() + 40]
        subj_we = re.search(r"(?:\bмы\b|\bмы строили\b)", ctx, re.IGNORECASE)
        F["has_real_implementation"] = bool(best_company) and not (subj_we and not best_company.lower() in ctx.lower())
        if F["has_real_implementation"]:
            ev["implementation"] = _snippet(norm, hit.span())
    else:
        F["has_real_implementation"] = False

    # -- result & metrics ------------------------------------------------
    mr = RESULT_RE.search(norm)
    F["has_result"] = bool(mr)
    if mr:
        ev["result"] = _snippet(norm, mr.span())
    met = []
    for rx, label in METRICS_PATTERNS:
        mm = re.search(rx, norm, re.IGNORECASE)
        if mm:
            met.append({"kind": label, "evidence": _snippet(norm, mm.span(), 50)})
    F["has_metrics"] = bool(met)
    F["metrics_signals"] = met[:6]
    if met:
        ev["metrics"] = met[:4]

    # -- illustrative / prescriptive / news ------------------------------
    mi = ILLUSTRATIVE_RE.search(norm)
    F["is_illustrative_example"] = bool(mi)
    if mi:
        ev["illustrative"] = _snippet(norm, mi.span())
    presc = PRESCRIPTIVE_RE.findall(norm)
    F["prescriptive_markers_count"] = len(set(p.lower() for p in presc))
    if presc:
        mpp = PRESCRIPTIVE_RE.search(norm)
        ev["prescriptive"] = _snippet(norm, mpp.span())
    mn = NEWS_RE.search(norm)
    F["news_markers"] = bool(mn)
    if mn:
        ev["news"] = _snippet(norm, mn.span())
    mq = QUOTE_ROLE_RE.search(norm)
    F["has_person_with_role_and_company"] = bool(mq)
    if mq:
        ev["quote_role"] = _snippet(norm, mq.span())

    # ------------------------------------------------------------------
    # Decision
    # ------------------------------------------------------------------
    company = F["has_real_company"]
    problem = F["has_real_problem"]
    impl = F["has_real_implementation"]
    result = F["has_result"] or F["has_metrics"]
    presc_strong = F["prescriptive_markers_count"] >= 3
    illustr = F["is_illustrative_example"]

    # strict: company+implementation+problem обязательны, метрики -> только confidence
    # soft:   company+implementation+(result|metrics), проблема опциональна
    if company and impl and problem:
        conf = 0.55
        if F["has_metrics"]:
            conf += 0.12
        if F["has_result"]:
            conf += 0.08
        if F["has_person_with_role_and_company"]:
            conf += 0.08
        if not illustr:
            conf += 0.05
        out["type"] = "business_case"
        out["confidence"] = round(min(0.95, conf), 2)
    elif company and impl and policy == "soft" and (result or F["has_metrics"]):
        conf = 0.5 + (0.1 if F["has_metrics"] else 0.0) + (0.05 if result else 0.0)
        out["type"] = "business_case"
        out["confidence"] = round(min(0.9, conf), 2)
        out["rationale"].append("soft policy: компания+внедрение+результат БЕЗ явной проблемы")
    elif presc_strong or (illustr and not company):
        out["type"] = "how_to"
        conf = 0.4 + 0.15 * presc_strong + 0.15 * illustr + (0.1 if not company else 0.0)
        out["confidence"] = round(min(0.95, conf), 2)
    elif F["news_markers"] and not company:
        out["type"] = "news"
        out["confidence"] = 0.5
    elif company and impl and not problem:
        # строгая политика: реальный кейс не подтверждён (нет нарратива бизнес-проблемы),
        # но и не how_to/news -> в очередь ручной проверки, НЕ business_case
        out["type"] = "other"
        out["confidence"] = 0.4
        out["needs_review"] = True
        out["rationale"].append("strict: компания+внедрение подтверждены, нарратива проблемы нет -> needs_review")
    else:
        out["type"] = "other"
        out["confidence"] = 0.35
        out["rationale"].append("недостаточно сигналов ни для кейса, ни для how_to/news")

    # rationale-ы для ключевых решений
    for k in ("has_real_company", "has_real_problem", "has_real_implementation",
              "has_result", "has_metrics", "is_illustrative_example"):
        out["rationale"].append(f"{k} = {F[k]}")
    return out


# ----------------------------------------------------------------------
# Variant B: AI classifier (проект запроса; исполнение — вне этого PoC)
# ----------------------------------------------------------------------

AI_SYSTEM_PROMPT = (
    "Ты — редакторский классификатор контента. Определи тип материала по его "
    "извлечённому тексту. Верни СТРОГО JSON без пояснений:\n"
    '{"type":"business_case|how_to|news|other","confidence":0..1,'
    '"company":string|null,"has_real_company":bool,"has_real_problem":bool,'
    '"has_real_implementation":bool,"has_real_result":bool,"has_metrics":bool,'
    '"is_illustrative_example":bool,"evidence":{"company":"...","problem":"...",'
    '"implementation":"...","result":"..."},"reason":"..."}\n'
    "Правила: business_case только если названа КОНКРЕТНАЯ компания-клиент "
    "(не вендор, не 'оптовая компания'), и она РЕАЛЬНО внедрила решение. "
    "Иллюстративные примеры ('например, в одной компании', 'как это может выглядеть') "
    "= is_illustrative_example=true -> how_to. Обучение/инструкции/чек-листы -> how_to. "
    "Анонсы продуктов/новости без истории клиента -> news. Каждый true обязан иметь "
    "короткую цитату-доказательство из текста (<=160 симв). Придумывать данные запрещено: "
    "если поля нет в тексте, верни false/null."
)


def build_ai_request(cleaned_text, metadata=None, max_chars=6000):
    meta = metadata or {}
    user = ("Заголовок: {t}\nURL: {u}\nОписание: {d}\n\nТЕКСТ:\n{txt}"
            .format(t=meta.get("title", ""), u=meta.get("url", ""),
                    d=meta.get("description", ""),
                    txt=(cleaned_text or "")[:max_chars]))
    return {"system": AI_SYSTEM_PROMPT, "user": user,
            "model_candidates": ["GigaChat-2", "GigaChat"], "temperature": 0.0}
