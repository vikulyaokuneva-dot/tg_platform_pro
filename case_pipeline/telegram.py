# -*- coding: utf-8 -*-
"""case_pipeline.telegram — publisher валидированного поста.

Принимает ГОТОВЫЙ текст: никакой классификации/решений здесь.
В dry-run ничего не отправляет. Токен НЕ логируется и в отчёты не попадает.
"""
import logging
import re
import time

import requests

from . import config, postformat

log = logging.getLogger("case_pipeline.telegram")

API = "https://api.telegram.org/bot%s/%s"
# лимит подписи к фото (Bot API): если ГОТОВЫЙ пост (после экранирования
# MarkdownV2) помещается в него целиком — публикация одним сообщением,
# пара «фото + текст» не создаётся
CAPTION_LIMIT = 1024
# лимит текстового сообщения (Bot API) и безопасный порог для продолжения
# (запас 6 симв. — как в прежнем страховочном clamping): split_for_photo
# проверяет продолжение по нему ДО отправки фото, чтобы не рвать статью
MESSAGE_LIMIT = 4096
MESSAGE_SAFE_LIMIT = MESSAGE_LIMIT - 6


class PublishResult:
    def __init__(self, ok, message_id=None, error=None, http_status=None):
        self.ok = ok
        self.message_id = message_id
        self.error = error
        self.http_status = http_status


def send_message(token, chat_id, text, dry_run=False, parse_mode=None, retries=2):
    """Низкий уровень отправки. Параметры token/chat_id ОБЯЗАТЕЛЬНЫ для
    реального send: скрытых env-fallback нет — канал обязан передать свою
    пару явно (см. credentials()). Это исключает ситуацию, когда второй
    канал без секрета молча уходит в чат первого."""
    if dry_run:
        log.info("DRY-RUN: публикация не выполняется (%d симв.)", len(text))
        return PublishResult(True, message_id=0, error="dry-run")
    token = token or ""
    if not token or not chat_id:
        return PublishResult(False, error="no bot token/chat_id "
                                          "(set channel credentials explicitly)")
    payload = {"chat_id": chat_id, "text": text,
               "disable_web_page_preview": False}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    last = None
    for attempt in range(retries + 1):
        try:
            r = requests.post(API % (token, "sendMessage"), json=payload, timeout=30)
            data = r.json() if r.content else {}
            if data.get("ok"):
                return PublishResult(True, message_id=data["result"]["message_id"],
                                     http_status=r.status_code)
            last = "%s %s" % (r.status_code, str(data.get("description", ""))[:200])
            # 429 — вежливый retry с backoff; 400 (например, parse) — как есть
            if r.status_code == 429:
                time.sleep(data.get("parameters", {}).get("retry_after", 3) or 3)
                continue
            if r.status_code == 400 and not parse_mode:
                break
        except Exception as e:
            last = type(e).__name__
            time.sleep(2)
    return PublishResult(False, error=str(last))


def credentials(channel="ai"):
    """Токен/чат по имени канала.

    ``ai`` и ``pets`` используют один управляющий bot token, но разные
    chat_id; ``agro`` получает тот же GitHub Secret через свой env-mapping.
    Изолированным остаётся именно target chat, а не идентичность бота.
    Секретов в коде нет: только env (см. config). -> (token, chat_id)
    """
    if channel == "agro":
        return config.AGRO_BOT_TOKEN, config.AGRO_CHAT_ID
    if channel == "pets":
        return config.BOT_TOKEN, config.PETS_CHAT_ID
    return config.BOT_TOKEN, config.CHAT_ID


def _cut_words(s, n):
    """Обрезка до n символов по границе слова: в MarkdownV2 резать можно
    только по пробелам — иначе можно разрезать escape-последовательность."""
    if len(s) <= n:
        return s
    piece = s[:n]
    i = piece.rfind(" ")
    if i <= 0:
        i = n
    return s[:i].rstrip().rstrip("\\") + "…"


