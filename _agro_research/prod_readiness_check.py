# -*- coding: utf-8 -*-
"""Prod-readiness проверка Agro-канала (без публикации).

Части:
  A) §4 конфигурация/credentials: без AGRO-секретов агро-публикация честный
     стоп; fallback на prod-пары невозможен (с реальным prod-токеном в памяти).
  B) §5 изоляция БД: реальный prod-файл БД не меняется; агро-публикация (через
     фейковый telegram-транспорт) пишет только в агро-BD; кросс-неблокировка.
  C) §6 dry-run живых источников: статистика по этапам + полные примеры постов.

Никаких реальных HTTP в Telegram: запросы к api.telegram.org перехватываются.
"""
import hashlib
import io
import os
import sys

sys.path.insert(0, ".")
import requests  # noqa

OUT = io.open("_agro_research/prod_readiness.txt", "w", encoding="utf-8")
def w(*x):
    OUT.write(" ".join(str(i)[:400] for i in x) + "\n")
    OUT.flush()

# ---------- telegram-транспорт gate: реальных отправок не будет никогда ----------
TG_ATTEMPTS = []
_orig_post = requests.post
def transport(url, *a, **k):
    if "api.telegram.org" in str(url):
        TG_ATTEMPTS.append(str(url).split("/")[3][:12] + "… (token скрыт)")
        class R:
            status_code = 200
            content = b"{}"
            @staticmethod
            def json():
                return {"ok": True, "result": {"message_id": 99999}}
        return R()
    return _orig_post(url, *a, **k)
requests.post = transport

from case_pipeline import agro, config, storage as storage_mod, telegram  # noqa

w("A) КОНФИГУРАЦИЯ (реальное env-состояние этого дерева)")
w("  AGRO_BOT_TOKEN задан:", bool(config.AGRO_BOT_TOKEN),
  "| AGRO_CHAT_ID:", repr(config.AGRO_CHAT_ID),
  "| AGRO_PUBLISH:", config.AGRO_PUBLISH)
w("  prod BOT_TOKEN задан (.env):", bool(config.BOT_TOKEN),
  "| prod CHAT_ID:", config.CHAT_ID)
w("  AGRO_DB_PATH:", config.AGRO_DB_PATH)
w("  совпадает с prod DB?", config.AGRO_DB_PATH == config.DB_PATH,
  "| лежит внутри data/?", os.path.dirname(config.AGRO_DB_PATH) == os.path.dirname(config.DB_PATH))
w("  credentials('ai') == prod-пары:", telegram.credentials("ai") == (config.BOT_TOKEN, config.CHAT_ID))
w("  credentials('agro'):", tuple(bool(x) for x in telegram.credentials("agro")), "(False,False = секретов нет)")

# A2: попытка РЕАЛЬНОЙ публикации в агро при наличии prod-секретов в env
res = telegram.publish_post("тестовый агро-пост", dry_run=False, channel="agro")
w("  publish_post(channel=agro, dry_run=False) без секретов -> ok=%s error=%r" % (res.ok, res.error))
w("  реальных HTTP в Telegram зафиксировано:", len(TG_ATTEMPTS))
r2 = telegram.publish_post("тест", dry_run=True, channel="agro")
w("  dry_run агро без секретов -> ok=%s (безопасно)" % r2.ok)

# ---------- B) ИЗОЛЯЦИЯ БД ----------
w("\nB) ИЗОЛЯЦИЯ БД (реальные файлы, tmp-копии)")

def fhash(p):
    if not os.path.exists(p):
        return None
    return hashlib.sha256(open(p, "rb").read()).hexdigest()[:16]

prod_db = config.DB_PATH
h_before, m_before = fhash(prod_db), os.path.getmtime(prod_db) if os.path.exists(prod_db) else None
w("  prod БД существует:", os.path.exists(prod_db), "| hash до:", h_before)

os.makedirs("_agro_research/tmp_iso", exist_ok=True)
for _f in os.listdir("_agro_research/tmp_iso"):
    os.remove(os.path.join("_agro_research/tmp_iso", _f))
agro_db = "_agro_research/tmp_iso/agro_iso.db"
if os.path.exists(agro_db):
    os.remove(agro_db)
st_agro = storage_mod.Storage(agro_db)

ART_URL = "https://www.botanichka.ru/article/kogda-sazhat-chesnok-osenyu/"
PAR1 = ("Озимый чеснок сажают за 35-45 дней до устойчивых заморозков: зубчик должен "
        "укорениться, но не тронуться в рост. На юге это конец октября, в средней "
        "полосе первая половина октября, на Урале сентябрь. Ориентируйтесь на "
        "прогноз: почва остывает до +10 градусов на глубине 5 см, и тогда посадку "
        "пора заканчивать, иначе луковица не успеет сформировать корни до холодов.")
