# -*- coding: utf-8 -*-
"""Insert send_photo() into telegram.py before get_me()."""
import pathlib

p = pathlib.Path("case_pipeline/telegram.py")
t = p.read_text(encoding="utf-8")
marker = "def get_me(dry_run=False):"
idx = t.index(marker)

new_func = '''def send_photo(token, chat_id, photo_url, caption=None, dry_run=False, retries=2):
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
    return PublishResult(False, error=str(last))


'''

out = t[:idx] + new_func + t[idx:]
p.write_text(out, encoding="utf-8")
print("inserted send_photo at char", idx)
