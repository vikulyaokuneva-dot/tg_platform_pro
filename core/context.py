# -*- coding: utf-8 -*-
"""JobContext — минимальный контекст задачи платформы (реализация контракта,
на который опирался runner.py, но модуль отсутствовал в рабочей копии).

- storage.json: per-job персистентный state (dedup-ключи, счётчики);
- log(): строки в stdout + буфер (пишется в runs/<job>/log при наличии);
- dry_run: глобальный флаг (env DRY_RUN=1 задаётся runner.py).
"""
import io
import json
import os
from datetime import datetime


class JobContext:
    def __init__(self, name, storage_path, dry_run=False):
        self.name = name
        self.storage_path = storage_path
        self.dry_run = dry_run
        self._logs = []
        self._storage = {}
        try:
            if os.path.exists(storage_path):
                with io.open(storage_path, "r", encoding="utf-8") as f:
                    self._storage = json.load(f)
        except Exception:
            self._storage = {}

    # ---------- state ----------
    @property
    def storage(self):
        return self._storage

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.storage_path) or ".", exist_ok=True)
            with io.open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(self._storage, f, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            self.log("storage save error: %s" % e)

    # ---------- logging ----------
    def log(self, msg):
        line = "%s [%s] %s" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.name, msg)
        self._logs.append(line)
        print(line, flush=True)

    @property
    def logs(self):
        return list(self._logs)
