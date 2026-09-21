# -*- coding: utf-8 -*-
import pathlib

p = pathlib.Path("_agro_research/final_production_publish.py")
lines = p.read_text(encoding="utf-8").split("\n")
out = []
for line in lines:
    if line.strip() == "# Claim in AGRO DB":
        out.append("# Set post_ready so claim can grab it")
        out.append('st.update(mid, status="post_ready")')
    else:
        out.append(line)
p.write_text("\n".join(out), encoding="utf-8")
print("patched claim flow")
