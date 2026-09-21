# -*- coding: utf-8 -*-
import io

t = io.open("_agro_research/repaired_stage1.py", encoding="utf-8").read()
def line_of(idx):
    return t[:idx].count("\n") + 1

i1 = t.find("# ---------------- AGRO HASHTAGS")
print("first AGRO marker: char", i1, "line", line_of(i1))
i1b = t.find("# ---------------- AGRO HASHTAGS", i1 + 1)
print("second occurrence:", i1b)
i2 = t.find('errors.append("headline: ML-claim not backed by source")')
print("ML errors.append line", line_of(i2))
i3 = t.find("tags = hashtags.build")
print("tags_for_case edit line", line_of(i3))
i4 = t.find("return tags", i3)
print("return tags line", line_of(i4))
print("POLISH exists:", "POLISH_SYSTEM_TMPL = (" in t)
print("render_template def:", "def render_template" in t)
# сколько всего AGRO-блоков
print("AGRO_HASHTAGS count:", t.count("AGRO_HASHTAGS"))
io.open("_agro_research/stage1_lines.txt", "w", encoding="utf-8").write(
    "\n".join("%d: %s" % (n + 1, l) for n, l in enumerate(t.splitlines()[905:930])))
