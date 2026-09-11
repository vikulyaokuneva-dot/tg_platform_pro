# -*- coding: utf-8 -*-
"""classifier_v2 — экспериментальная копия baseline + R2/R1/R3/R4/R5.

baseline (classifier_baseline.py) НЕ изменён. v2 переопределяет детекторы
ОБЩИМИ лингвистическими механизмами:

R2  overlap-scan компании (How X uses...; possessive; ранг 2 для possessive при
    повторе в тексте) + глаголы 3-го лица EN по окончанию -s;
R1  company_from_title — бренд = капитализованное слово (домен с точкой тоже),
    стоящее непосредственно перед глаголом заголовка, подтверждённое вхождением
    в тело текста (НЕ словарь компаний);
R3  has_case_sections — секции Challenge/Solution/Results/Задача/Решение/Результат
    как УСИЛЕНИЕ (с company + result/impl достаточно для business_case),
    сами по себе кейс не делают;
R4  is_opinion_byline / is_vendor_self_promo / упомянутый-источник-без-повтора
    (бренд только как библиографическая отсылка) — downgrade в needs_review;
R5  needs_review — первый класс статуса, не reject.

Расширены лексиконы problem/impl общими словами (unified, complexity, ...).
"""
import re

import classifier_baseline as B

NF = "NOT_FOUND"

# ---------------- лексиконы (общие слова, не имена компаний) ----------------

VERB_EN_S = re.compile(r"[a-z]{3,}s\b")  # 3rd-person: uses, accelerates, slashes...
VERB_RU_LIST = (r"(?:запустил[аи]?|запускают|внедрил[аи]?|внедряет|оптимизир\w+|"
                r"автоматизировал[аи]?|экономит|перенесл[аи]?|поставил[аи]?|"
                r"вернул[аи]?|обучил[аи]?|снизил[аи]?|расширил[аи]?|построил[аи]?|"
                r"перезапустил[аи]?|услуг[ае]?|ускоряет|собирает|подключил[аи]?|"
                r"сократил[аи]?|увеличил[аи]?|стал[аи]?|начал[аи]?|сталк|переехал[аи]?|"
                r"выбрал[аи]?|внедряют|создал[аи]?|использует|остановил[аи]?)")

TITLE_BRAND_PATTERNS = [
    # How/Inside <Brand> <verb>
    re.compile(r"(?:How|Inside|Why|When)\s+((?:[A-Z][\w'&.\-]*|[\w\-]+\.[a-z]{2,})(?:\s+[A-Z][\w'&.\-]*){0,2})\s+([a-z][\w'&\-]*s?\b[^\n]{0,25})", ),
    # <Brand> <verb-s> at very start / after " — "
    re.compile(r"(?:^|[—|:]\s*)((?:[A-Z][\w'&.\-]*|[\w\-]+\.[a-z]{2,})(?:\s+[A-Z][\w'&.\-]*){0,2})\s+((?:[a-z][\w'&\-]*(?:s|ed)\b|\w+)\b[^\n]{0,25})"),
    # опыт/кейс <Brand>
    re.compile(r"(?:опыт|Кейс|кейс|Case study[:\-]?)\s+((?:[А-ЯЁA-Z][\wА-ЯЁ.'\-]+|[\w\-]+\.[a-zа-я]{2,})(?:\s+[А-ЯЁA-Z][\wА-ЯЁ.'\-]+){0,2})", ),
    # Компании X / бренд X
    re.compile(r"(?:компани[яием]у?\s+|бренд\s+)((?:[А-ЯЁA-Z][\wА-ЯЁ.'\-]+|[\w\-]+\.[a-zа-я]{2,})(?:\s+[А-ЯЁA-Z][\wА-ЯЁ.'\-]+){0,2})", ),
]

