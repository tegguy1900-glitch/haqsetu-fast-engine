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
