# -*- coding: utf-8 -*-
"""Fail-closed rights contract and Wikimedia Commons resolver for PETS."""
import re

import requests

from .editorial_profiles import _breed_from


_OPEN_LICENSES = {"CC0-1.0", "CC-BY-4.0", "CC-BY-SA-4.0", "Public-Domain"}
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
COMMONS_HEADERS = {"User-Agent": "TelegramPlatformPETS/1.0 (owner-managed educational drafts)"}


def topic_query(title, text=""):
    """Search only for the animal/topic actually named by the material."""
    breed = _breed_from((title or "") + " " + (text or ""))
    if breed:
        return breed.replace("_", " ")
    low = ((title or "") + " " + (text or "")).lower()
    if re.search(r"кошк|кот[а-я]*|cat|kitten", low):
        return "domestic cat"
    if re.search(r"собак|щен|dog|puppy", low):
        return "domestic dog"
    return "pet animal"


def _plain(value):
    return re.sub(r"<[^>]+>", "", str(value or "")).strip()


def resolve_wikimedia_commons(candidate, ext, session=requests, limit=12):
    """Return one verifiably open Commons image or ``None``.

    No source-article image is reused. The API response supplies the original
    URL, author/credit, licence URL and page URL; ambiguous species/breed or
    missing metadata is rejected rather than guessed.
    """
    title = (ext or {}).get("title") or ""
    text = (ext or {}).get("text") or ""
    query = str((ext or {}).get("image_query") or topic_query(title, text)).strip()
    params = {"action": "query", "format": "json", "generator": "search",
              "gsrsearch": query, "gsrnamespace": 6, "gsrlimit": limit,
              "prop": "imageinfo|categories", "iiprop": "url|extmetadata", "cllimit": 50}
    try:
        response = session.get(COMMONS_API, params=params, headers=COMMONS_HEADERS, timeout=25)
        if response.status_code != 200:
            return None
        pages = (response.json().get("query") or {}).get("pages") or {}
    except Exception:
        return None
    expected_breed = _breed_from(title + " " + text)
    expected_tags = tuple((ext or {}).get("visual_tags") or ())
    if not expected_tags:
        # Without a visual contract only species can be demonstrated, which is
        # insufficient for PETS 3.1.  Leave the material in review instead.
        return None
    aliases = {
        "cat": ("cat", "kitten", "feline"), "dog": ("dog", "puppy", "canine"),
        "owner": ("owner", "handler", "person", "woman", "man"),
        "training": ("training", "train", "reward", "obedience"),
        "home": ("home", "indoor", "house", "room", "domestic"),
        "food": ("food", "feeding", "bowl", "meal"),
        "grooming": ("groom", "brush", "combing"), "walk": ("walk", "leash", "outdoor"),
        "rest": ("sleep", "rest", "bed"), "carrier": ("carrier", "crate"),
        "hygiene": ("hygiene", "wash", "clean"), "enrichment": ("toy", "enrichment", "play"),
        "safe_shelter": ("shelter", "hide", "house", "bed", "box"),
        "outdoor": ("outdoor", "outside", "garden", "yard", "street", "nature"),
    }
    for page in pages.values():
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata") or {}
        licence = _plain((meta.get("LicenseShortName") or {}).get("value"))
        licence = {"CC0": "CC0-1.0", "CC BY 4.0": "CC-BY-4.0",
                   "CC BY-SA 4.0": "CC-BY-SA-4.0",
                   "Public domain": "Public-Domain"}.get(licence, licence)
        author = _plain((meta.get("Artist") or {}).get("value"))
        attribution = _plain((meta.get("Attribution") or {}).get("value")) or author
        licence_url = _plain((meta.get("LicenseUrl") or {}).get("value"))
        url = info.get("url") or ""
        source_url = info.get("descriptionurl") or ""
        page_title = str(page.get("title") or "").lower()
        description = _plain((meta.get("ImageDescription") or {}).get("value"))
        categories = " ".join(str(item.get("title") or "") for item in page.get("categories", []))
        evidence = (page_title + " " + description + " " + categories).lower()
        if expected_breed and expected_breed.replace("_", " ") not in page_title:
            continue
        tags = {tag for tag in expected_tags if any(word in evidence for word in aliases.get(tag, (tag,)))}
        if set(expected_tags) - tags:
            continue
        result = {"url": url, "author": author, "source_url": source_url,
                  "license": licence, "license_url": licence_url,
                  "attribution": attribution, "query": query,
                  "topic_match": "+".join(expected_tags), "semantic_tags": tuple(sorted(tags)),
                  "required_tags": expected_tags, "semantic_evidence": evidence[:1000]}
        if expected_breed:
            result["breed"] = expected_breed
        ok, _ = validate_image(result, title)
        if ok and licence_url:
            return result
    return None


def validate_image(image, title=""):
    if not isinstance(image, dict):
        return False, "image rights metadata is missing"
    required = ("url", "author", "source_url", "license", "license_url", "attribution", "topic_match",
                "semantic_tags", "semantic_evidence")
    if any(not str(image.get(k, "")).strip() for k in required):
        return False, "image rights metadata is incomplete"
    if image.get("license") not in _OPEN_LICENSES:
        return False, "image license is not approved"
    semantic_tags = {str(tag).strip().lower() for tag in image.get("semantic_tags", ()) if str(tag).strip()}
    required_tags = {str(tag).strip().lower() for tag in image.get("required_tags", ()) if str(tag).strip()}
    if not semantic_tags or not required_tags:
        return False, "image semantic context is not verified"
    if not required_tags.issubset(semantic_tags):
        return False, "image does not match the required visual context"
    expected = _breed_from(title)
    actual = str(image.get("breed", "")).strip()
    if expected and actual != expected:
        return False, "breed image cannot be verified"
    return True, ""
