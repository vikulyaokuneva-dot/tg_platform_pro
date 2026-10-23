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
import xml.etree.ElementTree as ET

import requests

from .pets_facts import Fact, is_sensitive, license_terms


NCBI_EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
PMC_ARTICLE_URL = "https://pmc.ncbi.nlm.nih.gov/articles/%s/"
FDA_FOOD_ENFORCEMENT = "https://api.fda.gov/food/enforcement.json"
USER_AGENT = "TelegramPlatformPETS/3.1.2 (editorial candidate dry-run)"


@dataclass(frozen=True)
class TopicSpec:
    key: str
    label: str
    category: str
    species: str
    pmc_query: str


def _pets_query(species, terms):
    animal = "(cat[Title] OR feline[Title] OR kitten[Title])" if species == "cat" else "(dog[Title] OR canine[Title] OR puppy[Title])"
    return "%s AND (%s)" % (animal, " OR ".join("%s[Title]" % term for term in terms))


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


def _text(node):
    return re.sub(r"\s+", " ", "".join(node.itertext()) if node is not None else "").strip()


def _sentences(value):
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", value or "") if 50 <= len(part.strip()) <= 500]


def _species(value):
    value = (value or "").lower()
    cat = bool(re.search(r"\b(cat|cats|feline|kitten)\b", value)) and not bool(
        re.search(r"\bcat[-_]|\b[a-z]{2,}[-_]cat\b", value))
    dog = bool(re.search(r"\b(dog|dogs|canine|puppy)\b", value))
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
            topic_terms = CATEGORY_TITLE_TERMS.get(category, ())
            has_topic_signal = any(term in key for term in topic_terms)
            is_noise = any(term in key for term in RESULT_NOISE_TERMS)
            # A Result sentence which contains neither the selected theme nor
            # the animal subject is usually sample/table metadata, not an
            # owner-relevant finding.  Do not promote it to a factual brief.
            has_animal_signal = bool(re.search(r"\b(cat|cats|feline|kitten|dog|dogs|canine|puppy)\b", key))
            if (is_noise and not has_topic_signal) or (kind == "result" and not (has_topic_signal or has_animal_signal)):
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

    title_matches_category = _title_matches_category(title, candidate.get("category"))
    if not excluded and title_matches_category and candidate.get("category") in useful_categories:
        score += 2
    else:
        reasons.append("owner_relevance: excluded=%s; title_matches_category=%s" %
                       (excluded or "none", title_matches_category))
    if candidate.get("topic_key") and candidate.get("species") in {"cat", "dog", "both"} and title_matches_category:
        score += 2
    else:
        reasons.append("channel_fit: animal or topic is not explicit")
    if len(facts) >= 3:
        score += 2
    else:
        reasons.append("facts: fewer than three full-text facts")
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
    if candidate.get("species") in {"cat", "dog", "both"} and not excluded and title_matches_category:
        score += 2
    else:
        reasons.append("image: an unambiguous, relevant photo may not be selectable")

    ready = score >= 12 and not reasons and candidate.get("technical_status") == "source_usable"
    return {
        "score": score,
        "max_score": 14,
        "criteria": {
            "owner_usefulness": not bool(excluded), "channel_fit": bool(candidate.get("topic_key")),
            "specific_facts": len(facts) >= 3, "evidence": any(f.fact_kind != "unknown" for f in facts),
            "plain_language": bool(facts), "medical_safety": not bool(medical),
            "image_feasible": candidate.get("species") in {"cat", "dog", "both"},
        },
        "reasons": reasons,
        "decision": "editorially_ready" if ready else "needs_editorial_review",
    }


class PmcOpenAccessAdapter:
    """Official PMC E-utilities full-text connector with topic catalogue."""
    source_id = "pmc_oa"
    source_name = "PubMed Central Open Access"
    source_type = "primary_research"
    journal_query = ""

    def __init__(self, session=requests, email="pets-platform@example.invalid", tool="pets_platform"):
        self.session, self.email, self.tool = session, email, tool

    def _get(self, endpoint, **params):
        params.update({"tool": self.tool, "email": self.email})
        response = self.session.get(NCBI_EUTILS + endpoint, params=params,
                                    headers={"User-Agent": USER_AGENT}, timeout=30)
        if response.status_code != 200:
            raise RuntimeError("pmc_http_%s" % response.status_code)
        return response

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
        species = _species(title)
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
        candidate = {
            "source_key": "pmc:" + pmcid, "source_id": self.source_id, "title": title,
            "species": species, "doi": doi, "source_url": source_url, "authors": ", ".join(authors),
            "published_at": year, "license": license_name, "license_source_url": license_url or source_url,
            "attribution_requirements": obligations, "adaptation_allowed": adaptation_allowed,
            "technical_status": technical_status, "topic_key": spec.key, "category": spec.category,
            "facts": facts, "limitations": limitations,
            "safety_status": "review" if (not adaptation_allowed or _medical_text(title, facts)) else "candidate_ready",
        }
        candidate["editorial"] = editorial_assessment(candidate)
        candidate["editorial_status"] = candidate["editorial"]["decision"]
        return candidate

    def collect_candidates(self, limit=10):
        candidates, seen = [], set()
        # Rotate cat/dog catalogue entries; caps make the network test bounded.
        for spec in TOPIC_CATALOG:
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


def _candidate_identity(candidate):
    return candidate.get("doi") or candidate.get("source_key")


def collect_source_candidates(adapters, storage=None, limit=10):
    """Collect independently, deduplicate DOI/PMCID across sources, persist reasons."""
    report, accepted, seen, rejected = {}, [], set(), 0
    for source_id, adapter in (adapters or {}).items():
        try:
            found = list(adapter.collect_candidates(limit=max(limit * 2, 10)))
            unique = []
            for candidate in found:
                identity = _candidate_identity(candidate)
                if identity in seen:
                    rejected += 1
                    continue
                seen.add(identity)
                unique.append(candidate)
                if storage is not None:
                    storage.save_source_candidate(candidate)
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
    return (ready + review)[:limit], report, {"deduplicated": rejected, "total_unique": len(accepted)}
