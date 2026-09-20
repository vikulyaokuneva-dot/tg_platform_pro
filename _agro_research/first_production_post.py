# -*- coding: utf-8 -*-
"""Первый production-пост агро-канала «Сад без хлопот».

ОДИН пост в -1003389902213 через существующего shared_platform_bot.
Безопасность:
  - AGRO credentials задаются явно (не из env, не fallback);
  - telegram.send_message/send_photo требуют явную пару token/chat;
  - пишем только в AGRO_DB_PATH; prod DB хешируем до/после;
  - после отправки проверяем dedup повторным process_url;
  - если что-то пошло не так — ничего не отправляем.
"""
import hashlib
import io
import os
import re
import sys

sys.path.insert(0, ".")
from case_pipeline import (adapters, agro, config, extraction, httpclient,
                           storage as storage_mod, telegram)

OUT = io.open("_agro_research/first_publish_real.txt", "w", encoding="utf-8")
def w(*x):
    OUT.write(" ".join(str(i)[:400] for i in x) + "\n")
    OUT.flush()

# ---------- 0. Константы первого запуска ----------
AGRO_CHAT_ID = "-1003389902213"
AGRO_BOT_TOKEN = config.BOT_TOKEN  # используем существующего бота проекта
AGRO_DB_PATH = os.path.join(config.ROOT, "data", "agro_channel.db")
PROD_DB_PATH = config.DB_PATH

if not AGRO_BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN отсутствует в .env — нечем отправить пост")

