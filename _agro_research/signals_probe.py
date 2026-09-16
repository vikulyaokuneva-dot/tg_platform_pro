# -*- coding: utf-8 -*-
"""Сигналы классификатора на 4 РЕАЛЬНЫХ статьях (чтобы починить branch C без
гадания): заголовочные/тельные хиты, императивы, цифры, топик-хиты в title."""
import io, re, sys
sys.path.insert(0, ".")
from case_pipeline import classifier_agro as ca, extraction, httpclient

OUT = io.open("_agro_research/signals.txt", "w", encoding="utf-8")
def w(*x): OUT.write(" ".join(str(i)[:260] for i in x) + "\n")

URLS = [
    "https://www.botanichka.ru/article/7-komnatnyh-rastenij-kotorye-v-prirode-vyglyadyat-sovsem-inache/",
    "https://www.botanichka.ru/article/pochemu-zhivotnye-v-hozyajstve-hudeyut-hotya-edyat-normalno/",
    "https://www.botanichka.ru/article/chem-luchshe-belit-derevya-osenyu-izvest-mel-ili-sadovaya-kraska/",
    "https://www.gismeteo.ru/news/nature/jerozija-bolot-ezhegodno-perenosit-v-okean-okolo-380-tys-tonn-ugleroda/",
]
for u in URLS:
    _, html = httpclient.fetch(u, timeout=45)
    ext = extraction.extract_from_html(html, u)
    t, b = ext["title"], (ext.get("text") or "")
    head_pract = len(ca.PRACTICAL_RX.findall(t))
    body_pract = len(ca.PRACTICAL_RX.findall(b[:4000]))
    imper = len(ca.IMPERATIVE_RX.findall(b[:4000]))
    numbers = len(ca.NUM_RX.findall(t + " " + b[:3000]))
    ttopics = []
    for key, emoji, tag, rx in ca.TOPIC_RULES:
        if rx.search(t):
            ttopics.append(key)
    newsish = ca.NEWSISH_RX.findall(b[:3000])[:4]
    w(u.rsplit("/", 2)[-2][:60])
    w("  title=%r" % t[:80])
    w("  head_pract=%d body_pract=%d imper=%d numbers=%d topics(title)=%s" % (
        head_pract, body_pract, imper, numbers, ttopics))
    w("  newsish=%s verdict=%s" % (newsish, ca.classify(t, b)["type"]))
OUT.close()
print("signals done")
