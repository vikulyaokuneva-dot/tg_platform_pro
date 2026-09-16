# -*- coding: utf-8 -*-
import sqlite3
db = sqlite3.connect("_agro_research/tmp_iso/agro_job.db")
print(db.execute("SELECT status, COUNT(*) FROM materials GROUP BY status").fetchall())
q = ("SELECT status, substr(url,1,78), substr(IFNULL(reason,''),1,70) "
     "FROM materials WHERE reason LIKE '%already%' OR status IN "
     "('post_ready','news_hold') ORDER BY id DESC LIMIT 14")
for row in db.execute(q):
    print(" | ".join(str(x) for x in row))