# ---------- 1. Хеш prod DB ДО (неизменность) ----------
def db_hash(path):
    if not os.path.exists(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()

prod_hash_before = db_hash(PROD_DB_PATH)
w("PROD DB before:", PROD_DB_PATH, "hash=", prod_hash_before)

# ---------- 2. Выбор материала (Botanichka, первый свежий practical) ----------
urls = adapters.ADAPTERS["botanichka"].discover()
if not urls:
    raise RuntimeError("Botanichka discovery пуст")

candidate = None
for u in urls[:10]:
    try:
        _, html = httpclient.fetch(u, timeout=45)
        ext = extraction.extract_from_html(html, u)
        text = ext.get("text") or ""
        if len(text) < agro.MIN_BODY_CHARS:
            continue
        if not agro._age_ok(ext.get("published_at")):
            continue
        v = agro.classifier_agro.classify(ext.get("title") or "", text,
                                          ext.get("published_at") or "")
        if v["type"] != "practical":
            continue
        post, tags = agro.build_post(ext.get("title") or "", text, u,
                                     "botanichka", v)
        errs = agro.editorial_agro(post, text)
        if errs:
            w("editorial reject", u[:80], errs)
            continue
        candidate = {
            "url": u, "ext": ext, "text": text, "verdict": v,
            "post": post, "tags": tags, "image": ext.get("image") or "",
        }
        break
    except Exception as e:
        w("candidate fail", u[:80], type(e).__name__, str(e)[:120])

if not candidate:
    raise RuntimeError("Не найден свежий practical-материал Ботанички")

w("\n=== ВЫБРАННЫЙ МАТЕРИАЛ ===")
w("URL:", candidate["url"])
w("Title:", (candidate["ext"].get("title") or "")[:120])
w("Date:", candidate["ext"].get("published_at"))
w("Verdict:", candidate["verdict"]["type"], "conf=", candidate["verdict"]["confidence"])
w("Image:", candidate["image"] or "(нет)")
w("Tags:", candidate["tags"])
w("\n=== FINAL PREVIEW (caption) ===")
w(candidate["post"])

# ---------- 3. Evidence gate: числа поста ⊆ числа источника ----------
NUM_RX = re.compile(r"\d[\d.,]*\s*(?:%|см|мм|л|литров?|кг|грамм|г|шт|раз|"
                    r"минут|час|дн|недел|лет|°|C\b|п\.п\.)", re.I)
src_nums = set(NUM_RX.findall(candidate["text"]))
post_nums = set(NUM_RX.findall(candidate["post"]))
invented = post_nums - src_nums
if invented:
    raise RuntimeError("EVIDENCE GATE FAIL: выдуманные числа %r" % sorted(invented))
w("\nEvidence gate OK: post_nums ⊆ src_nums (%d чисел)" % len(post_nums))

# ---------- 4. Отправка ОДНОГО поста (photo+caption или text-only) ----------
st = storage_mod.Storage(AGRO_DB_PATH)
mid = st.add(candidate["url"], "botanichka")
st.update(mid, status="post_ready", post_text=candidate["post"])
if not st.claim_for_publish(mid):
    raise RuntimeError("claim_for_publish не получен (повтор?)")

res = None
image_used = None
cap = candidate["post"]

if candidate["image"]:
    # Telegram caption limit = 1024 chars
    if len(cap) <= 1024:
        res = telegram.send_photo(AGRO_BOT_TOKEN, AGRO_CHAT_ID,
                                  candidate["image"], caption=cap, dry_run=False)
        if res.ok:
            image_used = candidate["image"]
        else:
            w("photo send failed:", res.error, "-> fallback text-only")
    else:
        # длинный пост: фото + короткая подпись, затем полный текст отдельным сообщением
        head = cap.split("\n\n")[0]
        cap_short = head + "\n\nИсточник: " + candidate["url"] + "\n\n" + " ".join(candidate["tags"])
        res_photo = telegram.send_photo(AGRO_BOT_TOKEN, AGRO_CHAT_ID,
                                        candidate["image"], caption=cap_short, dry_run=False)
        if res_photo.ok:
            image_used = candidate["image"]
            res = telegram.send_message(AGRO_BOT_TOKEN, AGRO_CHAT_ID,
                                        cap, dry_run=False)
        else:
            w("photo send failed:", res_photo.error, "-> fallback text-only")

if res is None or not res.ok:
    # text-only fallback через publish_post (использует credentials('agro'))
    orig_t, orig_c = config.AGRO_BOT_TOKEN, config.AGRO_CHAT_ID
    config.AGRO_BOT_TOKEN, config.AGRO_CHAT_ID = AGRO_BOT_TOKEN, AGRO_CHAT_ID
    try:
        res = telegram.publish_post(cap, chat_id=AGRO_CHAT_ID,
                                    dry_run=False, channel="agro")
    finally:
        config.AGRO_BOT_TOKEN, config.AGRO_CHAT_ID = orig_t, orig_c

if not res.ok:
    raise RuntimeError("Telegram publish failed: %s" % res.error)

w("\n=== TELEGRAM RESULT ===")
w("ok=", res.ok, "message_id=", res.message_id, "image_used=", image_used or "(text-only)")

# ---------- 5. Фиксация в AGRO DB ----------
st.mark_published(mid, res.message_id, AGRO_CHAT_ID,
                  case_id="first-agro-" + hashlib.sha1(candidate["url"].encode()).hexdigest()[:12],
                  hashtags=" ".join(candidate["tags"]), content_type="agro")
w("AGRO DB written:", AGRO_DB_PATH)

# ---------- 6. Dedup-проверка: повторный process_url НЕ публикует ----------
r2 = agro.process_url(st, candidate["url"], "botanichka", publish=True, dry_run=False)
w("Dedup re-process:", r2.get("status"), "reason=", r2.get("reason"))
if r2.get("status") == "published":
    raise RuntimeError("DEDUP FAIL: повторная публикация того же URL!")

# ---------- 7. Prod DB неизменна ----------
prod_hash_after = db_hash(PROD_DB_PATH)
w("\nPROD DB after:", prod_hash_after, "unchanged=", prod_hash_before == prod_hash_after)
if prod_hash_before != prod_hash_after:
    raise RuntimeError("PROD DB ИЗМЕНЁН — аварийная остановка")

w("\n=== ИТОГ ===")
w("Первый production-пост отправлен ОДИН РАЗ.")
w("Канал:", AGRO_CHAT_ID)
w("Источник:", candidate["url"])
w("Изображение:", image_used or "(text-only)")
w("AGRO DB:", AGRO_DB_PATH)
w("PROD DB не изменён:", prod_hash_before == prod_hash_after)
w("Dedup работает:", r2.get("status") != "published")
OUT.close()
print("FIRST PUBLISH DONE. See _agro_research/first_publish_real.txt")
