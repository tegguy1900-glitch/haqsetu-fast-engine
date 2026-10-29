"""
Haq Setu - Pillar 1 bus-side orchestrator (voice -> scheme -> Haq Receipt).
This module does NOT contain the rule brain. The brain is injected as `match_fn`,
an ADAPTER SEAM: bind it to your engine/rules.py match() and nothing here changes.
A small reference_match_fn is provided ONLY to prove the contract today (stand-in,
like the mock STT decoder); it makes no claim about your 50 YAML rules.

Invariants enforced here (the conceptual Pillar 1 rules, now physical):
  NEVER DENY  : if match_fn raises, returns low confidence, or returns no scheme with
                uncertainty -> we ABSTAIN (emit entitlement_abstained, route to human).
                We never emit a denial. A denial is a human act with a reason code.
  NEVER LEAK  : name/phone go to the vault via emit(pii_fields=...); the ledger sees
                only a blob_id. The proof_trace carries facts+rule_ids+confidence, no PII.
  PROVE IT    : every matched decision carries a proof_trace (which facts fired which
                rule ids) so a citizen/officer/SDM can see WHY, not just WHAT.
  START CLOCK : a confident match issues an entitlement_petition_issued (the Haq
                Receipt / RTPS petition) which the SLA clock tracks like any case.
"""
import os, time, uuid
from core import event_bus

DEFAULT_THRESHOLD = float(os.environ.get("HAQ_CONF_THRESHOLD", "0.6"))

def _new_case():
    return f"HS-{time.strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

def process_voice(actor_role, facts, match_fn, pii_fields=None,
                  confidence_threshold=None, case_id=None):
    """Run one voice->scheme decision through the bus. Returns a summary dict.
    `match_fn(facts)` MUST return {confidence: float|None, schemes: [..], trace: [..]}.
    Bind match_fn = engine.rules.match (adapted to this shape) in production."""
    if not event_bus.is_ready():
        event_bus.init()
    thr = confidence_threshold if confidence_threshold is not None else DEFAULT_THRESHOLD
    cid = case_id or _new_case()
    # ---- call the brain; ANY failure or uncertainty => abstain (never deny) ----
    try:
        res = match_fn(facts)
        if not isinstance(res, dict):
            raise ValueError("match_fn must return a dict {confidence,schemes,trace}")
        conf = res.get("confidence")
        schemes = res.get("schemes") or []
        trace = res.get("trace") or []
    except Exception as e:
        ev = event_bus.emit(actor_role, cid, "entitlement_abstained",
                            {"reason": f"brain_error: {type(e).__name__}", "facts_keys": sorted(facts.keys())},
                            pii_fields=pii_fields)
        return {"decision": "abstained", "case_id": cid, "reason": ev["payload"]["reason"], "event": ev}
    # low confidence OR (no scheme AND we weren't told it's a confident empty) => abstain
    unsure = (conf is None) or (float(conf) < thr) or (not schemes and conf is None)
    if unsure:
        ev = event_bus.emit(actor_role, cid, "entitlement_abstained",
                            {"reason": "low_confidence_or_unsure", "confidence": conf,
                             "facts_keys": sorted(facts.keys())},
                            pii_fields=pii_fields)
        return {"decision": "abstained", "case_id": cid, "confidence": conf, "reason": "low_confidence_or_unsure", "event": ev}
    # ---- confident match: record match + proof trace, then issue the receipt (starts clock) ----
    em = event_bus.emit(actor_role, cid, "entitlement_matched",
                        {"schemes": schemes, "confidence": conf, "proof_trace": trace,
                         "facts_keys": sorted(facts.keys())},
                        pii_fields=pii_fields)
    ep = event_bus.emit(actor_role, cid, "entitlement_petition_issued",
                        {"schemes": schemes, "confidence": conf,
                         "receipt_id": f"HR-{cid}", "sla_kind": "petition"},
                        pii_fields=None)  # pii already stored on the matched event's blob
    return {"decision": "matched", "case_id": cid, "schemes": schemes, "confidence": conf,
            "events": [em, ep]}

# ---------------- reference matcher: STAND-IN to prove the contract; NOT your rules ----------------
# Replace by binding match_fn = engine.rules.match (wrapped to this dict shape). This exists so the
# pipeline is provable while your legacy source is unavailable. It encodes 3 toy rules + 2 abstain paths.
_REF_RULES = [
    ("old_age_pension_nsap", lambda f: f.get("age", 0) >= 60),
    ("widow_pension_nsap",   lambda f: bool(f.get("is_widow"))),
    ("pmay_gramin",          lambda f: f.get("has_pucca_house") is False),
]
def reference_match_fn(facts):
    # path that RAISES -> abstain(brain_error)
    if facts.get("_boom"):
        raise RuntimeError("simulated brain crash")
    fired = [(rid) for rid, pred in _REF_RULES if pred(facts)]
    # path that is UNSURE (no rule fired and caller flagged ambiguity) -> abstain(low_conf)
    if not fired and facts.get("_ambiguous"):
        return {"confidence": 0.30, "schemes": [], "trace": []}
    conf = 0.95 if fired else 0.0
    trace = [{"rule_id": rid, "matched": True} for rid in fired]
    return {"confidence": conf, "schemes": fired, "trace": trace}
