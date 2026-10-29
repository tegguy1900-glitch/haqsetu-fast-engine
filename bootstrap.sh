#!/usr/bin/env bash
# Haq Setu recovery bootstrap. Writes the 4 agent files CORRECTLY and verifies them,
# so prose can never leak into a file again. Run: bash bootstrap.sh
cd "$(dirname "$0")" 2>/dev/null || true
mkdir -p .agent

cat > HANDOFF.md <<'HF_MD'
# HANDOFF — Haq Setu

## Current state
The bedrock is built and green. Do not rebuild it.

Protected/proven components:
- ledger/chain.py: SQLite-WAL append-only ledger
- ledger/pii_store.py: encrypted PII vault
- core/event_bus.py: unified event bus
- core/outbox.py: offline propagation queue
- core/sla_clock.py: civic/commitment/petition clock
- rulepack/loader.py: YAML harvest with date coercion
- launcher.py: supervisor 4/4

Important working components:
- core/facts.py: never-invent fact extractor
- core/rule_engine.py: declarative engine using real PRIORITY
- rulepack/catalog.py: seed fallback catalog
- village/server.py: audited booth node
- block/server.py: audited upstream node
- sabha/*: Sabha pipeline
- sdm/*: dashboard/board
- all existing core/run_*_demo.py gates

Known green gates:
core.run_wal_migration, core.run_clock_demo, core.run_xproc_proof,
core.run_pillar1_demo, core.run_village_demo, core.run_backfill_demo,
sabha.run_sabha, sabha.run_decoder_demo, sdm.run_dashboard_demo,
core.run_launcher_demo, core.run_brain_audit, core.run_rulepack_bind

## Non-negotiable invariants
1. Append-only ledger: UPDATE/DELETE must abort.
2. Never leak PII: names/phones/Aadhaar go to vault only.
3. Never deny: uncertain cases abstain and route to human.
4. Never fabricate facts or schemes.
5. PRIORITY is from engine/rules.py: verify > needs_official_decision > include.
6. PyYAML date objects must be coerced to ISO strings at harvest.
7. Supervisor refuses unaudited legacy code.
8. Offline booth remains locally durable.
9. Do not resurrect legacy chain: server.py, box/, api/, old JSONL chains.
10. Do not mark catalog thresholds verified without human review.

## Remaining automatable bricks
grievance, abstain-cal, planner, redflags, closure, ladder, federation

## Human-only work
- verify-catalog: human must verify official thresholds.
- stt/deploy: operator must install real STT and deploy booth.

## Definition of done for a brick
Its own new gate passes AND all prior gates still pass AND no protected
invariant is weakened AND diff reviewed by human AND commit on branch.

## Gate runner
./run_gates.sh   (checks protected files, runs all required gates, plus any
new brick gate that exists as core.run_<brick>_demo)
HF_MD

cat > QWEN.md <<'QW_MD'
# QWEN CODER OPERATING RULES

You are working on Haq Setu.

## Before doing anything
Read: HANDOFF.md, QWEN.md, BRICK_PROMPT.txt, .agent/protected.sha256, run_gates.sh

## Allowed work
Implement only ONE brick at a time from HANDOFF.md.

## Forbidden
- edit protected files without explicit human approval;
- weaken append-only, PII guard, never-deny, never-fabricate, PRIORITY, date coercion;
- resurrect legacy server.py / box / api chains;
- add new dependencies without approval;
- use network without approval;
- use real citizen PII in tests;
- mark scheme thresholds verified;
- push to main;
- start the next brick after finishing one.

## Required workflow per brick
1. State the plan in 5 bullets.
2. Wait for human approval if it touches protected files or adds deps.
3. Implement using whole-file writes where practical.
4. Run ./run_gates.sh
5. If red, read the actual failure and repair ONCE.
6. If still red, stop and report the traceback. Do not loop.
7. If green, commit: git add . && git commit -m "brick: <name> green"
8. Stop. Do not start the next brick.

## Style
Small auditable changes. Preserve public APIs unless the brick requires change.
Add a gate for every new capability, named core.run_<brick>_demo.py.
Tests run in fresh sandboxes, never against the project ledger.
QW_MD

cat > run_gates.sh <<'RG_SH'
#!/usr/bin/env bash
set -u
cd "$(dirname "$0")"
[ -d venv ] && source venv/bin/activate 2>/dev/null || true
REPORT=".agent/last_gate_report.txt"
mkdir -p .agent
: > "$REPORT"
PROT=".agent/protected.sha256"
if [ -f "$PROT" ]; then
  if ! sha256sum -c "$PROT" >/dev/null 2>&1; then
    echo "[FAIL] Protected bedrock files changed. Restore them or get explicit human approval." | tee -a "$REPORT"
    sha256sum -c "$PROT" 2>&1 | tee -a "$REPORT"
    exit 2
  fi
fi
REQUIRED_GATES=(
  core.run_wal_migration core.run_clock_demo core.run_xproc_proof
  core.run_pillar1_demo core.run_village_demo core.run_backfill_demo
  sabha.run_sabha sabha.run_decoder_demo sdm.run_dashboard_demo
  core.run_launcher_demo core.run_brain_audit core.run_rulepack_bind
)
OPTIONAL_GATES=(
  core.run_block_demo core.run_grievance_demo core.run_abstain_cal_demo
  core.run_planner_demo core.run_redflags_demo core.run_closure_demo
  core.run_ladder_demo core.run_federation_demo
)
for g in "${OPTIONAL_GATES[@]}"; do
  if python -c "import importlib,sys; importlib.import_module(sys.argv[1])" "$g" 2>/dev/null; then
    REQUIRED_GATES+=("$g")
  fi
done
fail=0
for g in "${REQUIRED_GATES[@]}"; do
  d="$(mktemp -d /tmp/qgate_XXXXXX)"
  log="$d/log.txt"
  env HAQ_CHAIN="$d/chain.jsonl" HAQ_VAULT="$d/vault.jsonl" HAQ_KEYS="$d/keys" \
      HAQ_VAULT_KEY="$d/pii.key" SDM_DB="$d/sdm.db" HAQ_OUTBOX="$d/outbox.db" \
      HAQ_BLOCK_DB="$d/block.db" HAQ_SABHA_PORT=8020 HAQ_SDM_PORT=8110 \
      HAQ_VILLAGE_PORT=8000 HAQ_BLOCK_PORT=8100 HAQ_XP_DIR="$d" HAQ_DASH_DIR="$d" \
      HAQ_B_DIR="$d/b" python -m "$g" >"$log" 2>&1
  rc=$?
  printf '%-32s exit=%s\n' "$g" "$rc" | tee -a "$REPORT"
  if [ "$rc" -ne 0 ]; then
    fail=1
    echo "----- last 80 lines for $g -----" | tee -a "$REPORT"
    tail -n 80 "$log" | tee -a "$REPORT"
    echo "--------------------------------" | tee -a "$REPORT"
  fi
  rm -rf "$d"
done
if [ "$fail" -eq 0 ]; then echo "ALL_GATES_GREEN" | tee -a "$REPORT"; else echo "GATES_RED" | tee -a "$REPORT"; fi
exit "$fail"
RG_SH

cat > BRICK_PROMPT.txt <<'BP_TXT'
Read HANDOFF.md and QWEN.md.

Implement ONLY brick {{BRICK}}.

Do not touch protected files. Do not add dependencies. Do not use network.
Do not resurrect legacy server.py / box / api chains. Do not weaken append-only,
PII guard, never-deny, never-fabricate, PRIORITY, or date coercion.

Required:
- Add or update a gate named core.run_{{BRICK}}_demo.py unless HANDOFF says otherwise.
- Run ./run_gates.sh.
- If red, repair ONCE. If still red, stop and paste the exact traceback.
- If green, commit on the current branch: brick: {{BRICK}} green
- Stop. Do not start the next brick. Show me the diff before committing.
BP_TXT

# ---------------- self-verification: a mis-paste cannot pass silently ----------------
ok=1
e(){ echo "  [FAIL] $1"; ok=0; }
head -1 run_gates.sh | grep -qx '#!/usr/bin/env bash' || e "run_gates.sh line 1 is not the shebang (prose leaked in)"
bash -n run_gates.sh 2>/dev/null || e "run_gates.sh is not valid bash"
grep -q 'ALL_GATES_GREEN' run_gates.sh || e "run_gates.sh missing its sentinel"
grep -q 'You are working on Haq Setu' run_gates.sh && e "run_gates.sh contains QWEN prose (wrong block pasted)"
grep -q 'Non-negotiable invariants' run_gates.sh && e "run_gates.sh contains HANDOFF prose (wrong block pasted)"
grep -q 'Non-negotiable invariants' HANDOFF.md || e "HANDOFF.md missing its sentinel"
grep -q 'ALL_GATES_GREEN' HANDOFF.md && e "HANDOFF.md contains run_gates text (wrong block pasted)"
grep -q 'QWEN CODER OPERATING RULES' QWEN.md || e "QWEN.md missing its sentinel"
grep -q 'ALL_GATES_GREEN' QWEN.md && e "QWEN.md contains run_gates text (wrong block pasted)"
grep -q '{{BRICK}}' BRICK_PROMPT.txt || e "BRICK_PROMPT.txt missing {{BRICK}} placeholder"
chmod +x run_gates.sh
sha256sum ledger/chain.py ledger/pii_store.py core/event_bus.py core/outbox.py \
          core/sla_clock.py rulepack/loader.py launcher.py > .agent/protected.sha256 2>/dev/null \
  || e "could not hash bedrock (are you in ~/Downloads/project1?)"
[ "$ok" = 1 ] && echo "SETUP_OK :: 4 files written and verified; protected.sha256 regenerated" \
              || echo "SETUP_FAIL :: see [FAIL] lines above; re-copy ONLY the code block and re-run"
