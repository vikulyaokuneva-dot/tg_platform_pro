# -*- coding: utf-8 -*-
"""Восстановление postgen.py из повреждённой копии (инверсия mojibake + сним
структурных повреждений, нанесённых этой сессией) с верификацией против
эталонного bytecode Task-J (__pycache__/postgen.cpython-312.pyc, собранный
до порчи). Скрипт временный."""
import io
import marshal
import struct
import sys

t = io.open("_agro_research/repaired_stage1.py", encoding="utf-8").read()

# --- сним 1: блок AGRO_HASHTAGS, вставленный в mid-validate_post, + осиротевшая
# строка ML-гейта -> восстановить исходные 2 строку if-продолжения, убрать вставку
start = t.index("# ---------------- AGRO HASHTAGS ----------------")
end_marker = 'errors.append("headline: ML-claim not backed by source")'
end = t.index(end_marker)
orig_if = (
    '    if re.search(r"\\bml\\b|машинн", hl) and \\\n'
    '            not re.search(r"\\bml\\b|machine|машинн", srcb):\n        '
)
t = t[:start] + orig_if + t[end:]

# --- сним 2: tags_for_case -> оригинальный однострочный return
# (осторожно: "    return tags" встречается и в render_template — берём
#  первое вхождение строго после блока is_agro внутри tags_for_case)
b_start = t.index("    tags = hashtags.build(\"case\", blob, case.get(\"company_name\"))")
agro_use = t.index("        tags.extend(AGRO_HASHTAGS)", b_start)
b_end = t.index("    return tags", agro_use) + len("    return tags")
t = (t[:b_start]
     + "    return hashtags.build(\"case\", blob, case.get(\"company_name\"))"
     + t[b_end:])

# --- верификация: компилируем и сравниваем code-объекты с эталонным pyc
try:
    cand = compile(t, "postgen.py", "exec")
except SyntaxError as e:
    print("SYNTAX FAIL:", e)
    sys.exit(1)

with open("case_pipeline/__pycache__/postgen.cpython-312.pyc", "rb") as f:
    f.read(16)
    ref = marshal.load(f)

def norm(code):
    consts = []
    for k in code.co_consts:
        if hasattr(k, "co_code"):
            consts.append(norm(k))
        else:
            consts.append(k)
    return (code.co_name, tuple(code.co_names), tuple(consts))

a, b = norm(cand), norm(ref)
if a == b:
    print("MATCH: код восстановлен точечно (константы и имена совпадают с эталоном)")
else:
    # показать различия
    def diff(x, y, path=""):
        if x == y:
            return
        if isinstance(x, tuple) and len(x) == 3 and x[0] == y[0]:
            if x[1] != y[1]:
                print("names differ in", path or x[0], set(x[1]) ^ set(y[1]))
            for i, (cx, cy) in enumerate(zip(x[2], y[2])):
                if isinstance(cx, tuple) and len(cx) == 3 and not isinstance(cx[0], str) or (
                        isinstance(cx, tuple) and len(cx) == 3 and isinstance(cx[2], list)):
                    diff(cx, cy, path + "/" + str(i))
                elif cx != cy:
                    print("const differ", path, i, repr(cx)[:90], "REF:", repr(cy)[:90])
            if len(x[2]) != len(y[2]):
                print("const count", path or x[0], len(x[2]), "vs", len(y[2]))
        elif x != y:
            print("diff", path, repr(x)[:80], "VS", repr(y)[:80])
    diff(a, b)
    sys.exit(2)

with io.open("case_pipeline/postgen.py", "w", encoding="utf-8", newline="") as f:
    f.write(t)
print("postgen.py записан")