# инфинитивы/служебные слова не считаются «глаголом заголовка»
NOT_VERB = {"uses".join(""), "his", "her", "its", "as", "is", "are", "was", "were",
            "be", "been", "has", "have", "had", "to", "of", "in", "on", "and",
            "for", "with", "the", "a", "an", "at", "by", "from", "into", "it",
            "they", "this", "that", "our", "you", "your", "all", "new", "more",
            "what", "when", "how", "why", "who", "за", "как", "это", "или", "и",
            "но", "не", "он", "она", "оно", "они", "мы", "вы", "из", "по", "от",
            "до", "над", "об", "же", "бы", "ну", "let", "lets", "says"}

EXTRA_IMPL = re.compile(
    r"(unified|consolidat\w+|handl(?:e|es|ed)\b|streamlin\w+|migrat\w+|"
    r"partnered with|switched to|integrat\w+|deployed|went from|replac\w+|"
    r"enhanc\w+|built on|embedded|deliver(?:ed|ing)\b|transform\w+|"
    r"использу\w+|применя\w+|выстро\w+|настро\w+|подключ\w+|запуск\w+|"
    r"внедр\w+|реализова\w+|перешл\w+|переключ\w+|собрали|создал\w+)",
    re.IGNORECASE)

EXTRA_PROBLEM = re.compile(
    r"(unified data|complexities|complexity|disconnected|fragmented|"
    r"struggling|overwhelm|inefficien|slow(?:ing)?\b|manual\b|tripled the cost|"
    r"points? toward answers|risk of|fear of|grew\b|rising expectations|"
    r"wanted to|move away from|relied on|legacy|буксОВА|тормоз|сложност|"
    r"не успев|ручной|не хватало)", re.IGNORECASE)

SECTION_RX = re.compile(
    r"(?im)^\s*[\-—•]?\s*(challenge|the challenge|problem|solution|results?|"
    r"impact|outcomes?|executive summary|the results|how they \w+|"
    r"what changed|задача|проблема|решение|результат[аы]?|эффект|"
    r"что изменилось|как они \w+|кейс \w+)\s*[:\-]?\s*$", re.MULTILINE)

BYLINE_RX = re.compile(
    r"(?im)^\s*by [A-Z][\w'.\-]+ [A-Z][\w'.\-]+\s*,\s*"
    r"(chief|head of|senior|global|vice|director|vp|cto|ceo|coo|cio)")

SELF_PROMO_RX_TMPL = [
    r"(?:within|inside)\s+{PUB}\b",
    r"\b{PUB}'s? (?:own|internal|teams?|organization|cio)\b",
]

STOP_BRANDS = set(B.VENDOR_LEXICON) | {
    "executive summary", "ibm corp", "zapier", "learn", "explore", "get",
    "share", "learn how", "case study", "the results", "how", "why",
    "free", "pro", "best", "guide", "tips", "what",
}


def _body_mentions(brand, text):
    b = brand.strip(" «»\"").rstrip(".,")
    if not b:
        return 0
    variants = [b]
    if re.search(r"[а-яё]$", b) and len(b) > 3:
        variants.append(b[:-1])  # рус. падежный хвост: «МИФа» -> «МИФ»
    n = 0
    for v in variants:
        n = max(n, len(re.findall(r"\b" + re.escape(v), text)))
    return n


NONVERB_S = {  # множественные существительные в заголовках — не глаголы
    "sales", "ways", "tips", "teams", "users", "tools", "systems", "years",
    "days", "rates", "practices", "lessons", "questions", "trends", "goals",
    "steps", "cases", "issues", "notes", "news", "apps", "apis", "files",
    "orders", "clients", "customers", "products", "markets", "reports",
    "hours", "minutes", "tickets", "leads", "deals", "emails", "messages",
    "channels", "metrics", "numbers", "people", "employees", "agencies",
}


IRREGULAR_PAST = {"built", "made", "saw", "got", "went", "grew", "led", "cut",
                  "ran", "drove", "gave", "found", "held", "kept", "sold",
                  "became", "began", "chose", "won", "took", "read", "set",
                  "brought", "spent", "met", "sent", "turned", "helped"}


