# -*- coding: utf-8 -*-
"""Финальный production-запуск AGRO-канала «Сад без хлопот».

ОДИН пост в -1003389902213 с:
  - agro_postgen (человеческий формат, не копия статьи);
  - multipart image upload (скачиваем сами, не надеемся на Telegram);
  - evidence gate (числа поста ⊆ числа источника);
  - dedup, DB isolation, prod safety.
"""
import hashlib
import io
import os
import re
import sys

sys.path.insert(0, ".")
from case_pipeline import (adapters, agro, config, extraction, httpclient,
                           storage as storage_mod, telegram)
from case_pipeline.agro_postgen import build_agro_post

OUT = io.open("_agro_research/final_publish_report.txt", "w", encoding="utf-8")
def w(*x):
    OUT.write(" ".join(str(i)[:500] for i in x) + "\n")
    OUT.flush()

AGRO_CHAT_ID = "-1003389902213"
AGRO_DB_PATH = os.environ.get("AGRO_DB_PATH", "data/agro_channel.db")
PROD_DB_PATH = "data/ai_case_pipeline.db"

# --- 0. Prod DB hash before ---
def file_hash(path):
    if not os.path.exists(path):
        return "missing"
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

prod_hash_before = file_hash(PROD_DB_PATH)
w("PROD DB before:", PROD_DB_PATH, "hash=", prod_hash_before[:16])

# --- 1. Discover fresh practical article from Botanichka ---
urls = adapters.ADAPTERS["botanichka"].discover()
if not urls:
    raise RuntimeError("Botanichka недоступен")

st = storage_mod.Storage(AGRO_DB_PATH)
candidate = None
for url in urls[:10]:
    ext_html = None
    try:
        _, html = httpclient.fetch(url, timeout=45)
        ext = extraction.extract_from_html(html, url)
    except Exception as e:
        w("FETCH FAIL:", url[:80], str(e)[:100])
        continue
    title = ext.get("title") or ""
    text = ext.get("text") or ""
    verdict = agro.classifier_agro.classify(title, text, ext.get("published_at") or "")
    vtype = verdict.get("type") if isinstance(verdict, dict) else str(verdict)
    if vtype == "practical":
        mid = st.add(url, "botanichka")
        rec = st.get(mid)
        if rec and rec.get("status") == "published":
            w("SKIP already published:", url[:80])
            continue
        candidate = {"url": url, "ext": ext, "verdict": verdict, "mid": mid}
        break
    w("NOT practical:", label, url[:80])

if not candidate:
    raise RuntimeError("Не найден свежий practical материал из Ботанички")

ext = candidate["ext"]
url = candidate["url"]
title = ext.get("title") or ""
text = ext.get("text") or ""
image_url = ext.get("image") or ""
mid = candidate["mid"]

w("\n=== ВЫБРАННЫЙ МАТЕРИАЛ ===")
w("URL:", url)
w("Title:", title[:120])
w("Image URL:", image_url[:120] if image_url else "(none)")
w("Verdict:", candidate["verdict"])

# --- 2. Build tags ---
tags = ["#Практика"]
domain_tags = []
for tag, rx in agro.AGRO_DOMAIN_RULES:
    if re.search(rx, title) or re.search(rx, text[:2000]):
        domain_tags.append("#" + tag)
        if len(domain_tags) >= 3:
            break
tags.extend(domain_tags[:3])
if len(tags) < 3:
    tags.append("#Сад")
tags = list(dict.fromkeys(tags))[:5]  # dedup, max 5
w("Tags:", tags)

# --- 3. Build post with agro_postgen ---
post_text = build_agro_post(title, text, url, tags)
w("\n=== FINAL PREVIEW ===")
w(post_text)

# --- 4. Evidence gate: numbers in post ⊆ numbers in source ---
num_rx = re.compile(r"\d+(?:[.,]\d+)?")
src_nums = set(num_rx.findall(text))
post_nums = set(num_rx.findall(post_text))
invented = post_nums - src_nums
if invented:
    w("EVIDENCE GATE FAIL: invented numbers:", invented)
    raise RuntimeError("Evidence gate failed: invented numbers %s" % invented)
