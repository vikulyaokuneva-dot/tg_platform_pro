# -*- coding: utf-8 -*-
"""Fail-closed rights contract for PETS images."""
from .editorial_profiles import _breed_from


_OPEN_LICENSES = {"CC0-1.0", "CC-BY-4.0", "CC-BY-SA-4.0", "Public-Domain"}


def validate_image(image, title=""):
    if not isinstance(image, dict):
        return False, "image rights metadata is missing"
    required = ("url", "author", "source_url", "license", "attribution")
    if any(not str(image.get(k, "")).strip() for k in required):
        return False, "image rights metadata is incomplete"
    if image.get("license") not in _OPEN_LICENSES:
        return False, "image license is not approved"
    expected = _breed_from(title)
    actual = str(image.get("breed", "")).strip()
    if expected and actual != expected:
        return False, "breed image cannot be verified"
    return True, ""