def _verb_like(w):
    """Общая грамматическая проверка «похож на глагол». EN: 3-е лицо -s,
    прошедшее -ed, герундий -ing, список нерегулярных past; кроме множественных
    существительных. RU: личные/прошедшие окончания; инфинитивы на -ть/-чь
    не проходят."""
    if len(w) < 3 or w in NOT_VERB or w in NONVERB_S:
        return False
    if re.search(r"(ет|ут|ют|ят|ит|ил|ал|ел|ули|или|али|ала|ало|ело|ило|ивает|ывает|вает|мит|растут|стали)$", w):
        return True
    if re.search(r"(ли|ла|ло)$", w):
        return True
    if w in IRREGULAR_PAST:
        return True
    if (w.endswith(("s", "ed", "ing")) and len(w) >= 4):
        return True
    return False


EN_HOWTO_RX = re.compile(
    r"(?:how to\b|best practices|guide to\b|the future of|\b\d+ ways\b|^what \w+|^why \w+|"
    r"^\d+ \w+ (?:to|for)\b|checklist for)", re.IGNORECASE)
RU_HOWTO_RX = re.compile(
    r"(?:как \w+(?:ить|ти|ть)\b|что такое|что это|зачем \w+|кому \w+|"
    r"руководство|инструкция|чек-лист|пошагово)")


def title_brand(title, text):
    """R1: бренд в заголовке = капитализованное слово (или домен вида x.ru),
    непосредственно предшествующее глагольной группе заголовка (до 3 строчных
    слов-заполнителей между ними), И подтверждённое вхождением в тело текста.
    Это грамматическая форма «Заголовок = Субъект + Сказуемое», не словарь."""
    if not title or EN_HOWTO_RX.search(title) or RU_HOWTO_RX.search(title):
        return None
    toks = title.split()
    shape = re.compile(r"(?:[A-ZА-ЯЁ][\w'&.\-]*|[\w\-]+\.[a-zа-я]{2,})(?:-[A-Za-z]+)?")

    def ok(brand):
        brand = re.sub(r"[’']s$", "", brand).strip()  # «Okta's» -> «Okta»
        low = brand.lower().strip("«».,")
        if len(brand) < 3 or low in STOP_BRANDS:
            return None
        if brand.split()[0] in B.STOPWORD_STARTS or low in B.VENDOR_LEXICON:
            return None
        if re.search(B.GENERIC_COMPANY_RE, brand):
            return None
        # морфология: русское прилагательное с заглавной (начало фразы) — не бренд
        if " " not in brand.strip() and re.search(r"(ый|ая|ое|ые|аях|ых|им)$", brand, re.IGNORECASE):
            if not re.fullmatch(r"[А-ЯЁA-Z0-9.\-]+", brand):
                return None
        # шум «1-3 заглавные буквы» снимаем, только если бренд в теле кавычками
        # «...» или с маркером бренд/компания — т.е. подтверждён как именованный агент
        if re.fullmatch(r"[0-9А-ЯA-Z]{1,3}", brand):
            esc = re.escape(brand)
            if (not re.search(r"«" + esc + r"»|(?:бренд|компани[яеи])\s+" + esc, text)
                    and not re.search(r"\b" + esc + r"\b", text)):
                return None
        if _body_mentions(brand, text) < 1:
            return None
        return brand

    # 1) глагольная форма: ищем глагол, идём назад через строчные заполнители
    for vidx, t in enumerate(toks):
        w = t.lower().strip(".,:;!?")
        if vidx == 0 or not _verb_like(w):
            continue
        p = vidx - 1
        skipped = 0
        while p >= 0 and skipped < 3 and not shape.fullmatch(toks[p].strip("«»\"'().:,")):
            if not re.fullmatch(r"[,\-–—:;?!&\d%]+", toks[p].strip()):
                skipped += 1
            p -= 1
        if p < 0:
            continue
        for ln in (3, 2, 1):
            if p - ln + 1 < 0:
                continue
            seg = [x.strip("«»\"'().:,") for x in toks[p - ln + 1: p + 1]]
            if all(shape.fullmatch(s) for s in seg):
                b = ok(" ".join(seg))
                if b:
                    return b, "company_from_title"
    # 2) маркерные формы: «Кейс/опыт/Case study» + Имя или «Имя»
    mm = re.search(r"(?iu)(?:кейс|case study|опыт)[\s:—\-]{1,3}(?:[\wА-ЯЁ&.\-']+\s+){0,4}"
                   r"(?:«([А-ЯЁA-Z][^»]{2,35})»|([A-ZА-ЯЁ][\wА-ЯЁ.'\-]{2,30}))", title)
    if mm:
        b = ok(mm.group(1) or mm.group(2))
        if b:
            return b, "company_from_title"
    return None


