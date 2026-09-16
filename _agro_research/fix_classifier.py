# -*- coding: utf-8 -*-
"""Восстановить точные байты frozen-классификатора из git-объекта (без CRLF-smudge)."""
import hashlib
import subprocess

p = "case_pipeline/classifier_lib/classifier_v2.py"
raw = subprocess.run(["git", "cat-file", "blob", "HEAD:" + p], capture_output=True).stdout
with open(p, "wb") as f:
    f.write(raw)
print("written", len(raw), "bytes; sha256:", hashlib.sha256(raw).hexdigest())
import json
exp = json.load(open("case_pipeline/classifier_lib/checksums.json", encoding="utf-8"))
print("expected:", exp)
