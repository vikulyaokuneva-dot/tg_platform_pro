import sqlite3,os
for f in ['data/ai_case_pipeline.db','case_pipeline/data/ai_case_pipeline.db','data/agro_channel.db']:
    p=f if os.path.exists(f) else None
    if p:
        db=sqlite3.connect(p)
        c=db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        print(p, '->', [t[0] for t in c])
        # try materials/status counts if table exists
        for t in ['materials','publications','news','posts']:
            try:
                rows=db.execute(f"SELECT status,COUNT(*) FROM {t} GROUP BY status").fetchall()
                print('  ',t,rows)
            except Exception as e:
                pass
    else:
        print(f, 'MISSING')