PAR2 = ("Ошибка слишком ранняя посадка: перо, вышедшее до холодов, вымерзает. "
        "Схемы: лента с шагом 25 см между зубцами и 30 см между бороздами либо "
        "двухстрочная лента 20х40 см. Глубина заделки 6-8 см по лёгкому грунту и "
        "10-12 см по тяжёлому, после посадки замульчируйте грядку слоем 5 см, а "
        "весной частично сгребите мульчу: так сохраняется до 90 процентов всходов.")
HTML = ("<html><head><title>%s</title><script type=\"application/ld+json\">"
        "{\"@type\":\"Article\",\"headline\":\"%s\",\"datePublished\":\"%s\"}"
        "</script></head><body><article><p>%s</p><p>%s</p></article></body></html>")
import datetime
NOW = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%S+00:00")
pages = {ART_URL: HTML % ("Когда сажать чеснок осенью", "Когда сажать чеснок осенью", NOW, PAR1, PAR2)}
_real_fetch = agro.httpclient.fetch
agro.httpclient.fetch = lambda u, timeout=30, **k: (200, pages[u]) if u in pages else _real_fetch(u, timeout=timeout)

# имитируем ВКЛЮЧЁННЫЙ канал: фейковые агро-креды (реального send не будет — gate)
config.AGRO_BOT_TOKEN = "AGROFAKE:token"
config.AGRO_CHAT_ID = "-100AGROFAKE"
config.AGRO_PUBLISH = True
r = agro.process_url(st_agro, ART_URL, "botanichka", publish=True, dry_run=False)
w("  агро-публикация (фейк-креды, gate-транспорт):", r.get("status"), r.get("reason"))
rows = st_agro.db.execute("SELECT chat_id, content_type FROM publications").fetchall()
w("  публикации в АГРО-БД:", [tuple(x) for x in rows])
w("  перехваченные telegram-запросы (token/call):", TG_ATTEMPTS)
w("  отправлено с AGROFAKE-токеном:", TG_ATTEMPTS and "AGROFAKE:to…" in TG_ATTEMPTS[0])

h_after, m_after = fhash(prod_db), os.path.getmtime(prod_db)
w("  prod-БД: hash после:", h_after, "неизменен:", h_before == h_after,
  "| mtime не изменился:", m_before == m_after)

# кросс-неблокировка на копиях (в реальный prod-файл НЕ пишем)
prod_copy = "_agro_research/tmp_iso/prod_copy.db"
if os.path.exists(prod_copy):
    os.remove(prod_copy)
if os.path.exists(prod_db):
    import shutil
    shutil.copy(prod_db, prod_copy)
    st_prod = storage_mod.Storage(prod_copy)
    n0 = st_prod.db.execute("SELECT COUNT(*) c FROM materials").fetchone()["c"]
    # 5/6: тот же canonical уже «опубликован» в prod — агро не блокируется (своя БД)
    before = st_agro.db.execute("SELECT COUNT(*) c FROM publications").fetchone()["c"]
    st_prod.add(ART_URL, "mindbox")
    mid = st_prod.add(ART_URL, "mindbox")
    st_prod.update(mid, status="published")
    st_prod.mark_published(mid, 1, config.CHAT_ID, "some-case-id")
    # агро-БД уже содержит этот URL post_ready/published из шага выше:
    # повтор не должен заново публиковать (дедуп ВНУТРИ канала) и не должен
    # зависеть от prod-истории (дедуп МЕЖДУ каналами изолирован):
    r2 = agro.process_url(st_agro, ART_URL, "botanichka", publish=False, dry_run=True)
    after = st_agro.db.execute("SELECT COUNT(*) c FROM publications").fetchone()["c"]
    w("  агро-обработка того же URL: %s reason=%r; публикации агро не задвоены: %s"
      % (r2.get("status"), r2.get("reason"), before == after == 1))
    # 6/6: обратная неблокировка — prod-storage не знает case_id агро,
    # agro-storage не видит строк prod (домен disjoint + изоляция файлов)
    from case_pipeline import case_model
    agro_case_id = case_model.case_id_for(ART_URL, PAR1 + PAR2)
    w("  prod-копия case_published(agro_id):", st_prod.case_published(agro_case_id),
      "(False = prod не заблокирован агро-историей)")
    n1 = st_prod.db.execute("SELECT COUNT(*) c FROM materials").fetchone()["c"]
    ag_rows = st_agro.db.execute("SELECT COUNT(*) c FROM materials").fetchone()["c"]
    w("  prod-копия materials: до=%d сейчас=%d (прирост=1 — наша же setup-строка,"
      " агро lane в prod-копию не писал)" % (n0, n1))
    w("  агро-БД materials:", ag_rows, "(1 строка: только наш тестовый URL)")
