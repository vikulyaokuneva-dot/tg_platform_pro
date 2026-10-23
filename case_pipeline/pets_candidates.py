# -*- coding: utf-8 -*-
"""Official, rate-limited PETS 3.1.1 source-candidate connectors.

They collect evidence for editorial review only.  They never call a text model,
never publish, and never convert a title or metadata record into a fact.
"""
from datetime import datetime, timezone
import re
import time
import xml.etree.ElementTree as ET

import requests

from .pets_facts import Fact, is_sensitive, license_terms, normalize_license


NCBI_EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
PMC_ARTICLE_URL = "https://pmc.ncbi.nlm.nih.gov/articles/%s/"
FDA_FOOD_ENFORCEMENT = "https://api.fda.gov/food/enforcement.json"
USER_AGENT = "TelegramPlatformPETS/3.1.1 (educational candidate dry-run)"


def _text(node):
    return re.sub(r"\s+", " ", "".join(node.itertext()) if node is not None else "").strip()


def _sentences(value):
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", value or "") if 45 <= len(part.strip()) <= 500]


def _species(value):
    value = (value or "").lower()
    cat = bool(re.search(r"\b(cat|cats|feline|kitten)\b", value))
    dog = bool(re.search(r"\b(dog|dogs|canine|puppy)\b", value))
    return "both" if cat and dog else "cat" if cat else "dog" if dog else "general"


def _pet_species_from_title(title):
    """Accept only records whose title explicitly identifies cats or dogs.

    This intentionally rejects a paper which merely mentions a pet somewhere
    in its abstract.  It avoids turning incidental terms from another species
    into PETS candidates.
    """
    return _species(title)


def _requires_medical_review(title, facts):
    """Clinical studies are evidence, not owner-facing recommendations."""
    medical = (
        "case report", "case series", "clinical", "disease", "carcinoma",
        "cancer", "surgery", "surgical", "anesthe", "treatment", "therapy",
        "diagnos", "prognos", "kidney", "pancreatitis", "lymphoma",
        "fracture", "infection", "medication", "drug", "tumor",
        "clinicopathologic", "malignan", "imaging", "mass", "zoonosis",
        "health", "morbidity", "mortality", "neuter", "neutered",
    )
    text = " ".join([title] + [fact.claim for fact in facts]).lower()
    return any(term in text for term in medical)


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


class PmcOpenAccessAdapter:
    """PMC E-Utilities full-text XML connector with article-level licence check."""
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

    def search_ids(self, limit=10):
        query = self.journal_query or (
            "(dogs[MeSH Terms] OR cats[MeSH Terms]) AND "
            "(behavior[Title/Abstract] OR welfare[Title/Abstract] OR enrichment[Title/Abstract]) "
            "AND open access[filter]")
        response = self._get("esearch.fcgi", db="pmc", term=query, retmax=min(limit * 3, 30),
                             retmode="json", sort="pub date")
        ids = response.json().get("esearchresult", {}).get("idlist", [])
        return [item for item in ids if str(item).isdigit()][:min(limit * 3, 30)]

    def _articles(self, ids):
        if not ids:
            return []
        response = self._get("efetch.fcgi", db="pmc", id=",".join(ids), retmode="xml")
        return ET.fromstring(response.content).findall(".//article")

    def _candidate(self, article):
        title = _text(article.find(".//article-title"))
        abstract = _text(article.find(".//abstract"))
        # PMC full-text XML uses ``pmcid`` (for example ``PMC13683602``),
        # whereas the E-utilities search result itself contains the numeric
        # PMC archive id.  ``pmc`` is not the XML attribute used by current
        # records, so accepting both keeps this connector compatible without
        # treating an arbitrary metadata id as the public article id.
        pmcid = (_text(article.find(".//article-id[@pub-id-type='pmcid']"))
                 or _text(article.find(".//article-id[@pub-id-type='pmc']")))
        doi = _text(article.find(".//article-id[@pub-id-type='doi']"))
        if not title or not abstract or not pmcid:
            return None
        licence_node = article.find(".//license-p")
        licence_text = _text(licence_node)
        license_name = _license_from_text(licence_text)
        license_name, adaptation_allowed, obligations = license_terms(license_name)
        license_url = ""
        if licence_node is not None:
            for link in licence_node.findall(".//ext-link"):
                href = link.attrib.get("{http://www.w3.org/1999/xlink}href") or link.attrib.get("href") or ""
                if href:
                    license_url = href
                    break
        authors = []
        for contrib in article.findall(".//contrib[@contrib-type='author']")[:8]:
            name = _text(contrib.find("name"))
            if name:
                authors.append(name)
        year = _text(article.find(".//pub-date/year"))
        source_url = PMC_ARTICLE_URL % pmcid
        species = _pet_species_from_title(title)
        claims = _sentences(abstract)[:2]
        if not claims or species == "general":
            return None
        facts = tuple(Fact(topic=title, species=species, claim=claim, source_url=source_url,
                           source_name=self.source_name, source_type=self.source_type,
                           author_or_body=", ".join(authors) or self.source_name,
                           published_at=year or None, license=license_name,
                           license_source_url=license_url or source_url,
                           attribution_requirements=obligations,
                           adaptation_allowed=adaptation_allowed,
                           evidence_level="primary_research") for claim in claims)
        sensitive = any(is_sensitive(fact) for fact in facts)
        safety = "review" if (sensitive or not adaptation_allowed
                               or _requires_medical_review(title, facts)) else "candidate_ready"
        return {"source_key": "pmc:" + pmcid, "source_id": self.source_id, "title": title,
                "species": species, "doi": doi, "source_url": source_url,
                "authors": ", ".join(authors), "published_at": year or None,
                "license": license_name, "license_source_url": license_url or source_url,
                "attribution_requirements": obligations, "adaptation_allowed": adaptation_allowed,
                "facts": facts, "safety_status": safety}

    def collect_candidates(self, limit=10):
        # One search + one capped batch fetch; no crawling and no retry loop.
        candidates = []
        for article in self._articles(self.search_ids(limit)):
            candidate = self._candidate(article)
            if candidate:
                candidates.append(candidate)
            if len(candidates) >= limit:
                break
        return candidates


