p = "box/orchestrator.py"
s = open(p, encoding="utf-8").read()
old = '"citizen": "k-cit"}'
new = '"citizen": "k-cit", "block": "k-blk", "district": "k-dist", "state": "k-st"}'
n = s.count(old)
open(p, "w", encoding="utf-8").write(s.replace(old, new))
print("PATCHED orchestrator KEYS:", n, "site(s)")