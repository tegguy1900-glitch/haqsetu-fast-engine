"""
Haq Setu - Rule engine. Evaluates facts against the catalog. Catalog source is LAZY:
the REAL rulepack YAML if discoverable+parseable (it IS, on this box), else the auditable
SEED catalog with provisional=True (loud, never silent). Contract match_fn(facts)->
{confidence, schemes, trace, routed_verifies, provisional} is UNCHANGED so process_voice
and village are untouched; extra keys are additive. NEVER asserts a scheme outside the
catalog; NEVER fills a missing fact; a LAPSED rule (expires_on < today) is never acted on.

PRIORITY is taken VERBATIM from your engine/rules.py:
    PRIORITY = {Outcome.VERIFY:3, Outcome.NEEDS_OFFICIAL_DECISION:2, Outcome.INCLUDE:1}
    final    = max(matched_outcomes, key=PRIORITY)        # most-cautious wins
(An earlier draft of this file inverted it with min/include-wins; corrected here against
your literal constant. So among a scheme's FULLY-MATCHED rules, the most cautious outcome
governs: a scheme with both an include and a verify rule is routed to verify, not minted.)
Trace shape additionally mirrors your engine/matcher.py proof: per-scheme decision
(INCLUDE/ESCALATE) + a formal_logic one-liner + matched/failed clause lists. We do NOT
embed citizen_facts on-chain (avoid any leak surface); facts carry no name/phone anyway.
"""
from datetime import date
from rulepack import loader as _ld
from rulepack.catalog import SCHEMES as _SEED

_OPS = {"eq": lambda a,b:a==b, "ne": lambda a,b:a!=b, "gt": lambda a,b:a>b,
        "gte": lambda a,b:a>=b, "lt": lambda a,b:a<b, "lte": lambda a,b:a<=b,
        "in": lambda a,b:(a in b) if isinstance(b,(list,tuple,set)) else False,
        "not_in": lambda a,b:(a not in b) if isinstance(b,(list,tuple,set)) else True,
        "truthy": lambda a,b:bool(a), "falsy": lambda a,b:not bool(a),
        ">=": lambda a,b:a>=b, "<=": lambda a,b:a<=b, ">": lambda a,b:a>b, "<": lambda a,b:a<b,
        "==": lambda a,b:a==b, "!=": lambda a,b:a!=b}
# VERBATIM from your engine/rules.py (most-cautious wins via max):
_PRIORITY = {"include": 1, "needs_official_decision": 2, "verify": 3}
_RANK2NAME = {1: "include", 2: "needs_official_decision", 3: "verify"}

_cat = None; _prov = None
def _catalog():
    global _cat, _prov
    if _cat is None:
        packs = _ld.load_rulepack_dir()
        if packs:
            _cat = _ld.rows_from_packs(packs); _prov = False
        else:
            _cat = [{"scheme_id": s["id"], "rule_id": s["id"]+"_seed", "state": "",
                     "description": s.get("name",""), "requires": s.get("requires",[]),
                     "outcome": "include", "documents": s.get("docs",[]), "desk": "",
                     "clock_hours": None, "contact": None, "source": {"doc": s.get("source","")},
                     "verified_on": None, "verified_by": ["Seed", "VERIFY-BEFORE-PROD"],
                     "expires_on": None, "test_vectors": []} for s in _SEED]
            _prov = True
    return _cat, _prov

def _clause(c, facts):
    fact = c.get("fact"); op = c.get("op","eq"); val = c.get("value")
    if fact not in facts: return "missing", {"fact": fact, "note": "not provided"}
    got = facts[fact]; fn = _OPS.get(op)
    if fn is None: return "missing", {"fact": fact, "note": f"unknown op {op}"}
    try: ok = bool(fn(got, val))
    except Exception: return "missing", {"fact": fact, "note": "type mismatch"}
    return ("sat" if ok else "fail"), {"fact": fact, "op": op, "value": val, "observed": got, "result": ok}

def _eval_row(row, facts, today):
    if row.get("expires_on") and str(row["expires_on"]) < today:
        return "lapsed", []                       # don't act on lapsed authority
    sat=[]; miss=[]; fail=[]
    for c in row.get("requires",[]):
        st,pr=_clause(c,facts); (sat if st=="sat" else miss if st=="missing" else fail).append(pr)
    if fail: return "ineligible", sat+fail
    if miss: return "uncertain", sat+miss
    return "match", sat

