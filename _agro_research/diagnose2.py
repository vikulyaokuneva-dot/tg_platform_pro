# -*- coding: utf-8 -*-
"""Диагноз: почему agroinvestor сегодня не проходит extraction; сигналы
классификатора на gismeteo 'pal Nino' (ошибочный practical?)."""
import io, sys
sys.path.insert(0, ".")
from case_pipeline import agro, classifier_agro, extraction, httpclient

OUT = io.open("_agro_research/diagnose.txt", "w", encoding="utf-8")
def w(*x): OUT.write(" ".join(str(i)[:300] for i in x) + "\n")

ad = agro.adapters.ADAPTERS["agroinvestor"]
urls = ad.discover()
w("agroinvestor discovered:", len(urls))
for u in urls[:4]:
    try:
        s, html = httpclient.fetch(u, timeout=45)
        ext = extraction.extract_from_html(html, u)
        text = ext.get("text") or ""
        w(u[:95])
        w("  http=%s len_html=%d len_text=%d quality=%s title=%r date=%r captcha=%s" % (
            s, len(html), len(text), ext.get("quality"), (ext.get("title") or "")[:50],
            ext.get("published_at"), ext.get("suspect_captcha")))
        w("  html head snippet:", html[:300].replace("\n", " "))
    except Exception as e:
        w("FETCH FAIL", u[:80], type(e).__name__, str(e)[:150])

u = "https://www.gismeteo.ru/news/nature/jel-nino-pochti-ostanovil-sezon-uraganov-v-atlantike-ustanovlen-rekord/"
try:
    s, html = httpclient.fetch(u, timeout=45)
    ext = extraction.extract_from_html(html, u)
    text = ext.get("text") or ""
    v = classifier_agro.classify(ext.get("title") or "", text)
    w("\ngismeteo El Nino:", v["type"], "signals=", v["signals"])
    import re
    w("  practical matches:", re.findall(classifier_agro.PRACTICAL_RX, ext.get("title","")+" "+text[:2000])[:8])
    w("  body excerpt:", text[:250].replace("\n", " "))
    w("  body len:", len(text), "quality:", ext.get("quality"))
except Exception as e:
    w("gismeteo fail", type(e).__name__, str(e)[:120])
OUT.close()
print("diagnose done")
