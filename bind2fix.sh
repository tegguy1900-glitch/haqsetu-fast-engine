#!/usr/bin/env bash
# Haq Setu bind2-fix: surgically unfuse the one dropped "," in run_rulepack_bind.py.
# Zero heredoc, zero new paste risk. The other 3 files already compiled clean -> untouched.
cd "$(dirname "$0")" 2>/dev/null || true
source venv/bin/activate 2>/dev/null || true

python - <<'PY'
import pathlib
p = pathlib.Path("core/run_rulepack_bind.py"); s = p.read_text()

# anchor 1: the REPORTED fused dict token (must match exactly once)
a1o = '"desk":"block_development_officerclock_hours":72'
a1n = '"desk":"block_development_officer","clock_hours":72'
if s.count(a1o) != 1:
    raise SystemExit(f"[ABORT] dict anchor matched {s.count(a1o)}x (need 1); file differs from the reported corruption")
s = s.replace(a1o, a1n, 1); print("[fix1] ROAD dict: desk/clock_hours unfused")

# anchor 2: the assert MAY carry the same fused token (my source typo OR the same paste drop); 0 or 1 ok
a2o = '=="block_development_officerclock_hours"'
a2n = '=="block_development_officer"'
n2 = s.count(a2o)
if n2 == 1:
    s = s.replace(a2o, a2n, 1); print("[fix2] assert: desk comparison unfused")
elif n2 == 0:
    print("[skip2] assert already clean (no fused token to fix)")
else:
    raise SystemExit(f"[ABORT] assert anchor matched {n2}x (ambiguous, not patching)")

p.write_text(s); print("[patched] core/run_rulepack_bind.py")
PY
RC=$?
if [ "$RC" -ne 0 ]; then echo "[stop] fix rc=$RC"; exit "$RC"; fi

echo "########## COMPILE (proves no SECOND hidden syntax drop) ##########"
python -m py_compile core/run_rulepack_bind.py \
  && echo "  [OK] run_rulepack_bind.py compiles (line-34 corruption gone, no other syntax error)" \
  || { echo "  [FAIL] a SECOND corruption exists below line 34; paste this and I fix it next round"; exit 1; }
python -c "import core.run_rulepack_bind; print('  [OK] imports resolve')" || exit 1

echo "########## GATES (real-catalog bind + unregression) ##########"
GATES=""
gate(){ local L="$1"; shift; local d; d="$(mktemp -d /tmp/b2f_XXXXXX)"
  env HAQ_CHAIN="$d/chain.jsonl" HAQ_VAULT="$d/vault.jsonl" HAQ_KEYS="$d/keys" HAQ_VAULT_KEY="$d/pii.key" \
      SDM_DB="$d/sdm.db" HAQ_OUTBOX="$d/outbox.db" HAQ_BLOCK_DB="$d/block.db" \
      HAQ_SABHA_PORT=8020 HAQ_SDM_PORT=8110 HAQ_VILLAGE_PORT=8000 HAQ_BLOCK_PORT=8100 \
      HAQ_XP_DIR="$d" HAQ_DASH_DIR="$d" HAQ_B_DIR="$d/b" "$@" 2>&1 | tail -n 30
  local rc="${PIPESTATUS[0]}"; printf '>>> %-14s exit=%s\n' "$L" "$rc"; rm -rf "$d"; GATES="$GATES $L=$rc"; }
gate "rulepack-bind" python -m core.run_rulepack_bind
gate "brain-audit"  python -m core.run_brain_audit
gate "village"      python -m core.run_village_demo
gate "pillar1"      python -m core.run_pillar1_demo
gate "launch"       python -m core.run_launcher_demo
echo "########## SUMMARY ##########"
echo "GATES:$GATES"
allok=1; for kv in $GATES; do [ "${kv#*=}" = "0" ] || allok=0; done
[ "$allok" = 1 ] && echo "REAL RULEPACK LIVE :: your ~70 YAML schemes drive decisions on the unified ledger; PRIORITY adopted verbatim from engine/rules.py; PyYAML date objects coerced (village crash gone); never-deny enforced by YOUR test_vectors" || echo "SOME GATE RED :: see exit!=0 above"