def _formal_logic(sid, oname, clauses):
    parts = " AND ".join(f'{c["fact"]} {c.get("op","==")} {c.get("value")!r}'
                         for c in clauses if "op" in c) or "no conditions"
    return f'{sid.upper()} := ({parts}) -> {oname.upper()}'

def evaluate(rows, facts, today=None):
    facts = facts or {}; today = today or date.today().isoformat()
    by_scheme = {}
    for r in rows:
        st, proofs = _eval_row(r, facts, today)
        by_scheme.setdefault(r["scheme_id"], []).append((r, st, proofs))
    includes=[]; verifies=[]; trace=[]
    for sid, evs in by_scheme.items():
        matched = [(r,p) for (r,st,p) in evs if st=="match"]
        lapsed  = any(st=="lapsed" for (_,st,_) in evs)
        if matched:
            rank = max((_PRIORITY.get(r.get("outcome","include"),2) for r,_ in matched), default=2)
            oname = _RANK2NAME[rank]                                   # most-cautious wins (your PRIORITY)
            allp = [p for _,p in matched]
            for r,p in matched:
                trace.append({"scheme": sid, "scheme_name": r.get("description","") or sid,
                              "rule_id": r.get("rule_id"), "outcome": oname,
                              "decision": ("INCLUDE" if oname=="include" else "ESCALATE"),
                              "formal_logic": _formal_logic(sid, oname, p),
                              "clauses": p, "docs": r.get("documents",[]), "benefit": r.get("desk",""),
                              "verified_by": r.get("verified_by",[]), "source": r.get("source",{}),
                              "expires_on": r.get("expires_on"), "lapsed": lapsed})
            if oname=="include": includes.append(sid)
            elif oname=="verify": verifies.append(sid)
        else:
            miss_facts = sorted({pr["fact"] for (_,st,ps) in evs if st in ("uncertain","lapsed") for pr in ps if pr.get("note")=="not provided"})
            trace.append({"scheme": sid, "scheme_name": sid, "rule_id": None,
                          "outcome": "needs_official_decision", "decision": "ESCALATE",
                          "formal_logic": _formal_logic(sid, "needs_official_decision", []),
                          "clauses": [], "docs": [], "benefit": None, "verified_by": [], "source": {},
                          "expires_on": None, "lapsed": lapsed,
                          "uncertain_facts": miss_facts,
                          "note": ("all rules lapsed" if lapsed else "no rule fully matched")})
    conf = round(min(0.97, 0.6 + 0.12*len(includes)), 2) if includes else 0.0
    _, prov = _catalog()
    return {"confidence": conf, "schemes": sorted(set(includes)),
            "routed_verifies": sorted(set(verifies)), "trace": trace, "provisional": prov}

def match_fn(facts):
    rows, _ = _catalog()
    return evaluate(rows, facts)

def to_api_match_shape(facts, civic_hints=None):
    """Mirror your /api/match + triage/abstain contract {action,facts,civic,can,likely,case,speak}.
    can=confident includes; likely=uncertain-but-partial; civic=verify-routed (+ any hints).
    ABSTAIN when nothing confident -- exactly your intake_abstain path."""
    res = match_fn(facts)
    can = res["schemes"]; civic = list(res["routed_verifies"])
    if civic_hints:
        civic = sorted(set(civic) | set(civic_hints))
    likely = sorted({t["scheme"] for t in res["trace"]
                     if t.get("outcome")=="needs_official_decision" and t.get("uncertain_facts")})
    if not can and not civic:
        action="ABSTAIN"; speak="I did not catch clear conditions. The facilitator will ask one question."
    elif can:
        action="INCLUDE"; speak=f"Based on what you told me, you appear eligible for {len(can)} scheme(s)."
    else:
        action="VERIFY"; speak=f"This looks like a grievance to route for verification ({len(civic)})."
    return {"action": action, "facts": facts, "civic": civic, "can": can,
            "likely": likely, "case": "", "speak": speak, "provisional": res["provisional"]}
