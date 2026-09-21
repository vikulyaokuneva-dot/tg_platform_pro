# -*- coding: utf-8 -*-
# Decompile agro.cpython-312.pyc -> restore source-like text for audit (read-only)
import marshal, types, dis, sys, textwrap
with open('case_pipeline/__pycache__/agro.cpython-312.pyc','rb') as f:
    f.read(16)
    code = marshal.load(f)

with open('_agro_decompiled.py','w',encoding='utf-8') as out:
    out.write("# RECONSTRUCTED FROM agro.cpython-312.pyc (read-only)\n")
    out.write("# Source file: case_pipeline/agro.py (source missing; only .pyc exists)\n\n")
    # Main module constants / names
    out.write("MODULE NAMES (co_names): " + str(code.co_names)[:500] + "\n")
    out.write("CONSTANTS preview (first 20):\n")
    for i,c in enumerate(code.co_consts[:20]):
        if isinstance(c, str):
            out.write(f"  {i}: str(len={len(c)}) -> {c[:200]}\n")
        elif isinstance(c, int):
            out.write(f"  {i}: int={c}\n")
        elif isinstance(c, float):
            out.write(f"  {i}: float={c}\n")
        elif isinstance(c, type(code)):
            out.write(f"  {i}: code={c.co_name}\n")
        else:
            out.write(f"  {i}: {type(c)}={str(c)[:80]}\n")
    out.write("\n===== SUB FUNCTION CONSTANTS =====\n")
    for const in code.co_consts:
        if isinstance(const, types.CodeType):
            out.write(f"\n--- FUNCTION: {const.co_name} (line info available) ---\n")
            for i,c in enumerate(const.co_consts[:30]):
                if isinstance(c, str) and len(c) < 300:
                    s = c.replace('\n','\\n')
                    out.write(f"  const[{i}] = \"{s}\"\n")
                elif isinstance(c, int) or isinstance(c, float):
                    out.write(f"  const[{i}] = {c}\n")
                elif isinstance(c, type(const)):
                    out.write(f"  const[{i}] = <code {c.co_name}>\n")
            out.write("  names: " + str(const.co_names[:30]) + "\n")
print("written _agro_decompiled.py")
