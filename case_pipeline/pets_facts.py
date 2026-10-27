# -*- coding: utf-8 -*-
"""Contracts and fail-closed validation for PETS source facts.

Source adapters hand the editorial pipeline short, traceable factual claims –
never an article body that could be rewritten.  This module is intentionally
dependency-free so fixtures can exercise the complete safety path offline.
"""
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import re
from urllib.parse import urlparse


KNOWN_LICENSES = {
    "PUBLIC_DOMAIN", "CC0", "CC_BY", "CC_BY_SA", "OGL_3_0", "CC_BY_NC", "CC_BY_NC_SA", "CC_BY_NC_ND", "COPYRIGHT", "UNKNOWN",
}
AUTOMATIC_FACT_LICENSES = {"PUBLIC_DOMAIN", "CC0", "CC_BY", "CC_BY_SA", "OGL_3_0"}
SENSITIVE_TERMS = (
    "дозиров", "лекарств", "препарат", "лечение", "диагноз", "токсин",
    "отрав", "экстрен", "emergency", "dose", "medication", "treatment",
)


@dataclass(frozen=True)
class Fact:
    topic: str
    species: str
    claim: str
    source_url: str
    source_name: str
    source_type: str
    author_or_body: str
    published_at: str | None = None
    accessed_at: str | None = None
    license: str = "UNKNOWN"
    license_source_url: str = ""
    attribution_requirements: str = ""
    adaptation_allowed: bool = False
    evidence_level: str = "unknown"
    license_verified_at: str | None = None
    source_section: str = ""
    fact_kind: str = "unknown"

    def serializable(self):
        value = asdict(self)
        value["accessed_at"] = value["accessed_at"] or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        value["license_verified_at"] = value["license_verified_at"] or value["accessed_at"]
        return value


def normalize_license(value):
    raw = str(value or "UNKNOWN").strip().upper().replace("-", "_").replace(" ", "_").replace(".", "_")
    aliases = {
        "PUBLICDOMAIN": "PUBLIC_DOMAIN", "CC0_1_0": "CC0", "CC_BY_4_0": "CC_BY",
        "CC_BY_SA_4_0": "CC_BY_SA", "CC_BY_NC_4_0": "CC_BY_NC",
        "CC_BY_NC_SA_4_0": "CC_BY_NC_SA", "CC_BY_NC_ND_4_0": "CC_BY_NC_ND",
        "OGL": "OGL_3_0", "OGL_3": "OGL_3_0", "OGL_V3_0": "OGL_3_0",
    }
    raw = aliases.get(raw, raw)
    return raw if raw in KNOWN_LICENSES else "UNKNOWN"


def license_terms(license_name):
    """Return permission and obligations separately; never relabel CC BY-SA."""
    normalized = normalize_license(license_name)
    terms = {
        "PUBLIC_DOMAIN": (True, "attribute source when supplied"),
        "CC0": (True, "attribution is courteous but not required by CC0"),
        "CC_BY": (True, "credit author, source and licence"),
        "CC_BY_SA": (True, "credit author, source and licence; share adaptations under the same licence"),
        "OGL_3_0": (True, "acknowledge the information provider and source; link to the Open Government Licence where possible"),
        "CC_BY_NC": (False, "non-commercial licence; automatic commercial reuse is blocked"),
        "CC_BY_NC_SA": (False, "non-commercial/share-alike licence; automatic reuse is blocked"),
        "CC_BY_NC_ND": (False, "no-derivatives licence; automatic adaptation is blocked"),
    }
    allowed, obligations = terms.get(normalized, (False, "rights are unknown or incompatible"))
    return normalized, allowed, obligations


def validate_fact(fact):
    """Return ``(ok, reason)`` without ever inferring a missing fact or right."""
    if not isinstance(fact, Fact):
        return False, "fact_contract_invalid"
    if not fact.topic.strip() or not fact.claim.strip() or not fact.source_name.strip():
        return False, "fact_required_field_missing"
    if fact.species not in {"cat", "dog", "both", "general"}:
        return False, "fact_species_invalid"
    parsed = urlparse(fact.source_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False, "fact_source_url_invalid"
    license_name, allowed, _ = license_terms(fact.license)
    if license_name not in AUTOMATIC_FACT_LICENSES or not allowed or not fact.adaptation_allowed:
        return False, "source_rights_require_review"
    if not fact.evidence_level.strip():
        return False, "fact_evidence_missing"
    return True, ""


def is_sensitive(fact):
    text = (fact.topic + " " + fact.claim).lower()
    return any(term in text for term in SENSITIVE_TERMS)


def validate_fact_set(facts):
    """Validate traceability and apply the stricter medical-safety threshold."""
    facts = list(facts or ())
    if not facts:
        return False, "facts_missing"
    for fact in facts:
        ok, reason = validate_fact(fact)
        if not ok:
            return False, reason
    sensitive = [fact for fact in facts if is_sensitive(fact)]
    if sensitive:
        independent = {urlparse(fact.source_url).netloc.lower() for fact in facts}
        strong = {"guideline", "regulatory", "primary_research"}
        if len(independent) < 2 and not any(fact.evidence_level in strong for fact in sensitive):
            return False, "sensitive_claim_requires_stronger_evidence"
        # Medication, dosage and emergency instructions are manual-review only.
        if any(any(term in fact.claim.lower() for term in ("дозиров", "dose", "лекарств", "medication", "экстрен", "emergency"))
               for fact in sensitive):
            return False, "sensitive_claim_requires_manual_review"
    return True, ""


_LICENSE_VERSION_RE = re.compile(
    r"\b(?:open\s+government\s+licen[cs]e|ogl|cc(?:[-\s]?(?:by|by[-\s]?sa))?)"
    r"\s*(?:v(?:ersion)?\s*)?\d+(?:\.\d+)?\b", re.I)


def validate_generated_text(text, facts, *, citation_text="", allowed_source_urls=()):
    """Reject a model output that introduces visible unsupported numbers/safety claims."""
    value = str(text or "")
    if not value.strip():
        return False, "generated_text_empty"
    source_numbers = set()
    for fact in facts or ():
        source_numbers.update(re.findall(r"\b\d+(?:[.,]\d+)?\b", fact.claim))
    # Licence versions (for example ``OGL v3.0``) are attribution metadata,
    # not editorial numerical claims.  Strip only recognised licence markers;
    # every other visible number still has to be supported by a source fact.
    numeric_value = _LICENSE_VERSION_RE.sub("", value)
    generated_numbers = set(re.findall(r"\b\d+(?:[.,]\d+)?\b", numeric_value))
    if not generated_numbers.issubset(source_numbers):
        return False, "generated_text_has_unsupported_number"
    lower = value.lower()
    if any(term in lower for term in ("дозиров", "назначьте препарат", "вылечит", "гарантирован")):
        return False, "generated_text_has_unsafe_claim"
    # The Telegram layout may append a source link outside the AI body.  It is
    # still part of the rendered post, so validate it without forcing the model
    # to duplicate a long URL in its prose.
    cited = value + "\n" + str(citation_text or "")
    source_urls = {str(fact.source_url) for fact in facts or () if str(fact.source_url)}
    source_urls.update(str(url) for url in (allowed_source_urls or ()) if str(url))
    if not any(url in cited for url in source_urls):
        return False, "generated_text_source_links_missing"
    return True, ""
