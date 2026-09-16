# -*- coding: utf-8 -*-
import io
import os

t = io.open("_agro_research/repaired_stage1.py", encoding="utf-8").read()
print("stage1 lines:", len(t.splitlines()))
# где обрыв
for probe in ("def _head_body", "def headline_issues", "def _mechanics",
              "def clean_for_publish", "def tags_for_case", "def render_template",
              "POLISH_SYSTEM_TMPL = (", "def editorial_check"):
    print(probe, "->", t.find(probe))
print("---- tail of stage1 ----")
print("\n".join(t.splitlines()[-25:]))

print("---- backup files ----")
for p in ("_hl_before.txt", "_hl_after.txt"):
    print(p, os.path.exists(p))
