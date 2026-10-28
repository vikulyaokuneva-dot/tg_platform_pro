# -*- coding: utf-8 -*-
"""Traceable PETS source discovery and editorial selection.

This module is deliberately source-only: it neither calls a text model nor
delivers Telegram messages.  ``technical_status`` answers whether a licensed
source can be used; ``editorial_status`` answers whether its stored evidence is
enough for a future owner-facing draft.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import re
import time
import xml.etree.ElementTree as ET

import requests

from .pets_facts import Fact, is_sensitive, license_terms


NCBI_EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
PMC_ARTICLE_URL = "https://pmc.ncbi.nlm.nih.gov/articles/%s/"
FDA_FOOD_ENFORCEMENT = "https://api.fda.gov/food/enforcement.json"
USER_AGENT = "TelegramPlatformPETS/3.1.3 (editorial candidate dry-run; contact configured by operator)"


@dataclass(frozen=True)
class TopicSpec:
    key: str
    label: str
    category: str
    species: str
    pmc_query: str


def _field_or(terms):
    return " OR ".join('"%s"[Title/Abstract]' % term for term in terms)


def _pets_query(species, terms):
    """Search title/abstract without assuming all useful words are in a title.

    The query deliberately requires one domestic-context group but only one
    topic term.  The stricter full-text validation happens after retrieval.
    """
    animal = _field_or(("cat", "feline", "kitten")) if species == "cat" else _field_or(("dog", "canine", "puppy"))
    domestic = _field_or(("cat owner", "dog owner", "indoor cat", "pet cat", "household cat",
                          "companion dog", "pet dog", "household dog", "human-animal interaction",
                          "owner education", "pet welfare", "home environment"))
    return "(%s) AND (%s) AND (%s)" % (animal, domestic, _field_or(terms))


TOPIC_CATALOG = (
    TopicSpec("cat_home_behavior", "Поведение кошки дома", "behavior", "cat",
              _pets_query("cat", ("behavior", "behaviour", "home environment"))),
    TopicSpec("dog_home_behavior", "Поведение собаки дома", "behavior", "dog",
              _pets_query("dog", ("behavior", "behaviour", "home environment"))),
    TopicSpec("cat_enrichment", "Игры и обогащение среды для кошки", "enrichment", "cat",
              _pets_query("cat", ("enrichment", "play", "environment"))),
    TopicSpec("dog_enrichment", "Игры и обогащение среды для собаки", "enrichment", "dog",
              _pets_query("dog", ("enrichment", "play", "leisure"))),
    TopicSpec("cat_adaptation", "Адаптация кошки к новому дому", "care", "cat",
              _pets_query("cat", ("adoption", "rehoming", "new home"))),
    TopicSpec("dog_training", "Воспитание и обучение собаки", "training", "dog",
              _pets_query("dog", ("training", "learning", "owner"))),
    TopicSpec("cat_feeding", "Пищевые привычки кошки", "nutrition", "cat",
              _pets_query("cat", ("feeding behavior", "food preference", "feeding"))),
    TopicSpec("dog_walks", "Прогулки и активность собаки", "activity", "dog",
              _pets_query("dog", ("walking", "physical activity", "exercise"))),
    TopicSpec("cat_stress", "Стресс и благополучие кошки", "welfare", "cat",
              _pets_query("cat", ("stress", "welfare", "wellbeing"))),
    TopicSpec("dog_welfare", "Стресс и благополучие собаки", "welfare", "dog",
              _pets_query("dog", ("stress", "welfare", "wellbeing"))),
    TopicSpec("pet_ageing", "Возрастные особенности питомца", "care", "both",
              "((cat[Title] OR feline[Title]) OR (dog[Title] OR canine[Title])) AND (ageing[Title/Abstract] OR aging[Title/Abstract] OR senior[Title/Abstract])"),
)

EXCLUDED_TITLE_TERMS = (
    "case report", "case series", "surgery", "surgical", "diagnos", "imaging", "malignan",
    "tumor", "cancer", "carcinoma", "lymphoma", "patholog", "clinical", "laboratory",
    "in vitro", "student", "dissection", "osteology", "working dog", "service dog",
    "assistance dog", "detection dog", "military", "police dog", "canine-assisted", "zoonosis",
    "anaesthe", "anesthe", "ovariohysterectomy", "postoperative", "antimicrobial", "morbidity",
    "mortality", "dental", "allergen", "obesity", "wolf", "wolv", "shelter", "stray", "bite incident",
    "free-roaming", "virus", "viral", "antiviral", "molecular", "gene", "genomic", "crispr",
    "protein", "glycosyl", "tetherin", "cellular", "plant", "artemisia", "biochemical",
    "recognition", "network", "video", "algorithm", "computer vision", "breeder", "breeding",
    "association", "bodyweight", "body condition", "muscle condition",
    "nanoparticle", "antibiotic", "pathogen", "physicochemical", "follicular", "broad-spectrum",
)
MEDICAL_TERMS = EXCLUDED_TITLE_TERMS[:14] + (
    "therapy", "treatment", "drug", "medication", "dose", "anaesthe", "anesthe", "surgery",
    "postoperative", "morbidity", "mortality", "allergen", "obesity",
)
SECTION_TITLES = {
    "results": "result",
    "discussion": "discussion",
    "conclusion": "conclusion",
    "conclusions": "conclusion",
    "limitations": "limitations",
}
CATEGORY_TITLE_TERMS = {
    "behavior": ("behavior", "behaviour", "interaction", "temperament", "stress"),
    "enrichment": ("enrichment", "play", "leisure"),
    "care": ("adaptation", "new home", "ageing", "aging", "senior", "grooming", "hygiene"),
    "training": ("training", "learning", "owner education"),
    "nutrition": ("feeding", "food", "diet", "eating"),
    "activity": ("walking", "exercise", "activity", "leisure"),
    "welfare": ("welfare", "wellbeing", "well-being", "stress"),
}
RESULT_NOISE_TERMS = (
    "participants", "responses were retained", "demographics", "table 1", "table 2",
    "countries", "women", "men", "years old", "suburban", "frequency",
)
DOMESTIC_CONTEXT_TERMS = (
    "cat owner", "dog owner", "pet owner", "owners", "household", "home", "indoor", "companion",
    "pet cat", "pet dog", "owned cat", "owned dog", "human-animal interaction", "family dog", "family cat",
)
EVIDENCE_PATTERNS = {
    "behavior": ("behavior", "behaviour", "interaction", "stress", "temperament", "separation"),
    "enrichment": ("enrichment", "play", "toy", "activity", "engagement"),
    "care": ("adaptation", "new home", "rehoming", "habituation", "ageing", "aging", "senior"),
    "training": ("training", "learning", "owner education", "reinforcement", "instruction"),
    "nutrition": ("feeding", "food", "diet", "eating", "preference"),
    "activity": ("walking", "exercise", "activity", "active", "leisure"),
    "welfare": ("welfare", "wellbeing", "well-being", "quality of life", "stress"),
}
MEASURED_RESULT_TERMS = (
    "observed", "measured", "recorded", "reported", "showed", "found", "associated", "difference",
    "increased", "decreased", "higher", "lower", "significant", "score", "time", "frequency", "%",
)
DERIVATIVE_DISCUSSION_MARKERS = (
    "therefore", "broader evidence", "widely regarded", "should incentivize", "we recommend",
    "we suggest", "guidelines recommend", "this test originally", "literature points", "considerable number",
)


def _text(node):
    return re.sub(r"\s+", " ", "".join(node.itertext()) if node is not None else "").strip()


def _sentences(value):
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", value or "") if 50 <= len(part.strip()) <= 500]


def _species(value):
    original = value or ""
    value = original.lower()
    cat_matches = list(re.finditer(r"\b(cat|cats|feline|kitten)\b", original, re.I))
    # ``CAT`` is frequently an unrelated test/scale acronym in biomedical XML.
    cat = any(match.group(0) != "CAT" for match in cat_matches) and not bool(
        re.search(r"\bcat[-_]|\b[a-z]{2,}[-_]cat\b", value))
    dog = bool(re.search(r"\b(dog|dogs|canine|puppy)\b", original, re.I))
    return "both" if cat and dog else "cat" if cat else "dog" if dog else "general"


def _license_from_text(value):
    raw = (value or "").lower()
    if "cc by-nc-nd" in raw or "cc-by-nc-nd" in raw or "attribution-noncommercial-noderivatives" in raw:
        return "CC_BY_NC_ND"
    if "cc by-nc-sa" in raw or "cc-by-nc-sa" in raw:
        return "CC_BY_NC_SA"
    if "cc by-nc" in raw or "cc-by-nc" in raw:
        return "CC_BY_NC"
    if "cc by-sa" in raw or "cc-by-sa" in raw or "attribution-sharealike" in raw:
        return "CC_BY_SA"
    if "creative commons attribution" in raw or "cc by" in raw or "cc-by" in raw:
        return "CC_BY"
    if "cc0" in raw:
        return "CC0"
    return "UNKNOWN"


def _title_is_excluded(title):
    lowered = (title or "").lower()
    return next((term for term in EXCLUDED_TITLE_TERMS if term in lowered), "")


def _title_matches_category(title, category):
    lowered = (title or "").lower()
    return any(term in lowered for term in CATEGORY_TITLE_TERMS.get(category, ()))


def _medical_text(title, facts):
    text = " ".join([title] + [fact.claim for fact in facts]).lower()
    return next((term for term in MEDICAL_TERMS if term in text), "")


def _domestic_context(value):
    lowered = (value or "").lower()
    return any(term in lowered for term in DOMESTIC_CONTEXT_TERMS)


def _study_metadata(article, title=""):
    """Keep minimal study context so facts cannot masquerade as universal advice."""
    body = _text(article.find(".//body"))
    lowered = (str(title) + " " + body).lower()
    study_type = next((name for name, markers in (
        ("cross-sectional", ("cross-sectional", "cross sectional")),
        ("survey", ("survey", "questionnaire")),
        ("observational", ("observational", "observed")),
        ("controlled study", ("controlled", "randomized", "randomised")),
    ) if any(marker in lowered for marker in markers)), "unspecified")
    sample = re.findall(r"\b(?:n\s*=\s*\d+|\d+\s+(?:cats|dogs|owners|households|participants))\b", body, re.I)
    population_limited = bool(re.search(r"\b(?:in|among)\s+women\b", str(title).lower())) or any(marker in lowered for marker in (
        "women only", "female owners only", "veterinary students", "staff-owned dogs", "shelter population",
    ))
    return {"study_type": study_type, "sample_signals": sample[:3],
            "sample_described": bool(sample), "population_limited": population_limited,
            "limitations_present": "limitation" in lowered}


def _reason_category(candidate):
    title = candidate.get("title", "")
    facts = tuple(candidate.get("facts", ()))
    if not candidate.get("adaptation_allowed"):
        return "license"
    if _medical_text(title, facts):
        return "medical"
    excluded = _title_is_excluded(title)
    if excluded:
        return "false_keyword_match" if excluded in {"molecular", "gene", "protein", "cellular", "viral", "algorithm", "network"} else "irrelevant_audience"
    if not candidate.get("domestic_context"):
        return "irrelevant_audience"
    if len(facts) < 3:
        return "insufficient_facts"
    if not candidate.get("study", {}).get("sample_described") or candidate.get("study", {}).get("population_limited"):
        return "unsuitable_sample"
    return "editorial_review"


def _section_facts(article, *, title, species, source_url, source_name, source_type, authors,
                   published_at, license_name, license_url, obligations, adaptation_allowed, category):
    """Extract short, attributed observations from appropriate full-text sections."""
    selected, limitations, seen = [], [], set()
    for section in article.findall(".//sec"):
        heading = _text(section.find("title")).lower()
        kind = next((value for name, value in SECTION_TITLES.items() if name in heading), "")
        if not kind:
            continue
        body = " ".join(_text(node) for node in section.findall("./p"))
        for sentence in _sentences(body):
            key = sentence.lower()
            if key in seen:
                continue
            seen.add(key)
            if kind == "limitations":
                if len(limitations) < 2:
                    limitations.append(sentence)
                continue
            if len(selected) >= 5:
                continue
            topic_terms = EVIDENCE_PATTERNS.get(category, ())
            has_topic_signal = any(term in key for term in topic_terms)
            has_measurement = any(term in key for term in MEASURED_RESULT_TERMS) or bool(re.search(r"\b\d+(?:\.\d+)?\b", key))
            derivative_discussion = kind in {"discussion", "conclusion"} and any(
                marker in key for marker in DERIVATIVE_DISCUSSION_MARKERS)
            cited_discussion = kind in {"discussion", "conclusion"} and bool(
                re.search(r"\[\d+(?:[,-]\d+)*\]", sentence))
            sample_description = key.startswith("this study documented") and not any(
                marker in key for marker in ("associated", "difference", "increased", "decreased", "significant"))
            is_noise = any(term in key for term in RESULT_NOISE_TERMS)
            # A Result sentence which contains neither the selected theme nor
            # the animal subject is usually sample/table metadata, not an
            # owner-relevant finding.  Do not promote it to a factual brief.
            has_animal_signal = bool(re.search(r"\b(cat|cats|feline|kitten|dog|dogs|canine|puppy)\b", key))
            # A factual brief needs a category-specific observation/result;
            # random prose mentioning an animal does not qualify as evidence.
            if (is_noise and not has_topic_signal) or derivative_discussion or cited_discussion or sample_description or not has_topic_signal or not has_measurement:
                continue
            selected.append(Fact(topic=title, species=species, claim=sentence, source_url=source_url,
                                 source_name=source_name, source_type=source_type,
                                 author_or_body=authors or source_name, published_at=published_at,
                                 license=license_name, license_source_url=license_url or source_url,
                                 attribution_requirements=obligations,
                                 adaptation_allowed=adaptation_allowed,
                                 evidence_level="primary_research", source_section=kind,
                                 fact_kind="study_%s" % kind))
    if not limitations:
        limitations.append("The selected source is study-specific; its findings are not a universal owner recommendation.")
    return tuple(selected), tuple(limitations)


def editorial_assessment(candidate):
    """Transparent, conservative seven-criterion editorial gate (0..14)."""
    facts = tuple(candidate.get("facts", ()))
    title = candidate.get("title", "")
    reasons, score = [], 0
    excluded = _title_is_excluded(title)
    medical = _medical_text(title, facts)
    useful_categories = {"behavior", "enrichment", "care", "training", "nutrition", "activity", "welfare"}

    evidence_matched = len(facts) >= 3
    domestic_context = bool(candidate.get("domestic_context"))
    if not excluded and domestic_context and candidate.get("category") in useful_categories:
        score += 2
    else:
        reasons.append("owner_relevance: excluded=%s; domestic_context=%s" %
                       (excluded or "none", domestic_context))
    if candidate.get("topic_key") and candidate.get("species") in {"cat", "dog", "both"} and domestic_context:
        score += 2
    else:
        reasons.append("channel_fit: domestic animal context is not confirmed")
    if evidence_matched:
        score += 2
    else:
        reasons.append("facts: fewer than three evidence-pattern facts")
    if any(fact.fact_kind in {"study_result", "study_conclusion", "study_discussion"} for fact in facts):
        score += 2
    else:
        reasons.append("evidence: no result/discussion/conclusion fact")
    if all(len(fact.claim) <= 400 for fact in facts) and facts:
        score += 2
    else:
        reasons.append("plain_language: no concise evidence statements")
    if not medical and not any(is_sensitive(fact) for fact in facts):
        score += 2
    else:
        reasons.append("safety: medical_or_sensitive=%s" % (medical or "sensitive"))
    image_search_feasible = candidate.get("species") in {"cat", "dog", "both"} and domestic_context and not excluded
    if image_search_feasible:
        score += 2
    else:
        reasons.append("image: a relevant photo search is not feasible")
    if candidate.get("study", {}).get("population_limited"):
        reasons.append("sample: population is too narrow for a general owner-facing brief")

    ready = score >= 12 and not reasons and candidate.get("technical_status") == "source_usable"
    return {
        "score": score,
        "max_score": 14,
        "criteria": {
            "owner_usefulness": not bool(excluded) and domestic_context, "channel_fit": bool(candidate.get("topic_key")) and domestic_context,
            "specific_facts": evidence_matched, "evidence": any(f.fact_kind != "unknown" for f in facts),
            "plain_language": bool(facts), "medical_safety": not bool(medical),
            "image_search_feasible": image_search_feasible,
            "image_verified": False,
        },
        "reasons": reasons,
        "reason_category": _reason_category(candidate),
        "decision": "editorially_ready" if ready else "needs_editorial_review",
    }


class PmcOpenAccessAdapter:
    """Official PMC E-utilities full-text connector with topic catalogue."""
    source_id = "pmc_oa"
    source_name = "PubMed Central Open Access"
    source_type = "primary_research"
    journal_query = ""

    def __init__(self, session=requests, email=None, tool="tg_platform_pets", max_topic_specs=8,
                 request_interval=None, retries=2, sleep=time.sleep, clock=time.monotonic):
        self.session, self.email, self.tool = session, email, tool
        self.max_topic_specs = max(1, min(int(max_topic_specs), len(TOPIC_CATALOG)))
        # NCBI E-utilities permits only a small unauthenticated request rate.
        # GitHub-hosted runners share an IP, so stay below that limit and retry
        # transient overloads instead of losing the whole source collection.
        if request_interval is None:
            request_interval = 0.5 if session is requests else 0.0
        self.request_interval = max(0.0, float(request_interval))
        self.retries = max(0, int(retries))
        self.sleep, self.clock = sleep, clock
        self._next_request_at = 0.0

    def _get(self, endpoint, **params):
        # NCBI accepts a tool identifier without an invented contact address.
        # An operator may set NCBI_CONTACT_EMAIL for a future production lane.
        params.update({"tool": self.tool})
        if self.email:
            params["email"] = self.email
        for attempt in range(self.retries + 1):
            remaining = self._next_request_at - self.clock()
            if remaining > 0:
                self.sleep(remaining)
            response = self.session.get(NCBI_EUTILS + endpoint, params=params,
                                        headers={"User-Agent": USER_AGENT}, timeout=30)
            self._next_request_at = self.clock() + self.request_interval
            if response.status_code == 200:
                return response
            if response.status_code in {429, 500, 502, 503, 504} and attempt < self.retries:
                headers = getattr(response, "headers", {}) or {}
                try:
                    retry_after = float(headers.get("Retry-After", 1))
                except (TypeError, ValueError):
                    retry_after = 1.0
                self.sleep(max(self.request_interval, retry_after))
                # The retry delay already satisfies the normal request gap.
                self._next_request_at = 0.0
                continue
            raise RuntimeError("pmc_http_%s" % response.status_code)
        raise RuntimeError("pmc_request_retries_exhausted")

    def search_ids(self, spec, limit=3):
        query = "%s AND %s" % (self.journal_query, spec.pmc_query) if self.journal_query else spec.pmc_query
        response = self._get("esearch.fcgi", db="pmc", term=query, retmax=min(limit, 5),
                             retmode="json", sort="pub date")
        ids = response.json().get("esearchresult", {}).get("idlist", [])
        return [item for item in ids if str(item).isdigit()][:limit]

    def _articles(self, ids):
        if not ids:
            return []
        response = self._get("efetch.fcgi", db="pmc", id=",".join(ids), retmode="xml")
        return ET.fromstring(response.content).findall(".//article")

    def _candidate(self, article, spec=None):
        title = _text(article.find(".//article-title"))
        pmcid = (_text(article.find(".//article-id[@pub-id-type='pmcid']"))
                 or _text(article.find(".//article-id[@pub-id-type='pmc']")))
        doi = _text(article.find(".//article-id[@pub-id-type='doi']"))
        if not title or not pmcid:
            return None
        abstract = _text(article.find(".//abstract"))
        species = _species(" ".join((title, abstract)))
        if spec is None:
            spec = next((item for item in TOPIC_CATALOG
                         if item.species in {species, "both"}), TOPIC_CATALOG[0])
        if species == "general" or (spec.species != "both" and species not in {spec.species, "both"}):
            return None
        licence_node = article.find(".//license-p")
        license_name = _license_from_text(_text(licence_node))
        license_name, adaptation_allowed, obligations = license_terms(license_name)
        license_url = ""
        if licence_node is not None:
            for link in licence_node.findall(".//ext-link"):
                license_url = link.attrib.get("{http://www.w3.org/1999/xlink}href") or link.attrib.get("href") or ""
                if license_url:
                    break
        authors = []
        for contrib in article.findall(".//contrib[@contrib-type='author']")[:8]:
            name = _text(contrib.find("name"))
            if name:
                authors.append(name)
        year = _text(article.find(".//pub-date/year")) or None
        source_url = PMC_ARTICLE_URL % pmcid
        technical_status = "source_usable" if adaptation_allowed else "source_rights_review"
        facts, limitations = _section_facts(article, title=title, species=species, source_url=source_url,
                                            source_name=self.source_name, source_type=self.source_type,
                                            authors=", ".join(authors), published_at=year,
                                            license_name=license_name, license_url=license_url,
                                            obligations=obligations, adaptation_allowed=adaptation_allowed,
                                            category=spec.category)
        study = _study_metadata(article, title)
        # Do not infer household relevance from a reference list deep in an
        # article.  It must be explicit in the title or abstract.
        domestic_context = _domestic_context(" ".join((title, abstract)))
        candidate = {
            "source_key": "pmc:" + pmcid, "source_id": self.source_id, "title": title,
            "species": species, "doi": doi, "pmcid": pmcid, "source_url": source_url, "authors": ", ".join(authors),
            "published_at": year, "license": license_name, "license_source_url": license_url or source_url,
            "attribution_requirements": obligations, "adaptation_allowed": adaptation_allowed,
            "technical_status": technical_status, "topic_key": spec.key, "category": spec.category,
            "facts": facts, "limitations": limitations, "study": study, "domestic_context": domestic_context,
            "image_search_feasible": False, "image_verified": False,
            "safety_status": "review" if (not adaptation_allowed or _medical_text(title, facts)) else "candidate_ready",
        }
        candidate["editorial"] = editorial_assessment(candidate)
        candidate["editorial_status"] = candidate["editorial"]["decision"]
        candidate["image_search_feasible"] = candidate["editorial"]["criteria"]["image_search_feasible"]
        return candidate

    def collect_candidates(self, limit=10):
        candidates, seen = [], set()
        # Rotate cat/dog catalogue entries; caps make the network test bounded.
        # A bounded catalogue preserves E-utilities rate limits and makes a
        # manual dry-run predictable.
        for spec in TOPIC_CATALOG[:self.max_topic_specs]:
            if len(candidates) >= limit:
                break
            for article in self._articles(self.search_ids(spec, limit=2)):
                candidate = self._candidate(article, spec)
                if not candidate or candidate["source_key"] in seen:
                    continue
                seen.add(candidate["source_key"])
                candidates.append(candidate)
                if len(candidates) >= limit:
                    break
        return candidates


class FrontiersVeterinaryPmcAdapter(PmcOpenAccessAdapter):
    source_id = "frontiers_vet"
    source_name = "Frontiers in Veterinary Science via PMC OA"
    journal_query = "Front Vet Sci[jour]"


class FdaCvmSafetyAdapter:
    """Official FDA recall records remain review-only safety signals."""
    source_id = "fda_cvm"
    source_name = "FDA animal-food enforcement data"

    def __init__(self, session=requests):
        self.session = session

    def collect_candidates(self, limit=10):
        response = self.session.get(FDA_FOOD_ENFORCEMENT,
                                    params={"search": "product_description:(dog OR cat)", "limit": min(limit, 10)},
                                    headers={"User-Agent": USER_AGENT}, timeout=30)
        if response.status_code != 200:
            raise RuntimeError("fda_food_http_%s" % response.status_code)
        result = []
        for item in response.json().get("results", []):
            description, reason, recall = (str(item.get(key) or "").strip() for key in
                                           ("product_description", "reason_for_recall", "recall_number"))
            species = _species(description)
            if not (description and reason and recall and species != "general"):
                continue
            url = FDA_FOOD_ENFORCEMENT + "?search=recall_number:%s" % recall
            fact = Fact(topic="FDA animal-food safety record", species=species,
                        claim="FDA enforcement record %s lists product '%s' with recall reason: %s." % (recall, description, reason),
                        source_url=url, source_name=self.source_name, source_type="government_data",
                        author_or_body="U.S. Food and Drug Administration", published_at=item.get("recall_initiation_date"),
                        license="PUBLIC_DOMAIN", license_source_url="https://www.fda.gov/about-fda/website-policies/website-disclaimer",
                        attribution_requirements="credit FDA and do not imply endorsement", adaptation_allowed=True,
                        evidence_level="regulatory", source_section="record", fact_kind="safety_signal")
            result.append({"source_key": "fda:" + recall, "source_id": self.source_id,
                           "title": "FDA recall record " + recall, "species": species, "doi": "", "source_url": url,
                           "authors": "U.S. Food and Drug Administration", "published_at": item.get("recall_initiation_date"),
                           "license": "PUBLIC_DOMAIN", "license_source_url": "https://www.fda.gov/about-fda/website-policies/website-disclaimer",
                           "attribution_requirements": "credit FDA and do not imply endorsement", "adaptation_allowed": True,
                           "technical_status": "source_usable", "topic_key": "", "category": "safety",
                           "facts": (fact,), "limitations": ("A recall record is not an owner recommendation.",),
                           "safety_status": "review", "editorial_status": "needs_editorial_review",
                           "editorial": {"score": 0, "max_score": 14, "decision": "needs_editorial_review",
                                         "reasons": ["safety_signal_requires_manual_editorial_review"]}})
        return result


AUTOMATIC_CANDIDATE_ADAPTERS = {
    "pmc_oa": PmcOpenAccessAdapter,
    "frontiers_vet": FrontiersVeterinaryPmcAdapter,
    # FDA is collected for a visible safety/review lane only.  Its candidate
    # carries ``editorial_status=needs_editorial_review`` and can never fill
    # the automatic queue.
    "fda_cvm": FdaCvmSafetyAdapter,
}


def candidate_adapters_for(source_ids):
    """Return only explicitly supported evidence connectors (fail closed)."""
    return {source_id: AUTOMATIC_CANDIDATE_ADAPTERS[source_id]()
            for source_id in (source_ids or ()) if source_id in AUTOMATIC_CANDIDATE_ADAPTERS}


def _normalise_doi(value):
    value = (value or "").strip().lower()
    value = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value)
    return value.rstrip(" .;,")


def _candidate_identities(candidate):
    """DOI and PMCID are separate identity keys so source formatting cannot duplicate a study."""
    keys = set()
    doi = _normalise_doi(candidate.get("doi"))
    pmcid = (candidate.get("pmcid") or "").upper().replace(" ", "")
    if doi:
        keys.add("doi:" + doi)
    if pmcid:
        keys.add("pmcid:" + pmcid)
    if not keys:
        keys.add("source:" + str(candidate.get("source_key") or ""))
    return keys


def collect_source_candidates(adapters, storage=None, limit=10):
    """Collect independently, deduplicate DOI/PMCID across sources, persist reasons."""
    report, accepted, seen, rejected, history_skipped = {}, [], set(), 0, 0
    for source_id, adapter in (adapters or {}).items():
        try:
            found = list(adapter.collect_candidates(limit=max(limit * 2, 10)))
            unique = []
            for candidate in found:
                identities = _candidate_identities(candidate)
                if identities & seen:
                    rejected += 1
                    continue
                if storage is not None and storage.source_candidate_rejected(identities):
                    history_skipped += 1
                    continue
                seen.update(identities)
                unique.append(candidate)
                if storage is not None:
                    storage.save_source_candidate(candidate)
                    if candidate.get("editorial_status") != "editorially_ready":
                        storage.record_source_candidate_rejection(
                            identities, candidate.get("editorial", {}).get("reason_category", "editorial_review"))
            report[source_id] = {
                "status": "ok", "found": len(found), "unique": len(unique),
                "editorially_ready": sum(c.get("editorial_status") == "editorially_ready" for c in unique),
                "needs_editorial_review": sum(c.get("editorial_status") != "editorially_ready" for c in unique),
            }
            accepted.extend(unique)
        except Exception as exc:
            report[source_id] = {"status": "error", "error": type(exc).__name__}
    ready = [item for item in accepted if item.get("editorial_status") == "editorially_ready"]
    review = [item for item in accepted if item.get("editorial_status") != "editorially_ready"]
    return (ready + review)[:limit], report, {"deduplicated": rejected, "history_skipped": history_skipped,
                                               "total_unique": len(accepted)}
