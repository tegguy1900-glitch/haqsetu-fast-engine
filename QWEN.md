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
