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


def adapters_for(source_ids):
    return {name: PetsCatalogAdapter(name, *SOURCE_CANDIDATES[name])
            for name in source_ids if name in SOURCE_CANDIDATES}