class FrontiersVeterinaryPmcAdapter(PmcOpenAccessAdapter):
    source_id = "frontiers_vet"
    source_name = "Frontiers in Veterinary Science via PMC OA"
    # PMC full-text records do not reliably carry the PubMed MeSH assignment.
    # Search the published title/abstract instead, then require a full-text
    # licence and extract facts from that text below.
    journal_query = (
        'Front Vet Sci[jour] AND (dog[Title] OR cat[Title] OR canine[Title] OR feline[Title]) '
        'AND (behavior[Title] OR welfare[Title] OR enrichment[Title] OR training[Title])'
    )


class FdaCvmSafetyAdapter:
    """Official FDA recall data; candidates always require editorial review."""
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
        candidates = []
        for item in response.json().get("results", []):
            description = str(item.get("product_description") or "").strip()
            reason = str(item.get("reason_for_recall") or "").strip()
            recall_number = str(item.get("recall_number") or "").strip()
            if not description or not reason or not recall_number:
                continue
            species = _species(description)
            if species == "general":
                continue
            url = FDA_FOOD_ENFORCEMENT + "?search=recall_number:%s" % recall_number
            claim = "FDA enforcement record %s lists product '%s' with recall reason: %s." % (recall_number, description, reason)
            facts = (Fact(topic="FDA animal-food safety record", species=species, claim=claim, source_url=url,
                          source_name=self.source_name, source_type="government_data",
                          author_or_body="U.S. Food and Drug Administration", published_at=item.get("recall_initiation_date"),
                          license="PUBLIC_DOMAIN", license_source_url="https://www.fda.gov/about-fda/website-policies/website-disclaimer",
                          attribution_requirements="credit FDA and do not imply endorsement", adaptation_allowed=True,
                          evidence_level="regulatory"),)
            candidates.append({"source_key": "fda:" + recall_number, "source_id": self.source_id,
                               "title": "FDA recall record " + recall_number, "species": species, "doi": "",
                               "source_url": url, "authors": "U.S. Food and Drug Administration",
                               "published_at": item.get("recall_initiation_date"), "license": "PUBLIC_DOMAIN",
                               "license_source_url": "https://www.fda.gov/about-fda/website-policies/website-disclaimer",
                               "attribution_requirements": "credit FDA and do not imply endorsement",
                               "adaptation_allowed": True, "facts": facts, "safety_status": "review"})
        return candidates


def collect_source_candidates(adapters, storage=None, limit=10):
    """Collect independent source reports; one failed source never hides others."""
    report, candidates = {}, []
    for source_id, adapter in (adapters or {}).items():
        try:
            found = list(adapter.collect_candidates(limit=limit))
            for candidate in found:
                if storage is not None:
                    storage.save_source_candidate(candidate)
            report[source_id] = {"status": "ok", "found": len(found),
                                 "candidate_ready": sum(c["safety_status"] == "candidate_ready" for c in found),
                                 "review": sum(c["safety_status"] == "review" for c in found)}
            candidates.extend(found)
        except Exception as exc:
            report[source_id] = {"status": "error", "error": type(exc).__name__}
    return candidates[:limit], report
