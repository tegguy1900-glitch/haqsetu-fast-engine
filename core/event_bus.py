"""
Haq Setu - Event Bus.  The ONLY module pillars import to record anything.
Owns the event-type registry (no typos / no rogue types) and routes every
write through the unified ledger with the PII guard active.
v2: added 'commitment_fulfilled' (Pillar 2 owed-checklist close) and is_ready().
"""
from ledger import chain as _chain
from ledger import pii_store as _pii

EVENT_TYPES = {
    "entitlement_matched":        (1, False, "AI matched scheme(s) with proof trace"),
    "entitlement_abstained":      (1, False, "AI refused to guess; routed to human"),
    "entitlement_petition_issued":(1, True,  "Haq Receipt / RTPS petition generated"),
    "petition_resolved":          (1, False, "officer acted on a Haq Receipt (sanctioned/granted)"),
    "sabha_recording_started":    (2, False, "Mitra hit record"),
    "sabha_chunk_hashed":         (2, True,  "audio chunk hash locked"),
    "sabha_signed":               (2, True,  "Sarpanch signed compressed minutes"),
    "sabha_unsigned":             (2, False, "Sarpanch refused to sign (auditable)"),
    "sabha_pushed_sdm":           (2, False, "minutes delivered to block node"),
    "commitment_fulfilled":       (2, False, "owed-checklist item marked done by owner"),  # NEW
    "civic_intake":               (3, True,  "asset failure logged w/ photo+gps"),
    "civic_closure_attempt":      (3, True,  "officer tried to close"),
    "civic_closure_verified":     (3, True,  "photo-diff + OTP + gps passed"),
    "civic_closure_rejected":     (3, False, "evidence insufficient; clock continues"),
    "sla_breach":                 (3, False, "clock expired -> escalated (civic OR commitment)"),
    "ghost_audit_failed":         (3, False, "random re-verification failed"),
    "official_rejection":         (0, False, "human rejected WITH reason code"),
    "official_rejection_blocked": (0, False, "rejection without reason code -> blocked"),
}

_priv = _pub = None
def init():
    global _priv, _pub
    _priv, _pub = _chain.load_or_create_keys()
    ok, bad, why = _chain.verify_chain(_pub)
    if not ok:
        raise RuntimeError(f"Ledger integrity FAIL at seq {bad}: {why}")
    return ok

def is_ready():
    return _priv is not None

def emit(actor_role, case_id, event_type, payload, pii_fields=None):
    if event_type not in EVENT_TYPES:
        raise ValueError(f"Unknown event_type '{event_type}'. Register it first.")
    if pii_fields:
        blob_id = _pii.put_pii(case_id, pii_fields)
        payload = dict(payload)
        payload["pii_ref"] = blob_id
    return _chain.append_event(actor_role, case_id, event_type, payload, _priv)

def verify():
    if _pub is None: init()
    return _chain.verify_chain(_pub)

def tail(n=20):
    return _chain.get_chain()[-n:]
