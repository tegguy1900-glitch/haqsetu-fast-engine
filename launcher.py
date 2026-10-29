"""
Haq Setu - Process Supervisor.  Boots EXACTLY the proven services; REFUSES the
unaudited legacy ones by name, with a reason, even when their files exist on disk.
This refusal is the never-guess rule at the process layer: we will not execute
code we have not read, because running unaudited code is precisely how the five
fragmented chains came back.  Stdlib only.

Topology note (honest limitation, see run_launcher_demo caveats): in production the
village node (8000) and sabha service (8020) both append to ONE local chain.jsonl.
That multi-writer pattern leans on O_APPEND line-atomicity and is NOT a production
guarantee. The fix (SQLite-WAL ledger, single-writer or serialized appends) is the
designated next brick; until then `--live` starts the write-daemons with a loud
caveat, and the supervised demo deliberately probes children read-only to stay
race-free.

CLI:
  python -m launcher            -> plan + import-validate + legacy-refusal (dry)
  python -m launcher --live     -> the above, then spawn proven nodes + daemons
"""
import os, sys, time, signal, threading, importlib, subprocess

# name, module, port-env, default-port, legacy?, reason-if-skipped
SERVICES = [
    dict(name="sabha",       module="sabha.server", port_env="HAQ_SABHA_PORT", default=8020,
         legacy=False, reason=None),
    dict(name="sdm_preview", module="sdm.server",   port_env="HAQ_SDM_PORT",   default=8110,
         legacy=False, reason=None),
    dict(name="village", module="village.server", port_env="HAQ_VILLAGE_PORT", default=8000,
         legacy=False, reason=None),
    dict(name="sdm_node", module="block.server", port_env="HAQ_BLOCK_PORT", default=8100,
         legacy=False, reason=None),
]
DAEMON_MODULES = ["core.sla_clock", "core.outbox"]   # proven, importable, single-writer-safe in demo

def _port(svc, env=None):
    env = env if env is not None else os.environ
    return int(env.get(svc["port_env"], svc["default"]))

def plan(env=None):
    """Decide launch/skip per service WITHOUT importing legacy modules."""
    env = env if env is not None else os.environ
    enable_legacy = (env.get("HAQ_ENABLE_LEGACY", "0") == "1")
    out = []
    for s in SERVICES:
        present = os.path.exists(s["module"].replace(".", "/") + ".py") or \
                  os.path.exists(s["module"].split(".")[0] + "/" + s["module"].split(".")[-1] + ".py")
        if s["legacy"]:
            action = "launch" if enable_legacy else "SKIP"
            why = ("explicitly opted-in via HAQ_ENABLE_LEGACY=1 (still unaudited!)"
                   if enable_legacy else s["reason"])
        else:
            action, why = "launch", None
        out.append({**s, "port": _port(s, env), "file_present_on_disk": present,
                    "action": action, "why": why})
    return out

def validate(env=None):
    """Import ONLY the proven (non-legacy) modules + daemon libs. Legacy never imported."""
    res = {}
    for s in SERVICES:
        if s["legacy"]:
            res[s["name"]] = "REFUSED-import (unaudited)"
            continue
        try:
            importlib.import_module(s["module"]); res[s["name"]] = "ok"
        except Exception as e:
            res[s["name"]] = f"IMPORT-FAIL: {e}"
    for m in DAEMON_MODULES:
        try:
            importlib.import_module(m); res[m] = "ok"
        except Exception as e:
            res[m] = f"IMPORT-FAIL: {e}"
    return res

def spawn(decisions, env=None):
    """Popen the launchable non-legacy services. Returns list of (name, Popen, logpath)."""
    env = env if env is not None else os.environ
    kids = []
    for d in decisions:
        if d["action"] != "launch" or d["legacy"]:
            continue
        logp = os.path.join(env.get("HAQ_LAUNCH_LOGDIR", "."), f"{d['name']}.log")
        lf = open(logp, "wb")
        p = subprocess.Popen([sys.executable, "-m", d["module"]], env=env,
                             stdout=lf, stderr=subprocess.STDOUT)
        kids.append((d["name"], p, logp, lf))
    return kids

def start_daemons(stop, env=None, log=print):
    """Background threads: sla_clock tick loop + outbox flush loop.
    CAVEAT: these WRITE to the local chain; do not run them concurrently with
    child servers that also write the same chain until the ledger is SQLite-WAL."""
    from core import event_bus, sla_clock as clock, outbox
    event_bus.init()
    def _tick():
        iv = int((env or os.environ).get("HAQ_TICK_INTERVAL", "60"))
        while not stop.is_set():
            try:
                r = clock.tick()
                if r["emitted"]:
                    log(f"[sla_clock] tick emitted {len(r['emitted'])} breach; "
                        f"{[w for w in r['warnings']][:1]}")
            except Exception as e:
                log(f"[sla_clock] tick error (kept looping): {e}")
            stop.wait(iv)
    th = threading.Thread(target=_tick, daemon=True); th.start()
    fh = threading.Thread(target=outbox.flush_loop,
                          kwargs=dict(stop=stop, log=log), daemon=True); fh.start()
    return [th, fh]

def _shutdown(kids, stop):
    stop.set()
    for name, p, logp, lf in kids:
        try:
            p.send_signal(signal.SIGTERM); p.wait(timeout=5)
        except Exception:
            try: p.kill()
            except Exception: pass
        lf.close()

def main(argv):
    live = "--live" in argv
    print("=== HAQ SETU SUPERVISOR ===")
    dec = plan()
    for d in dec:
        flag = "FILE-PRESENT" if d["file_present_on_disk"] else "file-absent"
        print(f"  {d['name']:12s} :{d['port']:<5d} {d['action']:5s} [{flag}] "
              f"{(':: ' + d['why']) if d['why'] else ''}")
    val = validate()
    print("--- import validation (legacy NEVER imported) ---")
    for k, v in val.items():
        print(f"  {k:14s} {v}")
    if not live:
        print("(dry-run) add --live to spawn proven nodes + daemons"); return 0
    env = dict(os.environ)
    env.setdefault("HAQ_LAUNCH_LOGDIR", "/tmp")
    stop = threading.Event()
    kids = spawn(dec, env)
    print(f"--- spawned {[k[0] for k in kids]} ; starting daemons (CAVEAT: see header) ---")
    start_daemons(stop, env)
    try:
        while not stop.is_set():
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        _shutdown(kids, stop)
        print("--- children terminated ---")
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
