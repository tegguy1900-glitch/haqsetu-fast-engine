"""Harvest the REAL rulepack YAML (DATA) into engine rows. We do NOT import legacy
engine/rules.py classes; we read your YAML schema and translate faithfully. PyYAML-guarded:
if the parser or the dir is missing, load_rulepack_dir returns None and the caller falls
back to the SEED catalog LOUDLY (provisional) -- we never hand-roll a YAML parse.
CRITICAL (the village crash): your schema.py types verified_on/expires_on as `date`, and
PyYAML deserializes bare `2027-10-09` into datetime.date OBJECTS. A date object is not
JSON-serializable, so it would 500 the /voice HTTP body and break the ledger write. We
recursively coerce EVERY date/datetime in a row to its ISO string at harvest, so no date
object ever reaches json.dumps or the PII guard. This is the single fix for the
'TypeError: Object of type date is not JSON serializable' red."""
import os, glob, datetime
def _coerce_dates(obj):
    if isinstance(obj, (datetime.date, datetime.datetime)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _coerce_dates(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_coerce_dates(v) for v in obj]
    return obj
def discover_root():
    cands = [os.environ.get("HAQ_RULEPACK"), os.getcwd(),
             os.path.dirname(os.path.dirname(os.path.abspath(__file__)))]
    for base in cands:
        if base and os.path.isdir(os.path.join(base, "rulepack", "schemes")):
            return base
    return None
def load_rulepack_dir(root=None):
    root = root if root is not None else discover_root()
    if not root: return None
    try:
        import yaml
    except Exception:
        return None                      # no safe parser -> caller goes provisional
    packs = []
    for sub in ("schemes", "routes"):
        for f in sorted(glob.glob(os.path.join(root, "rulepack", sub, "*.yaml"))):
            try:
                doc = yaml.safe_load(open(f, encoding="utf-8"))
            except Exception:
                continue                 # a bad file is SKIPPED, not guessed
            if isinstance(doc, dict) and "scheme" in doc and "rules" in doc:
                packs.append(doc)
    return packs or None
def rows_from_packs(packs):
    """Faithful translation: when(AND)->requires; carry outcome/documents/desk/clock_hours/
    contact/source/verified_*/expires_on/test_vectors. One row per (scheme,rule). All date
    objects coerced to ISO strings (see _coerce_dates) so downstream json + guard are safe."""
    rows = []
    for pk in packs or []:
        sid = pk.get("scheme"); st = pk.get("state", "")
        for rl in pk.get("rules", []) or []:
            reqs = [{"fact": c.get("field"), "op": c.get("op", "eq"), "value": c.get("value")}
                    for c in (rl.get("when", []) or [])]
            row = {
                "scheme_id": sid, "rule_id": rl.get("id"), "state": st,
                "description": rl.get("description", ""), "requires": reqs,
                "outcome": rl.get("outcome", "include"),
                "documents": rl.get("documents", []) or [], "desk": rl.get("desk", ""),
                "clock_hours": rl.get("clock_hours"), "contact": rl.get("contact"),
                "source": rl.get("source", {}) or {},
                "verified_on": rl.get("verified_on"), "verified_by": rl.get("verified_by", []) or [],
                "expires_on": rl.get("expires_on"), "test_vectors": rl.get("test_vectors", []) or [],
            }
            rows.append(_coerce_dates(row))
    return rows
