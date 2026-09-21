# -*- coding: utf-8 -*-
"""Симуляция реального запуска jobs/agro через runner-контракт JobContext
(временная БД, publish выключен): что увидит production-раннер."""
import io
import os
import sys

os.environ["AGRO_DB_PATH"] = "_agro_research/job_sim.db"
os.environ.pop("AGRO_PUBLISH", None)
os.environ.pop("AGRO_BOT_TOKEN", None)
os.environ.pop("AGRO_CHAT_ID", None)
sys.path.insert(0, ".")

from core.context import JobContext  # noqa
from jobs.agro import job  # noqa

OUT = io.open("_agro_research/job_sim.txt", "w", encoding="utf-8")
ctx = JobContext("agro", "_agro_research/job_sim_storage.json", dry_run=True)
try:
    job.run(ctx)
    status = "OK"
except Exception as e:
    status = "FAIL %s: %s" % (type(e).__name__, e)
OUT.write("status: %s\ndb created: %s\n" % (status, os.path.exists("_agro_research/job_sim.db")))
for line in ctx.logs:
    OUT.write(line + "\n")
OUT.close()
print("job sim", status)
