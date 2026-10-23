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
    "PUBLIC_DOMAIN", "CC0", "CC_BY", "CC_BY_NC_ND", "COPYRIGHT", "UNKNOWN",
}
AUTOMATIC_FACT_LICENSES = {"PUBLIC_DOMAIN", "CC0", "CC_BY"}
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
    adaptation_allowed: bool = False
    evidence_level: str = "unknown"

    def serializable(self):
        value = asdict(self)
        value["accessed_at"] = value["accessed_at"] or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return value


def normalize_license(value):
    raw = str(value or "UNKNOWN").strip().upper().replace("-", "_").replace(" ", "_")
    aliases = {
        "PUBLICDOMAIN": "PUBLIC_DOMAIN", "CC0_1_0": "CC0", "CC_BY_4_0": "CC_BY",
        "CC_BY_SA_4_0": "CC_BY", "CC_BY_NC_ND_4_0": "CC_BY_NC_ND",
    }
    raw = aliases.get(raw, raw)
    return raw if raw in KNOWN_LICENSES else "UNKNOWN"


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
    license_name = normalize_license(fact.license)
    if license_name not in AUTOMATIC_FACT_LICENSES or not fact.adaptation_allowed:
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


def validate_generated_text(text, facts):
    """Reject a model output that introduces visible unsupported numbers/safety claims."""
    value = str(text or "")
    if not value.strip():
        return False, "generated_text_empty"
    source_numbers = set()
    for fact in facts or ():
        source_numbers.update(re.findall(r"\b\d+(?:[.,]\d+)?\b", fact.claim))
    generated_numbers = set(re.findall(r"\b\d+(?:[.,]\d+)?\b", value))
    if not generated_numbers.issubset(source_numbers):
        return False, "generated_text_has_unsupported_number"
    lower = value.lower()
    if any(term in lower for term in ("дозиров", "назначьте препарат", "вылечит", "гарантирован")):
        return False, "generated_text_has_unsafe_claim"
    if not any(fact.source_url in value for fact in facts or ()):
        return False, "generated_text_source_links_missing"
    return True, ""
