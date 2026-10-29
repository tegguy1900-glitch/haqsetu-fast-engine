#!/usr/bin/env bash
# Haq Setu booth boot. Usage:
#   bash boot.sh --check   run the full proof gate suite (self-test; no services)
#   bash boot.sh --init    create dirs + initialize the ledger (genesis)
#   bash boot.sh --live    start the 3 audited services + clock/outbox daemons + backfill loop
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"
[ -d venv ] && source venv/bin/activate 2>/dev/null || true
ENV_FILE="${HAQSETU_ENV:-$HERE/haqsetu.env}"
[ -f "$ENV_FILE" ] && { set -a; . "$ENV_FILE"; set +a; }
CMD="${1:---help}"

gate () {
  local label="$1"; shift
  local d
  d="$(mktemp -d /tmp/bootchk_XXXXXX)"
  env HAQ_CHAIN="$d/chain.jsonl" HAQ_VAULT="$d/vault.jsonl" HAQ_KEYS="$d/keys" \
      HAQ_VAULT_KEY="$d/pii.key" SDM_DB="$d/sdm.db" HAQ_OUTBOX="$d/outbox.db" \
      HAQ_SABHA_PORT=8020 HAQ_SDM_PORT=8110 HAQ_VILLAGE_PORT=8000 \
      HAQ_XP_DIR="$d" HAQ_DASH_DIR="$d" HAQ_B_DIR="$d/b" \
      python -m "$@" >/dev/null 2>&1
  local rc=$?
  rm -rf "$d"
  printf '  %-22s exit=%s\n' "$label" "$rc"
  echo "$rc"
}

case "$CMD" in
  --check)
    echo "== Haq Setu self-test =="
    bad=0
    for m in core.run_wal_migration core.run_clock_demo core.run_xproc_proof \
             core.run_pillar1_demo core.run_village_demo core.run_backfill_demo \
             sabha.run_sabha sabha.run_decoder_demo sdm.run_dashboard_demo \
             core.run_launcher_demo; do
      r=$(gate "$m" "$m")
      [ "$r" = 0 ] || bad=1
    done
    [ "$bad" = 0 ] && echo "SELF-TEST GREEN" || echo "SELF-TEST RED"
    exit "$bad"
    ;;
  --init)
    mkdir -p ledger keys sdm core
    python -c "from core import event_bus; event_bus.init(); print('[boot] ledger genesis ready')"
    ;;
  --live)
    mkdir -p ledger keys sdm core
    python -c "from core import event_bus; event_bus.init()"
    python -m core.backfill & BF=$!
    python -m launcher --live
    kill "$BF" 2>/dev/null
    ;;
  *)
    echo "usage: bash boot.sh [--check|--init|--live]"
    exit 1
    ;;
esac
