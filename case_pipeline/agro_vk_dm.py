# -*- coding: utf-8 -*-
"""Best-effort private delivery of a published AGRO post for manual VK use.

This is deliberately not a VK pipeline: it neither creates a VK queue nor
changes a material's editorial/Telegram status.  It runs only after the AGRO
channel accepted the post, receives the already-downloaded image bytes, and
uses the existing deterministic VK editor without an extra AI request.
"""
import logging

from . import config, telegram, vk_autopilot

log = logging.getLogger("case.agro_vk_dm")


def _technical_notice(image_present):
    if image_present:
        image_note = "Фото приложено из текущей AGRO-публикации."
    else:
        image_note = "Фото в текущей AGRO-публикации недоступно."
    if config.VK_SOURCE_IMAGES_ALLOWED:
        rights_note = ("Права на повторное использование этого исходного изображения "
                       "для VK подтверждены в настройке платформы.")
    else:
        rights_note = ("Права на повторную публикацию исходного изображения в VK "
                       "не подтверждены: не публикуйте это фото в VK без разрешения.")
    return "Техническая заметка (не часть текста для VK):\n%s\n%s" % (image_note, rights_note)


def _split_copy_text(text):
    """Split only between ready VK paragraphs; never trim or rewrite them."""
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= telegram.MESSAGE_SAFE_LIMIT:
        return [text]
    chunks, current = [], ""
    for block in text.split("\n\n"):
        candidate = block if not current else current + "\n\n" + block
        if len(candidate) <= telegram.MESSAGE_SAFE_LIMIT:
            current = candidate
            continue
        if not current or len(block) > telegram.MESSAGE_SAFE_LIMIT:
            return []
        chunks.append(current)
        current = block
    if current:
        chunks.append(current)
    return chunks


def deliver_after_agro_publication(storage, material_id, post_text, photo=None):
    """Send one prepared VK copy to the owner, once per material.

    All failures are terminal for automatic delivery: this is intentional
    duplicate protection.  A later resend requires an explicit operator
    decision rather than a regular AGRO pipeline rerun.
    """
    if not config.AGRO_VK_DM_ENABLED:
        return {"status": "disabled"}
    if not config.AGRO_VK_DM_CHAT_ID:
        log.warning("agro VK DM skipped for material=%s: chat id is not configured", material_id)
        return {"status": "not_configured"}

    vk_text = vk_autopilot.build_vk_post(post_text, provider=None)
    contract_error = vk_autopilot.vk_post_contract_error(vk_text)
    chunks = _split_copy_text(vk_text)
    if contract_error or not chunks:
        reason = contract_error or "VK text cannot be split without changing it"
        log.warning("agro VK DM skipped for material=%s: %s", material_id, reason)
        return {"status": "not_ready", "reason": reason}

    if not storage.claim_agro_vk_dm_delivery(material_id):
        return {"status": "duplicate", "delivery": storage.agro_vk_dm_delivery(material_id)}

    token, _channel_chat_id = telegram.credentials("agro")
    owner_chat_id = config.AGRO_VK_DM_CHAT_ID
    if not token:
        storage.finish_agro_vk_dm_delivery(material_id, "failed", "AGRO bot token is unavailable")
        return {"status": "failed", "reason": "AGRO bot token is unavailable"}

    def failed(stage, result):
        reason = "%s: %s" % (stage, str(getattr(result, "error", "unknown"))[:200])
        storage.finish_agro_vk_dm_delivery(material_id, "failed", reason)
        log.warning("agro VK DM failed for material=%s at %s", material_id, stage)
        return {"status": "failed", "reason": reason}

    technical = telegram.send_message(token, owner_chat_id, _technical_notice(bool(photo)))
    if not technical.ok:
        return failed("technical_notice", technical)

    message_id = technical.message_id
    if photo is not None:
        # When it fits, the ready-to-copy text is captioned on the original
        # publication image.  Technical/legal information has already gone in
        # a separate message and therefore never contaminates the VK copy.
        caption = chunks[0] if len(chunks) == 1 and len(chunks[0]) <= telegram.CAPTION_LIMIT else None
        image_result = telegram.send_photo(token, owner_chat_id, photo_bytes=photo, caption=caption)
        if not image_result.ok:
            return failed("photo", image_result)
        message_id = image_result.message_id or message_id
        if caption is not None:
            storage.finish_agro_vk_dm_delivery(material_id, "sent", "", message_id)
            return {"status": "sent", "message_id": message_id, "image": True}

    for index, chunk in enumerate(chunks, start=1):
        result = telegram.send_message(token, owner_chat_id, chunk)
        if not result.ok:
            return failed("vk_text_part_%s" % index, result)
        message_id = result.message_id or message_id
    storage.finish_agro_vk_dm_delivery(material_id, "sent", "", message_id)
    return {"status": "sent", "message_id": message_id, "image": bool(photo)}
