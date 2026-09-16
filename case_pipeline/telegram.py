# -*- coding: utf-8 -*-
"""case_pipeline.telegram — publisher валидированного поста.

Принимает ГОТОВЫЙ текст: никакой классификации/решений здесь.
В dry-run ничего не отправляет. Токен НЕ логируется и в отчёты не попадает.
"""
import logging
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


def publish_post(text, chat_id=None, dry_run=False, channel="ai"):
    """Финальная подача поста: целевой макет канала (жирный заголовок/поля,
    пустые строки между блоками) + валидный MarkdownV2 с полным экранированием
    (postformat). Механизм отправки и ретраи — прежние. Откат безопасный: если
    API отверг разметку (400 parse) или длина после экранирования близка к
    лимиту — тот же текст уходит plain text (без parse_mode).

    channel: 'ai' (default, поведение идентично прежнему) | 'agro'."""
    token, target_chat = credentials(channel)
    formatted = postformat.format_post(text)
    if dry_run:
        return send_message(token, chat_id or target_chat,
                            formatted, dry_run=True)
    if not token or not (chat_id or target_chat):
        # честный стоп: без секретов канала НЕ уходим в чужой токен/чат
        return PublishResult(False, error="no credentials for channel %s" % channel)
    md = postformat.to_markdownv2(formatted)
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