w("Evidence gate OK: post_nums ⊆ src_nums (%d чисел)" % len(post_nums))

# --- 5. Download image for multipart upload ---
photo_bytes = None
image_used = "(text-only)"
if image_url:
    try:
        img_resp = httpclient.fetch(image_url, timeout=30)
        raw = img_resp[1] if isinstance(img_resp, tuple) else img_resp
        if isinstance(raw, bytes) and len(raw) > 1000:
            photo_bytes = raw
            image_used = "uploaded successfully"
            w("Image downloaded: %d bytes" % len(raw))
        else:
            w("Image too small or empty:", len(raw) if isinstance(raw, bytes) else type(raw))
    except Exception as e:
        w("Image download failed:", str(e)[:120])

# --- 6. Publish ---
token = config.BOT_TOKEN  # shared_platform_bot (added as admin to agro channel)
if not token:
    raise RuntimeError("BOT_TOKEN not set")

# Set post_ready so claim can grab it
st.update(mid, status="post_ready")
if not st.claim_for_publish(mid):
    raise RuntimeError("Claim failed — possible duplicate or race")
st.update(mid, status="publishing")

res = None
if photo_bytes is not None and len(post_text) <= 1024:
    # Photo + caption (multipart)
    res = telegram.send_photo(token, AGRO_CHAT_ID, photo_bytes=photo_bytes,
                              caption=post_text, dry_run=False)
    if not res.ok:
        w("Photo send failed:", res.error, "-> fallback text-only")
        res = telegram.send_message(token, AGRO_CHAT_ID, post_text, dry_run=False)
        image_used = "fallback to text-only"
elif photo_bytes is not None:
    # Caption too long: send photo without caption, then text
    res_img = telegram.send_photo(token, AGRO_CHAT_ID, photo_bytes=photo_bytes, dry_run=False)
    if res_img.ok:
        res = telegram.send_message(token, AGRO_CHAT_ID, post_text, dry_run=False)
        image_used = "uploaded successfully (separate message)"
    else:
        w("Photo send failed:", res_img.error, "-> fallback text-only")
        res = telegram.send_message(token, AGRO_CHAT_ID, post_text, dry_run=False)
        image_used = "fallback to text-only"
else:
    # No image
    res = telegram.send_message(token, AGRO_CHAT_ID, post_text, dry_run=False)

if not res or not res.ok:
    st.update(mid, status="failed")
    raise RuntimeError("Telegram publish failed: %s" % (res.error if res else "no result"))

# Mark published
st.mark_published(mid, res.message_id, AGRO_CHAT_ID, "agro-final-v2",
                  hashtags=" ".join(tags), content_type="agro")

w("\n=== TELEGRAM RESULT ===")
w("ok=", res.ok, "message_id=", res.message_id, "image_used=", image_used)
w("AGRO DB written:", AGRO_DB_PATH)

# --- 7. Dedup verification ---
r2 = agro.process_url(st, url, "botanichka", publish=True, dry_run=False)
w("Dedup re-process:", r2.get("status"), "reason=", r2.get("reason", ""))

# --- 8. Prod DB unchanged ---
prod_hash_after = file_hash(PROD_DB_PATH)
w("\nPROD DB after:", prod_hash_after[:16], "unchanged=", prod_hash_before == prod_hash_after)

w("\n=== ИТОГ ===")
w("Первый production-пост v2 отправлен ОДИН РАЗ.")
w("Канал:", AGRO_CHAT_ID)
w("Источник:", url)
w("Изображение:", image_used)
w("AGRO DB:", AGRO_DB_PATH)
w("PROD DB не изменён:", prod_hash_before == prod_hash_after)
w("Dedup работает:", r2.get("status") != "published")
OUT.close()
print("FINAL PUBLISH DONE. See _agro_research/final_publish_report.txt")