def fit_caption(md, limit=CAPTION_LIMIT):
    """Caption ≤ limit для sendPhoto: заголовок, строка «Источник:» и хэштеги
    сохраняются всегда, тело ужимается по границам слов (лимит считается по
    уже экранированному тексту — как его считает Telegram)."""
    if len(md) <= limit:
        return md
    blocks = md.split("\n\n")
    head = blocks[0]
    src_i = next((i for i, b in enumerate(blocks)
                  if b.lstrip().startswith("Источник")), len(blocks))
    tail = blocks[src_i:]
    middle = blocks[1:src_i]

    def total():
        return len("\n\n".join([head] + middle + tail))

    for _ in range(100):
        if total() <= limit:
            break
        over = total() - limit
        if middle:
            joined = "\n\n".join(middle)
            new = _cut_words(joined, max(40, len(joined) - over))
            middle = new.split("\n\n") if new != joined else middle[:-1]
        else:
            inner = head[1:-1] if (head.startswith("*") and len(head) > 2
                                   and head.endswith("*")) else head
            new = _cut_words(inner, max(20, len(inner) - over))
            if new == inner:
                break
            head = ("*%s*" % new) if (head.startswith("*") and len(head) > 2
                                      and head.endswith("*")) else new
    return "\n\n".join([head] + middle + tail)


