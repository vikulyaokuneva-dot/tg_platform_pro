# -*- coding: utf-8 -*-
"""classifier_lib — замороженная production-база классификации (V2, holdout-validated).

Файлы classifier_v2.py / classifier_baseline.py скопированы byte-identical из
parser_poc_results/classifier_v2_validation (см. checksums.json). При импорте
проверяется SHA256: любое расхождение — RuntimeError (защита от тихой правки).

v2 импортирует baseline как плоский модуль, поэтому каталог добавляется в
sys.path (сам код классификатора не модифицируется).
"""
import hashlib
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _sha(path):
    return hashlib.sha256(io.open(path, "rb").read()).hexdigest()


def verify():
    manifest = json.load(io.open(os.path.join(HERE, "checksums.json"), encoding="utf-8-sig"))
    for fname, want in manifest.items():
        if not fname.endswith(".py"):
            continue
        got = _sha(os.path.join(HERE, fname))
        if got != want:
            raise RuntimeError("classifier integrity check failed for %s: %s != %s"
                               % (fname, got, want))
    return True


if HERE not in sys.path:
    sys.path.insert(0, HERE)
verify()

import classifier_v2 as V2  # noqa: E402  (плоский импорт замороженного модуля)

__all__ = ["V2", "verify"]
