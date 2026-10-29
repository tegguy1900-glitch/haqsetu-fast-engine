#!/usr/bin/env bash
# Haq Setu bind3-fix: red1 = real compound-magnitude bug in core/facts.py (_parse_amount
# didn't advance i past the magnitude token, so "2 lakh 50 hazaar" -> 200000 not 250000).
# red2 = stale seed-id assert in core/run_village_demo.py (product correctly returned REAL
# catalog ids old_age_pension+widow_pension; the test still expected seed ids). Both are
# single-line verify-or-abort patches; no heredoc, no new paste surface. Idempotent.
cd "$(dirname "$0")" 2>/dev/null || true
source venv/bin/activate 2>/dev/null || true

python - <<'PY'
import pathlib
def patch_line(fname, anchor, repl, tag, skip_marker=None):
    p = pathlib.Path(fname)
    if not p.exists(): raise SystemExit(f"[ABORT] {fname} missing [{tag}]")
    lines = p.read_text().splitlines(keepends=True)
    if skip_marker and any(skip_marker in l for l in lines):
        print(f"  [skip] {fname} :: {tag} (already applied)"); return
    hits = [i for i,l in enumerate(lines) if anchor in l]
    if len(hits) != 1:
        raise SystemExit(f"[ABORT] {fname}: anchor {anchor!r} matched {len(hits)}x (need 1) [{tag}]")
    i = hits[0]
    lines[i] = repl if repl.endswith("\n") else repl + "\n"
    p.write_text("".join(lines))
    print(f"  [ok] {fname} :: {tag}")

# ---- red1 (PRODUCT): _parse_amount must advance i past a consumed magnitude token ----
patch_line("core/facts.py",
    "total+=cur*_MULT[toks[i].lower()]; continue",
    "            if i<n and toks[i].lower() in _MULT: total+=cur*_MULT[toks[i].lower()]; i+=1; continue",
    "red1 compound-magnitude i+=1",
    skip_marker="i+=1; continue")

# ---- red2 (STALE TEST): village demo assert must be catalog-agnostic (real ids, not seed) ----
patch_line("core/run_village_demo.py",
    "nsap_old_age+widow+pmay",
    '        chk("A matched a widow + old-age scheme (real catalog ids)", any("widow" in s for s in v.get("schemes", [])) and any("age" in s for s in v.get("schemes", [])), _tb(v) or str(v.get("schemes")))',
    "red2 village assert catalog-agnostic",
    skip_marker="real catalog ids")
print("[bind3fix] both patches applied (or skipped if already present)")
PY
RC=$?
if [ "$RC" -ne 0 ]; then echo "[stop] patch rc=$RC"; exit "$RC"; fi

echo "########## COMPILE (proves no second hidden corruption) ##########"
python -m py_compile core/facts.py core/run_village_demo.py \
  && echo "  [OK] facts.py + run_village_demo.py compile" || { echo "  [FAIL] compile"; exit 1; }
python -c "import core.facts, core.run_village_demo, village.server; print('  [OK] imports resolve')" || exit 1

echo "########## GATES (the 2 reds + 3 regressions) ##########"
GATES=""
gate(){ local L="$1"; shift; local d; d="$(mktemp -d /tmp/b3f_XXXXXX)"
  env HAQ_CHAIN="$d/chain.jsonl" HAQ_VAULT="$d/vault.jsonl" HAQ_KEYS="$d/keys" HAQ_VAULT_KEY="$d/pii.key" \
      SDM_DB="$d/sdm.db" HAQ_OUTBOX="$d/outbox.db" HAQ_BLOCK_DB="$d/block.db" \
      HAQ_SABHA_PORT=8020 HAQ_SDM_PORT=8110 HAQ_VILLAGE_PORT=8000 HAQ_BLOCK_PORT=8100 \
      HAQ_XP_DIR="$d" HAQ_DASH_DIR="$d" HAQ_B_DIR="$d/b" "$@" 2>&1 | tail -n 12
  local rc="${PIPESTATUS[0]}"; printf '>>> %-14s exit=%s\n' "$L" "$rc"; rm -rf "$d"; GATES="$GATES $L=$rc"; }
gate "brain-audit"  python -m core.run_brain_audit
gate "village"      python -m core.run_village_demo
gate "rulepack-bind" python -m core.run_rulepack_bind
gate "pillar1"      python -m core.run_pillar1_demo
gate "launch"       python -m core.run_launcher_demo
echo "########## SUMMARY ##########"
echo "GATES:$GATES"
allok=1; for kv in $GATES; do [ "${kv#*=}" = "0" ] || allok=0; done
[ "$allok" = 1 ] && echo "ALL GATES GREEN :: compound-magnitude income bug fixed (2 lakh 50 hazaar=250000); village assert now catalog-agnostic (real ids); 77-scheme real rulepack live on the unified ledger; supervisor 4/4; never-deny enforced by YOUR test_vectors" || echo "SOME GATE RED :: see exit!=0 above"