def publish_post(text, chat_id=None, dry_run=False, channel="ai", image=None):
    """Финальная подача поста: целевой макет канала (жирный заголовок/поля,
    пустые строки между блоками) + валидный MarkdownV2 с полным экранированием
    (postformat). Механизм отправки и ретраи — прежние. Откат безопасный: если
    API отверг разметку (400 parse) или длина после экранирования близка к
    лимиту — тот же текст уходит plain text (без parse_mode).

    channel: 'ai' (default, поведение идентично прежнему) | 'agro'.
    image: bytes — публикация фото и текста как ЕДИНОЙ публикации: если
    весь пост (после экранирования MarkdownV2) помещается в лимит подписи
    CAPTION_LIMIT — одно sendPhoto с полным текстом, второго сообщения нет.
    Если не помещается (лимит Bot API на подпись — 1024 симв.) —
    (1) sendPhoto с подписью, заполненной целыми абзацами тела
    (postformat.split_for_photo: разрез только по границам смысловых
    блоков — абзац/список не рвётся посередине), затем (2)
    сообщение-ПРОДОЛЖЕНИЕ отдельной отправкой (первая строка — пометка
    «Продолжение», далее остаток тела БЕЗ повторного заголовка и без
    того, что уже в подписи — msg80/81: читатель видит его прямо под
    фото). «Источник:» + хэштеги — РОВНО ОДИН РАЗ в конце последнего
    сообщения (в подписи длинного поста источника нет); продолжение
    проверяется на лимит MESSAGE_LIMIT. Если пост разделить без потерь
    невозможно — честный отказ ДО отправки (фото не уходит, текст не
    режется): материал уходит на ручную проверку в agro.process_url.
    Без image — прежний текстовый путь."""
    token, target_chat = credentials(channel)
    # agro-канал: ведущий эмодзи заголовка — часть стиля и НЕ удаляется
    is_agro = channel == "agro"
    formatted = postformat.format_post(text,
                                       keep_headline_emoji=is_agro,
                                       agro_style=is_agro)
    # AGRO has a single HTML payload path: it can safely wrap a multi-line
    # conclusion in <i>...</i>, while the AI lane keeps its existing
    # MarkdownV2 contract unchanged.
    render = postformat.to_telegram_html if is_agro else postformat.to_markdownv2
    parse_mode = "HTML" if is_agro else "MarkdownV2"
    to_plain = (postformat.unescape_telegram_html if is_agro
                else postformat.unescape_markdownv2)
    rendered = render(formatted)
    if dry_run:
        return send_message(token, chat_id or target_chat,
                            rendered, dry_run=True, parse_mode=parse_mode)
    if not token or not (chat_id or target_chat):
        # честный стоп: без секретов канала НЕ уходим в чужой токен/чат
        return PublishResult(False, error="no credentials for channel %s" % channel)
    if image:
        target = chat_id or target_chat
        # 0) весь пост помещается в подпись (≤CAPTION_LIMIT) -> ЕДИНАЯ
        # публикация: фото с полным текстом, второго сообщения нет (не
        # создаём «второй пост» из одного и того же материала)
        if len(rendered) <= CAPTION_LIMIT:
            res = send_photo(token, target, photo_bytes=image,
                             caption=rendered, parse_mode=parse_mode)
            if not res.ok:
                err = str(res.error or "").lower()
                if "400" in err and "parse" in err:
                    log.warning("caption markup rejected (400 parse) — "
                                "повтор без parse_mode")
                    res = send_photo(token, target, photo_bytes=image,
                                     caption=to_plain(rendered))
                if not res.ok:
                    log.error("telegram photo publish failed: %s", res.error)
                    return res
            log.info("photo published with full caption #%s (%d chars)",
                     res.message_id, len(rendered))
            return res
        # 1) не помещается в подпись: подпись заполняется целыми абзацами
        # тела (разрез только по границам смысловых блоков) + сообщение-
        # продолжение с остатком — без повторного заголовка и без дублей
        cap_plain, msg_plain = postformat.split_for_photo(
            formatted, caption_limit=CAPTION_LIMIT,
            message_limit=MESSAGE_SAFE_LIMIT, render=render)
        if cap_plain is None:
            # корректное деление без потерь невозможно: в подпись не
            # помещается ни один абзац тела, либо продолжение с пометкой,
            # разметкой и источником не влезает в лимит сообщения.
            # ЧЕСТНЫЙ ОТКАЗ ДО отправки — фото не уходит, статья не
            # режется и не дублируется; в agro.process_url материал
            # уходит на ручную проверку (review)
            log.error("unsplittable post: no whole body block fits caption "
                      "or continuation exceeds message limit")
            return PublishResult(False,
                                 error="post cannot be split without loss")
        caption = render(cap_plain)
        if not is_agro:
            caption = fit_caption(caption, CAPTION_LIMIT)
        res = send_photo(token, target, photo_bytes=image,
                         caption=caption, parse_mode=parse_mode)
        if not res.ok:
            err = str(res.error or "").lower()
            if "400" in err and "parse" in err:
                log.warning("caption markup rejected (400 parse) — повтор без parse_mode")
                res = send_photo(token, target, photo_bytes=image,
                                 caption=to_plain(caption))
            if not res.ok:
                log.error("telegram photo publish failed: %s", res.error)
                return res
        # 2) полный текст отдельным сообщением (фото — над текстом в ленте)
        full_md = render(msg_plain)
        if len(full_md) > MESSAGE_SAFE_LIMIT and not is_agro:
            # страховка: split_for_photo уже проверил продолжение по
            # MESSAGE_SAFE_LIMIT ДО отправки фото, а контракт ИИ-редактуры
            # держит пост ≤3400 симв. — путь не должен срабатывать
            log.warning("full text %d chars > %d после экранирования — clamping",
                        len(full_md), MESSAGE_SAFE_LIMIT)
            full_md = fit_caption(full_md, MESSAGE_SAFE_LIMIT)
        res2 = send_message(token, target, full_md, parse_mode=parse_mode)
        if not res2.ok:
            err = str(res2.error or "").lower()
            if "400" in err and "parse" in err:
                log.warning("markup rejected (400 parse) — повтор plain text")
                res2 = send_message(token, target,
                                    to_plain(full_md))
        if not res2.ok:
            # фото ушло, текст нет -> честный отказ (-> review без
            # авто-повтора, чтобы фото не задублировалось)
            log.error("telegram text publish failed (photo sent #%s): %s",
                      res.message_id, res2.error)
            return PublishResult(False, message_id=res.message_id,
                                 error="text message: %s" % res2.error,
                                 http_status=res2.http_status)
        log.info("pair published: photo #%s + text #%s",
                 res.message_id, res2.message_id)
        return PublishResult(True, message_id=res.message_id,
                             http_status=res.http_status)
    if len(rendered) <= 4090:
        res = send_message(token, chat_id or target_chat, rendered,
                           parse_mode=parse_mode)
        if res.ok:
            return res
        err = str(res.error or "").lower()
        if "400" not in err or "parse" not in err:
            log.error("telegram publish failed: %s", res.error)
            return res
        log.warning("markup rejected (400 parse) — повтор plain text")
    # plain-fallback: чистый текст без markdown-символов (** и _ не попадают
    # в опубликованное сообщение, даже если API отверг разметку)
    res = send_message(token, chat_id or target_chat,
                       to_plain(rendered))
    if not res.ok:
        log.error("telegram publish failed: %s", res.error)
    return res


