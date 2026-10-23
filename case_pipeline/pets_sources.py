# -*- coding: utf-8 -*-
"""Candidate source registry for PETS.

Registration is not activation: a source becomes callable only when its ID is
explicitly placed in PETS_SOURCES after owner approval.  Discovery stays within
the public catalog and does not bypass login, robots or access controls.
"""
import json
import re
from urllib.parse import urljoin, urlsplit

from .httpclient import fetch
from .pets_facts import Fact


class PetsCatalogAdapter:
    def __init__(self, name, catalog, domain):
        self.name, self.catalog, self.domain = name, catalog, domain

    def accept(self, url):
        path = urlsplit(url).path.rstrip("/")
        if urlsplit(url).netloc.lower().removeprefix("www.") != self.domain:
            return False
        bad = ("/search", "/login", "/account", "/shop", "/privacy", "/terms", "/contact")
        return len(path.split("/")) >= 3 and not any(part in path.lower() for part in bad)

    def discover(self):
        _, html = fetch(self.catalog, timeout=45)
        urls, seen = [], set()
        for href in re.findall(r'''href=["']([^"'#?]+)''', html, re.I):
            url = urljoin(self.catalog, href)
            if self.accept(url) and url not in seen:
                seen.add(url)
                urls.append(url)
        return urls


SOURCE_CANDIDATES = {
    "purina": ("https://www.purina.ru/articles", "purina.ru"),
    "royal_canin": ("https://www.royalcanin.com/", "royalcanin.com"),
    "hills": ("https://www.hillspet.ru/", "hillspet.ru"),
    "akc": ("https://www.akc.org/expert-advice/", "akc.org"),
    "icatcare": ("https://icatcare.org/advice/", "icatcare.org"),
    "cats_protection": ("https://www.cats.org.uk/help-and-advice", "cats.org.uk"),
    "pdsa": ("https://www.pdsa.org.uk/pet-help-and-advice", "pdsa.org.uk"),
    "vca": ("https://vcahospitals.com/know-your-pet", "vcahospitals.com"),
    "merck_vet": ("https://www.merckvetmanual.com/", "merckvetmanual.com"),
    "petmd": ("https://www.petmd.com/", "petmd.com"),
}

# Registration and technical reachability are not permission to transform or
# republish an article.  The legal audit below intentionally keeps all current
# candidates out of PETS_SOURCES until the rightsholder grants a suitable
# written licence.  Merck additionally remains fact-check only.
SOURCE_POLICY = {
    "pdsa": {"mode": "reference_only", "reason": "personal-use terms; written authorisation required"},
    "cats_protection": {"mode": "reference_only", "reason": "reproduction and modification require written permission"},
    "vca": {"mode": "reference_only", "reason": "public reuse/derivative works prohibited"},
    "merck_vet": {"mode": "fact_check_only", "reason": "reuse requires written permission"},
    "purina": {"mode": "reference_only", "reason": "commercial source; reuse not verified"},
    "royal_canin": {"mode": "reference_only", "reason": "commercial source; reuse not verified"},
    "hills": {"mode": "reference_only", "reason": "commercial source; reuse not verified"},
    "akc": {"mode": "reference_only", "reason": "terms prohibit automated reuse"},
    "icatcare": {"mode": "reference_only", "reason": "access/reuse not verified"},
    "petmd": {"mode": "reference_only", "reason": "reuse not verified"},
}


def policy_for(source_id):
    return dict(SOURCE_POLICY.get(source_id, {"mode": "unknown", "reason": "source is not registered"}))


def adapters_for(source_ids):
    """Return only sources explicitly approved for automated adaptation.

    This fail-closed gate means a repository variable cannot accidentally turn
    a reference-only catalogue into an automated copier.
    """
    return {name: PetsCatalogAdapter(name, *SOURCE_CANDIDATES[name])
            for name in source_ids if name in SOURCE_CANDIDATES
            and policy_for(name)["mode"] == "automated_allowed"}


class StructuredFactsAdapter:
    """Base contract for PETS 3.1 official-source adapters.

    ``collect`` calls one documented endpoint only.  It returns short factual
    claims with rights metadata, never an article body.  Tests pass a fixture
    ``fetch_json``; normal runs are disabled until PETS_EXTERNAL_SOURCES=1.
    """
    source_id = "unknown"
    endpoint = ""
    source_name = ""
    source_type = "government"
    body = ""
    license = "UNKNOWN"
    adaptation_allowed = False
    evidence_level = "guideline"

    def __init__(self, fetch_json=None):
        self.fetch_json = fetch_json

    def _fetch(self):
        if self.fetch_json is not None:
            return self.fetch_json(self.endpoint)
        status, raw = fetch(self.endpoint, timeout=45)
        if status != 200:
            raise RuntimeError("source_http_%s" % status)
        return json.loads(raw)

    def claims_from_payload(self, payload):
        """Adapters override this parser; unknown payloads fail closed."""
        return []

    def collect(self):
        return self.claims_from_payload(self._fetch())

    def fact(self, topic, species, claim, url, published_at=None):
        return Fact(topic=topic, species=species, claim=claim, source_url=url,
                    source_name=self.source_name, source_type=self.source_type,
                    author_or_body=self.body, published_at=published_at,
                    license=self.license, adaptation_allowed=self.adaptation_allowed,
                    evidence_level=self.evidence_level)


