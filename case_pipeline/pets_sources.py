# -*- coding: utf-8 -*-
"""Candidate source registry for PETS.

Registration is not activation: a source becomes callable only when its ID is
explicitly placed in PETS_SOURCES after owner approval.  Discovery stays within
the public catalog and does not bypass login, robots or access controls.
"""
import re
from urllib.parse import urljoin, urlsplit

from .httpclient import fetch


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