def send_photo(token, chat_id, photo_url=None, photo_bytes=None,
               caption=None, dry_run=False, retries=2, parse_mode=None):
    """Отправка фото в Telegram (sendPhoto). Поддерживает два режима:
      - photo_url: Telegram сам скачивает (может вернуть 400 failed to get HTTP URL content);
      - photo_bytes: multipart upload (надёжнее для CDN с защитой от ботов).
    Token/chat_id обязательны; fallback нет. Caption <= 1024 символов;
    parse_mode — разметка caption (по умолчанию plain, без parse_mode)."""
    label = (photo_url or "(bytes)")[:80]
    if dry_run:
        log.info("DRY-RUN: send_photo не выполняется (%s)", label)
        return PublishResult(True, message_id=0, error="dry-run")
    if not token or not chat_id:
        return PublishResult(False, error="no bot token/chat_id for send_photo")
    if photo_bytes is not None:
        files = {"photo": ("photo.jpg", photo_bytes, "image/jpeg")}
        data_payload = {"chat_id": chat_id}
    elif photo_url:
        files = None
        data_payload = {"chat_id": chat_id, "photo": photo_url}
    else:
        return PublishResult(False, error="send_photo: no photo_url or photo_bytes")
    if caption:
        data_payload["caption"] = caption
    if parse_mode:
        data_payload["parse_mode"] = parse_mode
    last = None
    for attempt in range(retries + 1):
        try:
            if files is not None:
                r = requests.post(API % (token, "sendPhoto"),
                                  data=data_payload, files=files, timeout=60)
            else:
                r = requests.post(API % (token, "sendPhoto"),
                                  json=data_payload, timeout=30)
            resp = r.json() if r.content else {}
            if resp.get("ok"):
                msg = resp["result"]
                mid = msg.get("message_id") if isinstance(msg, dict) else None
                return PublishResult(True, message_id=mid, http_status=r.status_code)
            last = "%s %s" % (r.status_code, str(resp.get("description", ""))[:200])
            if r.status_code == 429:
                time.sleep(resp.get("parameters", {}).get("retry_after", 3) or 3)
                continue
        except Exception as e:
            last = type(e).__name__
            time.sleep(2)
    return PublishResult(False, error=str(last))


def get_me(dry_run=False, channel="ai"):
    """Проверка токена/доступности бота (для self-test). Возвращает либо
    {"username":...,"id":...}, либо {"error": "<без секретов>"}. Токен не раскрывается."""
    token, _chat_id = credentials(channel)
    if not token:
        return None
    try:
        r = requests.get(API % (token, "getMe"), timeout=20)
        try:
            data = r.json()
        except ValueError:
            return {"error": "non-JSON response, HTTP %s" % r.status_code}
        if data.get("ok"):
            return {"username": data["result"].get("username"), "id": data["result"].get("id")}
        return {"error": "HTTP %s: %s" % (r.status_code, str(data.get("description", ""))[:120])}
    except Exception as e:
        return {"error": "%s" % type(e).__name__}


def pets_channel_preflight():
    """Verify PETS credentials and posting rights without sending a message.

    The returned diagnostic deliberately omits the bot token and chat id.  It
    is safe to place in a private Actions artifact, but not in public logs.
    """
    token, chat_id = credentials("pets")
    result = {"ok": False, "credentials_configured": bool(token and chat_id)}
    if not token or not chat_id:
        result["reason"] = "pets_credentials_missing"
        return result

    def call(method, params=None):
        try:
            response = requests.get(API % (token, method), params=params or {}, timeout=20)
            data = response.json() if response.content else {}
        except Exception as exc:
            return None, "transport_%s" % type(exc).__name__
        if not data.get("ok"):
            return None, "telegram_%s" % response.status_code
        return data.get("result") or {}, None

    bot, error = call("getMe")
    if error:
        result["reason"] = error
        return result
    chat, error = call("getChat", {"chat_id": chat_id})
    if error:
        result["reason"] = error
        return result
    membership, error = call("getChatMember", {"chat_id": chat_id, "user_id": bot.get("id")})
    if error:
        result["reason"] = error
        return result
    status = membership.get("status")
    result.update({"bot_username": bot.get("username"), "chat_type": chat.get("type"),
                   "membership": status})
    if chat.get("type") != "channel":
        result["reason"] = "pets_target_is_not_channel"
    elif status not in {"administrator", "creator"}:
        result["reason"] = "pets_bot_not_channel_administrator"
    else:
        result["ok"] = True
    return result