class FdaCvmAdapter(StructuredFactsAdapter):
    source_id = "fda_cvm"
    endpoint = "https://www.fda.gov/animal-veterinary"
    source_name = "FDA Center for Veterinary Medicine"
    source_type = "government"
    body = "U.S. Food and Drug Administration"
    license = "PUBLIC_DOMAIN"
    adaptation_allowed = True
    evidence_level = "regulatory"

    def claims_from_payload(self, payload):
        # Official RSS/API wrapper fixture: each item already contains a short,
        # attributable agency claim. HTML pages are deliberately not scraped.
        return [[self.fact(item["topic"], item.get("species", "both"), item["claim"],
                           item["url"], item.get("published_at"))]
                for item in (payload or {}).get("items", []) if all(item.get(k) for k in ("topic", "claim", "url"))]


class OpenFdaAdapter(StructuredFactsAdapter):
    source_id = "openfda"
    endpoint = "https://api.fda.gov/animalandveterinary/event.json?limit=10"
    source_name = "openFDA"
    source_type = "government_data"
    body = "U.S. Food and Drug Administration"
    license = "CC0"
    adaptation_allowed = True
    evidence_level = "regulatory"

    def claims_from_payload(self, payload):
        # Raw adverse-event data are not medical recommendations.  A result is
        # marked sensitive by the validator and cannot become post_ready alone.
        result = []
        for item in (payload or {}).get("results", []):
            url = item.get("source_url") or "https://open.fda.gov/apis/animalandveterinary/"
            claim = item.get("claim")
            topic = item.get("topic") or "Сигналы безопасности FDA для владельцев животных"
            if claim:
                result.append([self.fact(topic, item.get("species", "both"), claim, url,
                                         item.get("date"))])
        return result


class CdcHealthyPetsAdapter(StructuredFactsAdapter):
    source_id = "cdc_healthy_pets"
    endpoint = "https://www.cdc.gov/healthy-pets/"
    source_name = "CDC Healthy Pets"
    source_type = "government"
    body = "Centers for Disease Control and Prevention"
    license = "PUBLIC_DOMAIN"
    adaptation_allowed = True
    evidence_level = "guideline"

    def claims_from_payload(self, payload):
        # The production connector accepts only an official structured feed
        # wrapper with ``asset_owner=CDC``; third-party page assets are rejected.
        return [[self.fact(item["topic"], item.get("species", "both"), item["claim"],
                           item["url"], item.get("published_at"))]
                for item in (payload or {}).get("items", [])
                if item.get("asset_owner") == "CDC" and all(item.get(k) for k in ("topic", "claim", "url"))]


class FrontiersVeterinaryAdapter(StructuredFactsAdapter):
    source_id = "frontiers_vet"
    endpoint = "https://www.frontiersin.org/journals/veterinary-science/articles"
    source_name = "Frontiers in Veterinary Science"
    source_type = "primary_research"
    body = "Frontiers in Veterinary Science"
    license = "CC_BY"
    adaptation_allowed = True
    evidence_level = "primary_research"

    def claims_from_payload(self, payload):
        # Article-level licence is mandatory: journal-level CC BY is insufficient
        # when a publication carries an exception or third-party content credit.
        return [[self.fact(item["topic"], item.get("species", "both"), item["claim"],
                           item["url"], item.get("published_at"))]
                for item in (payload or {}).get("items", [])
                if str(item.get("license", "")).upper().replace("-", "_") in {"CC_BY", "CC_BY_4_0"}
                and item.get("article_level_license") is True
                and all(item.get(k) for k in ("topic", "claim", "url"))]


OFFICIAL_SOURCE_ADAPTERS = {
    "fda_cvm": FdaCvmAdapter,
    "openfda": OpenFdaAdapter,
    "cdc_healthy_pets": CdcHealthyPetsAdapter,
    "frontiers_vet": FrontiersVeterinaryAdapter,
}


def official_adapters_for(source_ids):
    return {source_id: OFFICIAL_SOURCE_ADAPTERS[source_id]() for source_id in (source_ids or ())
            if source_id in OFFICIAL_SOURCE_ADAPTERS}
