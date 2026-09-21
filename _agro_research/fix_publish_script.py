# -*- coding: utf-8 -*-
"""Fix final_production_publish.py: replace canonical_mid with st.add."""
import pathlib

p = pathlib.Path("_agro_research/final_production_publish.py")
t = p.read_text(encoding="utf-8")

old = '    label = verdict.get("label") if isinstance(verdict, dict) else str(verdict)\n    if label == "practical":\n        # Check dedup\n        mid = storage_mod.canonical_mid(url)'
new = '    vtype = verdict.get("type") if isinstance(verdict, dict) else str(verdict)\n    if vtype == "practical":\n        mid = st.add(url, "botanichka")'

if old not in t:
    print("OLD BLOCK NOT FOUND - trying alternate")
    # Try line-by-line replacement
    lines = t.split("\n")
    out = []
    for line in lines:
        if "storage_mod.canonical_mid" in line:
            out.append(line.replace("storage_mod.canonical_mid(url)", "st.add(url, 'botanichka')"))
        elif 'verdict.get("label")' in line:
            out.append(line.replace('verdict.get("label")', 'verdict.get("type")').replace("label", "vtype"))
        elif "if label ==" in line:
            out.append(line.replace("label", "vtype"))
        elif "NOT practical:" in line and "label" in line:
            out.append(line.replace("label", "vtype"))
        else:
            out.append(line)
    p.write_text("\n".join(out), encoding="utf-8")
    print("PATCHED via line-by-line")
else:
    p.write_text(t.replace(old, new), encoding="utf-8")
    print("PATCHED via block replace")
