#!/usr/bin/env bash
# D1-D4 robust repair. Run: cd ~/Downloads/project1 && bash d14fix.sh
# Uses function-level replacement + single-line anchors (no multi-line exact matching).
cd "$(dirname "$0")" 2>/dev/null || true
source venv/bin/activate 2>/dev/null || true

python - <<'PYEOF'
import pathlib, sys, re

def replace_func(source, func_name, new_code):
    lines = source.split('\n')
    start = None
    pat = re.compile(rf'^def {re.escape(func_name)}\(')
    for i, line in enumerate(lines):
        if pat.match(line):
            start = i; break
    if start is None:
        raise SystemExit(f"[ABORT] def {func_name}( not found")
    end = start + 1
    while end < len(lines):
        l = lines[end]
        if l and not l[0].isspace() and not l.startswith('#') and not l.startswith('@'):
            break
        end += 1
    return '\n'.join(lines[:start]) + '\n' + new_code + '\n' + '\n'.join(lines[end:])

def patch_line(fname, anchor, repl, tag):
    p = pathlib.Path(fname)
    if not p.exists(): raise SystemExit(f"[ABORT] {fname} missing [{tag}]")
    lines = p.read_text().splitlines(keepends=True)
    hits = [i for i, l in enumerate(lines) if anchor in l]
    if len(hits) != 1:
        raise SystemExit(f"[ABORT] {fname}: {anchor!r} matched {len(hits)}x (need 1) [{tag}]")
    i = hits[0]
    if isinstance(repl, list):
        lines[i:i+1] = [r if r.endswith('\n') else r+'\n' for r in repl]
    else:
        lines[i] = repl if repl.endswith('\n') else repl+'\n'
    p.write_text(''.join(lines))
    print(f"  [ok] {fname} :: {tag}")

# ===== D1: chain.py _scan_pii opaque-token exemption (function-level replace) =====
cp = pathlib.Path("ledger/chain.py"); src = cp.read_text()
if "_OPAQUE_VALUE_KEYS" in src:
    print("  [skip] D1 already applied")
else:
    new = '''_OPAQUE_VALUE_KEYS = {
    "pii_ref","photo_hash","minutes_hash","chunk_hash","evidence_hash",
    "commitment_id","opened_by_minutes",
}
def _scan_pii(obj, path="payload"):
    if isinstance(obj, dict):
        for k, v in obj.items():
            kl = str(k).strip().lower()
            if kl in _FORBIDDEN_KEYS:
                raise PiiLeakError(f"Forbidden PII key '{k}' at {path}")
            if kl in _OPAQUE_VALUE_KEYS:
                continue
            _scan_pii(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _scan_pii(v, f"{path}[{i}]")
    elif isinstance(obj, str):
        if _AADHAAR_RE.search(obj): raise PiiLeakError(f"Aadhaar-like 12-digit number at {path}")
        if _PHONE_RE.search(obj):   raise PiiLeakError(f"Phone-like 10-digit number at {path}")'''
    cp.write_text(replace_func(src, "_scan_pii", new))
    print("  [ok] ledger/chain.py :: D1 _scan_pii opaque exemption")

# ===== D2a: outbox.py pending(force) (function-level replace) =====
op = pathlib.Path("core/outbox.py"); src = op.read_text()
if "def pending(now=None, force=False):" in src:
    print("  [skip] D2a already applied")
else:
    new = '''def pending(now=None, force=False):
    now = now if now is not None else time.time()
    with _conn() as c:
        if force:
            return c.execute(
                "SELECT id,key,url,method,payload,attempts,status FROM deliveries"
                " WHERE status='pending' ORDER BY id").fetchall()
        return c.execute(
            "SELECT id,key,url,method,payload,attempts,status FROM deliveries"
            " WHERE status='pending' AND next_try<=? ORDER BY id", (now,)).fetchall()'''
    src = replace_func(src, "pending", new)
    op.write_text(src)
    print("  [ok] core/outbox.py :: D2a pending(force)")

# ===== D2b: outbox.py flush_once signature + pending call (single-line anchors) =====
src = op.read_text()
if "force=False" in src and "pending(now, force=force)" in src:
    print("  [skip] D2b already applied")
else:
    patch_line("core/outbox.py",
        "def flush_once(now=None, timeout=3, max_attempts=5):",
        "def flush_once(now=None, timeout=3, max_attempts=5, force=False):",
        "D2b flush_once sig")
    patch_line("core/outbox.py",
        "in pending(now):",
        "in pending(now, force=force):",
        "D2b flush_once call")

# ===== D2c: village/server.py /sync force=True (single-line anchor) =====
patch_line("village/server.py",
    "HAQ_SYNC_MAXATT",
    ['            _send(self, 200, outbox.flush_once(force=True,',
     '                      max_attempts=int(os.environ.get("HAQ_SYNC_MAXATT", "5"))))'],
    "D2c village /sync force")

# ===== D4: run_xproc_proof.py stale assert (single-line anchor) =====
patch_line("core/run_xproc_proof.py",
    "did NOT spawn legacy village/sdm_node",
    ['    chk("supervisor did NOT spawn the STILL-unaudited sdm_node", "sdm_node" not in spawned, str(spawned))',
     '    chk("supervisor DID spawn the now-audited village", "village" in spawned, str(spawned))'],
    "D4 xproc assert refresh")

print("[d14fix] all patches applied via function-level + single-line anchors (whitespace-drift immune)")
PYEOF

RC=$?
if [ "$RC" -ne 0 ]; then echo "[stop] patch rc=$RC"; exit $RC; fi

echo "########## GATES (8 suites, fresh sandbox each) ##########"
GATES=""
gate () {
  local label="$1"; shift; local d; d="$(mktemp -d /tmp/d14_XXXXXX)"
  env HAQ_CHAIN="$d/chain.jsonl" HAQ_VAULT="$d/vault.jsonl" HAQ_KEYS="$d/keys" \
      HAQ_VAULT_KEY="$d/pii.key" SDM_DB="$d/sdm.db" HAQ_OUTBOX="$d/outbox.db" \
      HAQ_SABHA_PORT=8020 HAQ_SDM_PORT=8110 HAQ_VILLAGE_PORT=8000 \
      HAQ_XP_DIR="$d" HAQ_DASH_DIR="$d" HAQ_B_DIR="$d/b" "$@" 2>&1 | tail -n 5
  local rc="${PIPESTATUS[0]}"
  printf '>>> %-12s exit=%s\n' "$label" "$rc"
  rm -rf "$d"; GATES="$GATES $label=$rc"
}
gate "wal"        python -m core.run_wal_migration
gate "clock"      python -m core.run_clock_demo
gate "xproc"      python -m core.run_xproc_proof
gate "pillar1"    python -m core.run_pillar1_demo
gate "village"    python -m core.run_village_demo
gate "sabha"      python -m sabha.run_sabha
gate "dash"       python -m sdm.run_dashboard_demo
gate "launch"     python -m core.run_launcher_demo
echo "########## SUMMARY ##########"
echo "GATES:$GATES"
allok=1; for kv in $GATES; do [ "${kv#*=}" = "0" ] || allok=0; done
[ "$allok" = 1 ] && echo "ALL GATES GREEN :: D1 opaque exemption live, D2 manual-sync force live, D4 xproc expects audited village" || echo "SOME GATE RED :: see exit!=0 above"
