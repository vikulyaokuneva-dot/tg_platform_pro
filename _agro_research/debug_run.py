# -*- coding: utf-8 -*-
import sys, io
sys.path.insert(0, ".")
import case_pipeline.config as c
import case_pipeline.telegram as t
import case_pipeline.agro as a
import case_pipeline.adapters as ad
from case_pipeline import storage
import tests.test_agro_channel as m

OUT = io.open("_agro_research/debug_run.txt", "w", encoding="utf-8")
def w(*x): OUT.write(" ".join(str(i) for i in x) + "\n")

pages = {m.ART_URL: m._art_html()}
def fake(u, timeout=30, **k):
    return (200, pages[u])
a.httpclient.fetch = fake
ad.ADAPTERS["botanichka"].discover = lambda: [m.ART_URL]
c.AGRO_PUBLISH = True
c.AGRO_BOT_TOKEN = "t"
c.AGRO_CHAT_ID = "C"
c.AGRO_PUBLISH_LIMIT = 1
sent = []
def spy(token, chat_id, text, dry_run=False, parse_mode=None, retries=2):
    sent.append((token, chat_id))
    return t.PublishResult(True, message_id=7)
t.send_message = spy

st = storage.Storage("_agro_research/dbg1.db")
w("DIRECT", a.process_url(st, m.ART_URL, "botanichka", publish=True, dry_run=False))
st2 = storage.Storage("_agro_research/dbg2.db")
w("RUN", a.run(dry_run=False, publish=True, sources=["botanichka"], st=st2))
w("sent", sent)
OUT.close()
print("done")
