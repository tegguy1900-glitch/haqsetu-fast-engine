import io
p = "eval/research_harness.py"
src = io.open(p, encoding="utf-8").read().replace("\r\n", "\n")
marker = 'e["cm"] = {f"{a}>>{b}": v for (a, b), v in e["cm"].items()}'
old = '    results = {"data_source": source, "n_cal": len(cal), "n_test": len(test),'
if marker in src:
    print("ALREADY PATCHED")
elif old in src:
    ins = '    for e in (op, noab):\n        ' + marker + '\n'
    io.open(p, "w", encoding="utf-8").write(src.replace(old, ins + old))
    print("PATCHED OK")
else:
    print("LINE NOT FOUND - tell me")