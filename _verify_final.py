import subprocess, os, sqlite3
print("=== CHANGED ===")
subprocess.run(["git","diff","--stat"])
print("=== UNTRACKED ===")
res = subprocess.run(["git","ls-files","--others","--exclude-standard"], capture_output=True, text=True)
for ln in res.stdout.splitlines():
    if "__pycache__" not in ln and "node_modules" not in ln:
        print(ln)
print("=== AGRO ===")
print("agro.py exists:", os.path.exists("case_pipeline/agro.py"))
for p in ["data/agro_channel.db","data/ai_case_pipeline.db"]:
    if os.path.exists(p):
        db=sqlite3.connect(p)
        table=[t[0] for t in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() if t[0]=="materials"]
        if table:
            print(p, db.execute("SELECT status,COUNT(*) FROM materials GROUP BY status").fetchall())