def _find_candidates_v2(text, meta):
    """R2: скан с разрешением перекрытий + possessive-промоушен + расширенный список."""
    pub = (meta.get("publisher") or "").lower().strip()
    exclude = set(B.VENDOR_LEXICON)
    if pub:
        exclude.add(pub)
    sitename = (meta.get("sitename") or "").lower().strip()
    if sitename:
        exclude.add(sitename)
    hay = text + "\n" + (meta.get("title") or "") + "\n" + (meta.get("description") or "")

    # дополнительные EN-глаголы 3-го лица для narrative-паттерна
    verb_extra = (r"|uses|accelerates?|slashes?|scales?|pilots?|supports?|streams?|"
                  r"lights?|powers?|resolves?|unifies|consolidates?|provides?|"
                  r"serves?|delivers?|brings?|runs?|makes?|cuts?|turns?|goes?|plans?")
    cands = {}

    def add(name, span, rank, kind):
        nm = " ".join(name.split()).strip(" .«»,'-")
        if len(nm) < 2:
            return
        low = nm.lower().strip("«» ")
        if low in exclude or nm.split()[0].lower() in {s.lower() for s in B.STOPWORD_STARTS}:
            return
        if pub and low.split(" ")[0] == pub:
            return
        if re.search(B.GENERIC_COMPANY_RE, nm):
            return
        if re.fullmatch(r"[0-9А-ЯA-Z]{1,3}", nm):
            return
        if not B._proper_noun_ok(nm):
            return
        prev = cands.get(nm)
        if prev is None or prev[1] < rank:
            cands[nm] = (span, rank, kind, B._snippet(hay, span))

    # все baseline-паттерны, НО с overlap-перезапуском (R2)
    pats = list(B.COMPANY_PATTERNS)
    for i, (kind, rx, rank) in enumerate(pats):
        if kind == "en_verb_narrative":
            rx = rx.replace(r"switched\)", r"switched" + verb_extra + r")")
        rx_c = re.compile(rx) if isinstance(rx, str) else rx
        pos = 0
        while True:
            m = rx_c.search(hay, pos)
            if not m:
                break
            name = m.group(1)
            low = " ".join(name.split()).strip(" .«»,'-").lower().strip("«» ")
            reject = (low in exclude or not name.strip() or
                      (low.split(" ")[0] if low else "") in {s.lower() for s in B.STOPWORD_STARTS} or
                      (pub and low.split(" ")[0] == pub) or
                      bool(re.search(B.GENERIC_COMPANY_RE, name)) or
                      bool(re.fullmatch(r"[0-9А-ЯA-Z]{1,3}", name)) or
                      not B._proper_noun_ok(name))
            if reject:
                pos = m.start() + 1          # ГЛАВНЫЙ FIX R2: не глотать позицию
                continue
            rank_use = rank
            if kind == "en_possessive" and _body_mentions(name, hay) >= 1:
                rank_use = max(rank, 2)      # possessive с подтверждением в тексте
            add(name, m.span(), rank_use, kind)
            pos = m.start() + 1              # и дальше тоже с перекрытием
    ordered = sorted(cands.items(), key=lambda kv: -kv[1][1])
    return ordered


