# -*- coding: utf-8 -*-
import io

t = io.open("_agro_research/repaired_stage1.py", encoding="utf-8").read()
start = t.index("# ---------------- AGRO HASHTAGS ----------------")
end_marker = 'errors.append("headline: ML-claim not backed by source")'
end = t.index(end_marker)
orig_if = (
    '    if re.search(r"\\bml\\b|машинн", hl) and \\\n'
    '            not re.search(r"\\bml\\b|machine|машинн", srcb):\n        '
)
t = t[:start] + orig_if + t[end:]
b_start = t.index('    tags = hashtags.build("case", blob, case.get("company_name"))')
agro_use = t.index("        tags.extend(AGRO_HASHTAGS)", b_start)
b_end = t.index("    return tags", agro_use) + len("    return tags")
seg = t[b_start:b_end]
print("segment lines:", seg.count(chr(10)) + 1)
print("segment contains def render_template:", "def render_template" in seg)
io.open("_agro_research/snip.txt", "w", encoding="utf-8").write(seg)
t2 = t[:b_start] + '    return hashtags.build("case", blob, case.get("company_name"))'
print("after: render_template def present:", "def render_template" in t2)
