# -*- coding: utf-8 -*-
"""Fail-closed health check for a restored PETS SQLite state file."""
import os
import sqlite3


def inspect(path):
    if not os.path.exists(path):
        return {"status": "missing", "durable": False}
    try:
        db = sqlite3.connect("file:%s?mode=ro" % os.path.abspath(path).replace("\\", "/"), uri=True)
        try:
            integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            db.close()
    except sqlite3.Error as exc:
        return {"status": "corrupt", "durable": False, "reason": type(exc).__name__}
    if integrity != "ok" or not {"materials", "publications", "pets_topic_history"}.issubset(tables):
        return {"status": "invalid", "durable": False, "reason": "integrity_or_schema"}
    return {"status": "ready", "durable": False}