def classify_v2(cleaned_text, metadata=None, policy="strict"):
    """Возвращает тот же контракт, что baseline, плюс доп. фичи.
    Типы: business_case | how_to | news | other | needs_review."""
    meta = metadata or {}
    base = B.classify(cleaned_text, meta, policy=policy)
    text = cleaned_text or ""
    norm = text.replace("\u2019", "'").replace("\u00ab", "«").replace("\u00bb", "»")
    out = dict(base)
    F = dict(out.get("features") or {})
    ev = dict(out.get("evidence") or {})
    out["features"] = F
    out["evidence"] = ev
    title = meta.get("title") or ""

    # --- R2/R1 company -------------------------------------------------
    cand = _find_candidates_v2(norm, meta)
    tb = title_brand(title, norm)
    title_low = title.lower()
    company = None
    via = None
    cinfo = None
    if tb:
        # бренд из заголовка = субъект истории: приоритет над body-кандидатами
        company, via, cinfo = tb[0], "company_from_title", (None, 9, "company_from_title", title[:120])
    else:
        for name, info in cand:                     # pick first VALID candidate
            count = _body_mentions(name, norm)
            in_title = name.lower().strip("«» ") in title_low
            if info[1] >= 3 or count >= 2 or in_title:
                company, cinfo, via = name, info, info[2]
                break
    if company:
        F["company_candidates"] = (
            [{"name": n, "kind": i[2], "rank": i[1], "evidence": i[3]} for n, i in cand[:3]]
            + ([{"name": tb[0], "kind": "company_from_title", "rank": 9, "evidence": title[:120]}]
               if tb else []))
    has_company = bool(company)
    F["has_real_company"] = has_company
    F["company_detection_method"] = via or NF
    out["company"] = company or NF
    if company and not ev.get("company"):
        ev["company"] = cinfo[3] if cinfo and cinfo[3] else title[:120]

    # --- R4 guard: бренд упомянут только как библио-источник ------------
    F["company_is_only_mentioned_as_source"] = bool(
        not company and cand and _body_mentions(cand[0][0], norm) <= 1
        and cand[0][1][1] <= 2 and cand[0][0].lower() not in title_low)

    # --- problem / impl (расширенные лексиконы) -------------------------
    problem = F.get("has_real_problem") or bool(EXTRA_PROBLEM.search(norm))
    if problem and not ev.get("problem"):
        m = B.PROBLEM_RE.search(norm) or EXTRA_PROBLEM.search(norm)
        if m:
            ev["problem"] = B._snippet(norm, m.span())
    impl = F.get("has_real_implementation") or bool(EXTRA_IMPL.search(norm))
    if impl and not ev.get("implementation"):
        m = B.IMPL_RE.search(norm) or EXTRA_IMPL.search(norm)
        if m:
            ev["implementation"] = B._snippet(norm, m.span())

    # --- R3 sections ----------------------------------------------------
    secs = {s.group(0).strip().lower().rstrip(":-.") for s in SECTION_RX.finditer(norm)}
    def _grp(a):
        return any(x in a for x in ("challenge", "проблема", "задача"))
    def _grp_sol(a):
        return any(x in a for x in ("solution", "решение", "как они", "how they"))
    def _grp_res(a):
        return any(x in a for x in ("result", "результат", "impact", "outcome",
                                    "эффект", "executive summary", "что изменилось",
                                    "the results"))
    has_secs = (any(_grp(s) for s in secs) and any(_grp_sol(s) for s in secs)
                and any(_grp_res(s) for s in secs))
    F["case_sections"] = sorted(secs)[:8]
    F["has_case_sections"] = has_secs
    if has_secs:
        ev["case_sections"] = "; ".join(sorted(secs)[:6])

    # --- R4 byline / self-promo -----------------------------------------
    # Self-promo = ИЗДАТЕЛЬ является subject истории, а не инструментом.
    # 1) имя издателя и имя компании соседствуют в ЗАГОЛОВКОЙ строке
    #    («IBM AskHR», «IBM's AskHR») — это продукт вендора;
    # 2) «within/inside PUB», «PUB's own/internal» в теле, но только если
    #    кандидат НЕ в заголовке (иначе это клиентский кейс про инструмент).
    F["is_opinion_byline"] = bool(BYLINE_RX.search(title + "\n" + norm[:1500]))
    pub = (meta.get("publisher") or meta.get("sitename") or "").strip()
    F["is_vendor_self_promo"] = False
    if pub and company and pub.lower() in title.lower():
        esc_p = re.escape(pub)
        esc_c = re.escape(company.split()[0])
        company_in_title = company.split()[0].lower() in title.lower()
        if re.search(esc_p + r"['’]?s? " + esc_c, title, re.IGNORECASE):
            F["is_vendor_self_promo"] = True
            ev["self_promo"] = "title: «" + pub + " " + company + "» — продукт издателя"
        elif not company_in_title:
            rx2 = "|".join(t.format(PUB=esc_p) for t in SELF_PROMO_RX_TMPL)
            m2 = re.search(rx2, norm[:2500], re.IGNORECASE)
            if m2:
                F["is_vendor_self_promo"] = True
                ev["self_promo"] = B._snippet(norm, m2.span())

    # --- decision --------------------------------------------------------
    result = F.get("has_result") or F.get("has_metrics")
    presc_strong = F.get("prescriptive_markers_count", 0) >= 3
    illustr = F.get("is_illustrative_example")
    if len(re.sub(r"\s+", " ", norm)) < 700 and not (
            has_company and (has_secs or result)):
        out.update(type="other", confidence=0.9, rationale=["size-gate"])
        return out

    def conf_calc(extra_secs=False, weak=False):
        c = 0.45
        if problem: c += 0.12
        if F.get("has_metrics"): c += 0.12
        if F.get("has_result"): c += 0.08
        if F.get("has_person_with_role_and_company"): c += 0.08
        if not illustr: c += 0.05
        if extra_secs: c += 0.06
        if weak: c -= 0.05
        if via == "company_from_title" and not cand: c -= 0.03
        return round(max(0.3, min(0.93, c)), 2)

    out["rationale"] = []
    strong = has_company and impl and problem
    sec_route = has_company and has_secs and (result or impl)
    # R4 guard-ы: даже при сильных сигналах — в needs_review, не в accept
    if (strong or sec_route) and F["is_vendor_self_promo"]:
        out.update(type="needs_review", confidence=0.55)
        out["rationale"].append("R4: вендор продвигает себя (издатель в заголовке + "
                                "«within pub»/«pub company») -> needs_review")
        return out
    if (strong or sec_route) and F["is_opinion_byline"] and (
            via == "role_affiliation_at" or not sec_route):
        # гостевая колонка, где компания — аффилиация автора, а не независимый
        #subject с структурированным кейсом
        out.update(type="needs_review", confidence=0.5)
        out["rationale"].append("R4: opinion byline (автор-практик о своей компании)"
                                " -> needs_review")
        return out
    # принятие кейса
    if strong or sec_route:
        out.update(type="business_case",
                   confidence=conf_calc(extra_secs=sec_route, weak=sec_route and not strong),
                   policy=policy)
        r = ["company=%s via=%s" % (company, via)]
        if strong:
            r.append("company + problem + implementation (ядро)")
        if sec_route:
            r.append("R3: sections Challenge/Solution/Results + result/impl")
        if F.get("has_metrics"):
            r.append("booster: метрики")
        out["rationale"].extend(r)
        return out
    # R5: review-lane (компания+внедрение, но проблемы нет) — статус, не reject
    if has_company and impl and not problem:
        out.update(type="needs_review", confidence=0.5)
        out["rationale"].append("R5: company+implementation без problem -> needs_review")
        return out
    if has_company and problem and not impl and result and has_secs:
        out.update(type="needs_review", confidence=0.45)
        out["rationale"].append("R5: company+problem+sections, impl не подтвержден -> needs_review")
        return out

    if presc_strong or (illustr and not has_company):
        c = 0.4 + 0.15 * presc_strong + 0.15 * illustr + (0.1 if not has_company else 0.0)
        out.update(type="how_to", confidence=round(min(0.95, c), 2))
        return out
    if F.get("news_markers") and not has_company:
        out.update(type="news", confidence=0.5)
        return out
    if base.get("type") == "needs_review" or base.get("needs_review"):
        out.update(type="needs_review", confidence=0.5)
        return out
    out.update(type="other", confidence=0.35)
    return out
