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
    """Токен/чат по имени канала. 'ai' — существующий production-канал
    (пары env не тронуты), 'agro' — второй канал (jobs/agro). Секретов в коде
    нет: только env (см. config).-> (token, chat_id)"""
    if channel == "agro":
        return config.AGRO_BOT_TOKEN, config.AGRO_CHAT_ID
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


def fit_caption(md, limit=1024):
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
            inner = head[2:-2] if (head.startswith("**") and len(head) > 4
                                   and head.endswith("**")) else head
            new = _cut_words(inner, max(20, len(inner) - over))
            if new == inner:
                break
            head = ("**%s**" % new) if head.startswith("**") else new
    return "\n\n".join([head] + middle + tail)


def publish_post(text, chat_id=None, dry_run=False, channel="ai", image=None):
    """Финальная подача поста: целевой макет канала (жирный заголовок/поля,
    пустые строки между блоками) + валидный MarkdownV2 с полным экранированием
    (postformat). Механизм отправки и ретраи — прежние. Откат безопасный: если
    API отверг разметку (400 parse) или длина после экранирования близка к
    лимиту — тот же текст уходит plain text (без parse_mode).

    channel: 'ai' (default, поведение идентично прежнему) | 'agro'.
    image: bytes — публикация в ДВА шага: (1) sendPhoto с короткой
    законченной подписью ≤1024 (postformat.split_for_photo: заголовок +
    краткий анонс по границе предложения + «Источник:»), затем (2) ПОЛНЫЙ
    текст отдельным сообщением (заголовок, тело БЕЗ скопированного дословно
    анонса — вступление не дублируется, msg80/81; «Источник:» + хэштеги;
    лимит сообщения 4096 с безопасной страховкой). Длинный пост раньше
    целиком уходил в caption и обрезался fit_caption по словам — материал
    терял рекомендации (обрыв в msg78). Без image — прежний текстовый путь."""
    token, target_chat = credentials(channel)
    formatted = postformat.format_post(text)
    if dry_run:
        return send_message(token, chat_id or target_chat,
                            formatted, dry_run=True)
    if not token or not (chat_id or target_chat):
        # честный стоп: без секретов канала НЕ уходим в чужой токен/чат
        return PublishResult(False, error="no credentials for channel %s" % channel)
    md = postformat.to_markdownv2(formatted)
    if image:
        target = chat_id or target_chat
        # 1) фото с короткой подписью (заголовок + краткий анонс, без
        # хэштегов — они в полном тексте)
        cap_plain, msg_plain = postformat.split_for_photo(formatted)
        if msg_plain == cap_plain:
            log.warning("split_for_photo: тело не делится (дубль в сообщении)")
        caption = fit_caption(postformat.to_markdownv2(cap_plain), 1024)
        res = send_photo(token, target, photo_bytes=image,
                         caption=caption, parse_mode="MarkdownV2")
        if not res.ok:
            err = str(res.error or "").lower()
            if "400" in err and "parse" in err:
                log.warning("caption markdown rejected (400 parse) — повтор без parse_mode")
                res = send_photo(token, target, photo_bytes=image,
                                 caption=postformat.unescape_markdownv2(caption))
            if not res.ok:
                log.error("telegram photo publish failed: %s", res.error)
                return res
        # 2) полный текст отдельным сообщением (фото — над текстом в ленте)
        full_md = postformat.to_markdownv2(msg_plain)
        if len(full_md) > 4090:
            # страховка: контракт ИИ-редактуры держит пост ≤3400 символов,
            # так что путь не должен срабатывать (см. agro.MAX_POST_CHARS)
            log.warning("full text %d chars > 4090 после экранирования — clamping",
                        len(full_md))
            full_md = fit_caption(full_md, 4090)
        res2 = send_message(token, target, full_md, parse_mode="MarkdownV2")
        if not res2.ok:
            err = str(res2.error or "").lower()
            if "400" in err and "parse" in err:
                log.warning("markdownv2 rejected (400 parse) — повтор plain text")
                res2 = send_message(token, target, msg_plain)
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
    if len(md) <= 4090:
        res = send_message(token, chat_id or target_chat, md,
                           parse_mode="MarkdownV2")
        if res.ok:
            return res
        err = str(res.error or "").lower()
        if "400" not in err or "parse" not in err:
            log.error("telegram publish failed: %s", res.error)
            return res
        log.warning("markdownv2 rejected (400 parse) — повтор plain text")
    res = send_message(token, chat_id or target_chat, formatted)
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


def get_me(dry_run=False):
    """Проверка токена/доступности бота (для self-test). Возвращает либо
    {"username":...,"id":...}, либо {"error": "<без секретов>"}. Токен не раскрывается."""
    token = config.BOT_TOKEN
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
