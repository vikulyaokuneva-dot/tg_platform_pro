# -*- coding: utf-8 -*-
"""Replace send_photo in telegram.py with multipart-capable version."""
import pathlib

p = pathlib.Path("case_pipeline/telegram.py")
t = p.read_text(encoding="utf-8")

old = '''def send_photo(token, chat_id, photo_url, caption=None, dry_run=False, retries=2):
    """Отправка фото по URL (sendPhoto). Используется агро-каналом для
    post-with-image. Token/chat_id обязательны; fallback нет. Caption max 1024
    символов (ограничение Telegram API); проверка на стороне вызывающего."""
    if dry_run:
        log.info("DRY-RUN: send_photo не выполняется (%s)", photo_url[:80])
        return PublishResult(True, message_id=0, error="dry-run")
    if not token or not chat_id:
        return PublishResult(False, error="no bot token/chat_id for send_photo")
    payload = {"chat_id": chat_id, "photo": photo_url}
    if caption:
        payload["caption"] = caption
    last = None
    for attempt in range(retries + 1):
        try:
            r = requests.post(API % (token, "sendPhoto"), json=payload, timeout=30)
            data = r.json() if r.content else {}
            if data.get("ok"):
                msg = data["result"]
                mid = msg.get("message_id") if isinstance(msg, dict) else None
                return PublishResult(True, message_id=mid, http_status=r.status_code)
            last = "%s %s" % (r.status_code, str(data.get("description", ""))[:200])
            if r.status_code == 429:
                time.sleep(data.get("parameters", {}).get("retry_after", 3) or 3)
                continue
        except Exception as e:
            last = type(e).__name__
            time.sleep(2)
    return PublishResult(False, error=str(last))'''

new = '''def send_photo(token, chat_id, photo_url=None, photo_bytes=None,
               caption=None, dry_run=False, retries=2):
    """Отправка фото в Telegram (sendPhoto). Поддерживает два режима:
      - photo_url: Telegram сам скачивает (может вернуть 400 failed to get HTTP URL content);
      - photo_bytes: multipart upload (надёжнее для CDN с защитой от ботов).
    Token/chat_id обязательны; fallback нет. Caption <= 1024 символов."""
    label = (photo_url or "(bytes)")[:80]
    if dry_run:
        log.info("DRY-RUN: send_photo не выполняется (%s)", label)
        return PublishResult(True, message_id=0, error="dry-run")
    if not token or not chat_id:
        return PublishResult(False, error="no bot token/chat_id for send_photo")
    if photo_bytes is not None:
        files = {"photo": ("photo.jpg", photo_bytes, "image/jpeg")}
        data_payload = {"chat_id": chat_id}
        if caption:
            data_payload["caption"] = caption
    elif photo_url:
        files = None
        data_payload = {"chat_id": chat_id, "photo": photo_url}
        if caption:
            data_payload["caption"] = caption
    else:
        return PublishResult(False, error="send_photo: no photo_url or photo_bytes")
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
    return PublishResult(False, error=str(last))'''

if old not in t:
    raise RuntimeError("old send_photo not found in telegram.py")
out = t.replace(old, new)
p.write_text(out, encoding="utf-8")
print("send_photo replaced with multipart-capable version")