agro.httpclient.fetch = _real_fetch

# ---------- C) DRY-RUN ЖИВЫХ ИСТОЧНИКОВ ----------
w("\nC) DRY-RUN ЖИВЫХ ИСТОЧНИКОВ (без публикации; своя tmp-БД)")
config.AGRO_PUBLISH = False
N_PROBE = 5
live_db = "_agro_research/tmp_iso/agro_live.db"
if os.path.exists(live_db):
    os.remove(live_db)
st_live = storage_mod.Storage(live_db)
examples = {}
POSTS = io.open("_agro_research/example_posts.txt", "w", encoding="utf-8")
for name in ("botanichka", "agroinvestor", "gismeteo"):
    ad = agro.adapters.ADAPTERS[name]
    try:
        urls = ad.discover()
    except Exception as e:
        w("  %s: DISCOVERY FAIL %s %s" % (name, type(e).__name__, str(e)[:100])); continue
    stat = {"discovered": len(urls), "fetch_ok": 0, "extract_ok": 0, "practical": 0,
            "news": 0, "ad_offtopic": 0, "thin_stale": 0, "post_ready": 0, "errors": []}
    from case_pipeline import extraction, httpclient
    useful = 0
    scanned = 0
    for u in urls[:N_PROBE * 4]:
        if useful >= N_PROBE or scanned >= 12:
            break
        scanned += 1
        try:
            status, html = httpclient.fetch(u, timeout=45)
            stat["fetch_ok"] += 1
            ext = extraction.extract_from_html(html, u)
            text = ext.get("text") or ""
            if ext.get("quality") == "failed" or len(text) < agro.MIN_BODY_CHARS:
                stat["thin_stale"] += 1
                stat["errors"].append("thin(%d,q=%s) @ %s" % (len(text), ext.get("quality"), u[:55]))
                continue
            stat["extract_ok"] += 1
            if not agro._age_ok(ext.get("published_at")):
                stat["thin_stale"] += 1
                stat["errors"].append("stale(%s) @ %s" % (ext.get("published_at"), u[:55]))
                continue
            v = agro.classifier_agro.classify(ext["title"], text, ext.get("published_at") or "")
            useful += 1  # материал «состоялся» (любой валидный вердикт)
            if v["type"] == "practical":
                stat["practical"] += 1
                post, tags = agro.build_post(ext["title"], text, u, name, v)
                errs = agro.editorial_agro(post, text)
                if not errs:
                    stat["post_ready"] += 1
                    if len(examples.get(name, [])) < 3:
                        examples.setdefault(name, []).append((u, ext.get("published_at"), v, post, tags, len(text)))
                else:
                    stat["errors"].append("editorial: %s @ %s" % (errs, u[:60]))
            elif v["type"] == "news":
                stat["news"] += 1
            else:
                stat["ad_offtopic"] += 1
        except Exception as e:
            stat["errors"].append("%s @ %s: %s" % (type(e).__name__, u[:60], str(e)[:80]))
    w("  %-13s %s" % (name, stat))
    for u, d, v, post, tags, tl in examples.get(name, [])[:3]:
        w("    ПРИМЕР %s | date=%s | verdict=%s conf=%s | src_len=%d" % (u[:90], d, v["type"], v["confidence"], tl))
        POSTS.write("=" * 70 + "\n%s (%s) conf=%s src_len=%d\n%s\n\n[пост %d симв., теги %s]\n%s\n" % (
            name, u[:100], v["confidence"], tl, "—" * 40, len(post), tags, post))
POSTS.close()

# полный прогон run() как это сделает job (dry_run, без секретов)
sm = agro.run(dry_run=True, publish=False, st=storage_mod.Storage("_agro_research/tmp_iso/agro_job.db"))
w("  agro.run(dry) summary:", sm)

# ---------- D) СВОЁ ФЕРМЕРСТВО: статус ----------
w("\nD) svoe_fermerstvo:")
w("  адаптер зарегистрирован:", "svoe_fermerstvo" in agro.adapters.ADAPTERS,
  "| в AGRO_SOURCES:", "svoe_fermerstvo" in config.AGRO_SOURCES,
  "| основания: source_probe2/3.txt (Nuxt SPA, article-like=[], feed/sitemap 404)")

w("\nИТОГ: реальных запросов к api.telegram.org:", len(TG_ATTEMPTS),
  "(перехвачены gate, не отправлены)" if TG_ATTEMPTS else "(ноль)")
OUT.close()
print("readiness done; tg attempts:", len(TG_ATTEMPTS))
