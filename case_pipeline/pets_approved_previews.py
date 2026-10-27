# -*- coding: utf-8 -*-
"""Explicitly approved PETS previews, separate from demos and evergreen posts."""

from .pets_facts import Fact, validate_fact_set, validate_generated_text
from . import pets_images, utils


FIRST_POST_ID = "pets46-apartment-dog-government-guidance"


def _facts():
    common = {
        "topic": "Собака для квартиры: выбор с учётом образа жизни", "species": "dog",
        "source_url": "https://www.nidirect.gov.uk/buying-a-puppy",
        "source_name": "nidirect / Department of Agriculture, Environment and Rural Affairs",
        "source_type": "government_guidance", "author_or_body": "Northern Ireland Executive",
        "license": "OGL-3.0", "license_source_url": "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
        "attribution_requirements": "Acknowledge the information provider and source; link to the Open Government Licence where possible.",
        "adaptation_allowed": True, "evidence_level": "government_guidance",
    }
    return (
        Fact(**common, source_section="Lifestyle", fact_kind="owner_planning", claim="Перед выбором собаки стоит оценить, сколько времени хозяин обычно проводит вне дома и сможет ли он регулярно уделять ей время."),
        Fact(**common, source_section="Environment", fact_kind="environment", claim="Для собаки необходимо безопасное место, где она может спокойно отдыхать и чувствовать себя комфортно."),
        Fact(**common, source_section="Exercise, training, play", fact_kind="owner_planning", claim="При оценке совместимости с домашним режимом нужно учитывать возможности для прогулок, занятий и игры, а не только площадь жилья."),
    )


_FIRST_POST = {
    "source_url": "https://www.gov.uk/government/publications/code-of-practice-for-the-welfare-of-dogs",
    "title": "Собака для квартиры: важнее не метры, а ваш обычный день",
    "body": """Перед тем как завести собаку, оцените свой обычный день и подумайте, сколько времени вы обычно проводите вне дома. Это поможет понять, сможет ли питомец комфортно жить в квартире и получать достаточно внимания и активности.

Не забывайте, что для собаки важно не только наличие просторной квартиры, но и наличие безопасного и спокойного места дома, где она сможет отдохнуть и расслабиться. А ещё учитывайте возможности для прогулок, занятий и игр, которые вы сможете ей обеспечить.

Размер квартиры сам по себе не является полным критерием выбора собаки. Важнее подумать о вашем режиме дня и о том, сколько времени и сил вы готовы уделять питомцу.

🐾 Источник: Contains public sector information from the Department for Environment, Food & Rural Affairs, licensed under the Open Government Licence v3.0.""",
    "category": "owner_lifestyle", "species": "dog",
    "image": {
        "url": "https://thumb.wikimedia.org/wikipedia/commons/thumb/b/b2/Dog_with_an_ear_accessory_relaxing_indoors_on_a_cozy_afternoon_while_observing_its_surroundings.jpg/1280px-Dog_with_an_ear_accessory_relaxing_indoors_on_a_cozy_afternoon_while_observing_its_surroundings.jpg?utm_source=commons.wikimedia.org&utm_campaign=imageinfo&utm_content=thumbnail",
        "original_url": "https://upload.wikimedia.org/wikipedia/commons/b/b2/Dog_with_an_ear_accessory_relaxing_indoors_on_a_cozy_afternoon_while_observing_its_surroundings.jpg?utm_source=commons.wikimedia.org&utm_campaign=imageinfo&utm_content=original",
        "source_url": "https://commons.wikimedia.org/wiki/File:Dog_with_an_ear_accessory_relaxing_indoors_on_a_cozy_afternoon_while_observing_its_surroundings.jpg",
        "author": "Shixart1985", "attribution": "Shixart1985 / CC BY 2.0", "license": "CC-BY-2.0",
        "license_url": "https://creativecommons.org/licenses/by/2.0/", "query": "dog indoors home", "topic_match": "dog+home",
        "semantic_tags": ("dog", "home"), "required_tags": ("dog", "home"),
        "semantic_evidence": "Dog indoors in a cozy home environment; the Commons file description explicitly identifies a dog indoors.",
    },
}


def queue_first_approved_post(storage):
    """Validate and queue only the owner-approved first preview; never send it."""
    data, facts = dict(_FIRST_POST), _facts()
    facts_ok, facts_reason = validate_fact_set(facts)
    if not facts_ok:
        return {"status": "review", "reason": "facts:" + facts_reason}
    title, body = data["title"], data["body"]
    text_ok, text_reason = validate_generated_text(title + "\n" + body, facts, citation_text=data["source_url"], allowed_source_urls=(data["source_url"],))
    if not text_ok:
        return {"status": "review", "reason": "text:" + text_reason}
    image_ok, image_reason = pets_images.validate_image(data["image"], title)
    if not image_ok:
        return {"status": "review", "reason": "image:" + image_reason}
    existing = storage.seen_url(data["source_url"])
    if existing:
        return {"status": "skipped", "reason": "source_already_%s" % existing["status"]}
    rendered = "%s\n\n%s\n\nИсточник: %s" % (title, body, data["source_url"])
    if storage.content_duplicated(rendered):
        return {"status": "skipped", "reason": "content_duplicate"}
    material_id = storage.add(data["source_url"], "approved_factual_preview")
    if not storage.reserve_topic(material_id, FIRST_POST_ID, data["category"], data["species"]):
        storage.update(material_id, status="rejected", reason="duplicate_semantic_topic")
        return {"status": "rejected", "reason": "duplicate_semantic_topic"}
    storage.record_facts(material_id, facts)
    storage.record_image_rights(material_id, data["image"])
    storage.update(material_id, content_hash=utils.content_hash(rendered), status="post_ready", post_text=rendered,
                   image_url=data["image"]["url"], classification="pets:%s:%s" % (data["category"], data["species"]),
                   reason="pets_expert:owner_approved_preview")
    if not storage.enqueue_verified_material(material_id, origin="owner_approved_preview"):
        storage.update(material_id, status="review", reason="approved_preview_queue_failed")
        return {"status": "review", "reason": "approved_preview_queue_failed"}
    return {"status": "post_ready", "material_id": material_id, "source": "owner_approved_preview"}
