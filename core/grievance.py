"""Civic grievance intake — orchestrator LOGIC on the unified SQLite-WAL bedrock.

Ports box/orchestrator.py split/route/docs/next-question/consent/intake case shape.
Clock hours, desk, and contact come from rulepack/routes/*.yaml (harvested rows),
never from a running legacy FastAPI. Civic cases are civic_intake events.
"""
import hashlib
import re
import time
from datetime import datetime, timedelta

from core import event_bus, outbox
from core.rule_engine import _catalog
from core.sla_clock import DEFAULT_HOURS, ISSUE_CLOCKS

# intent substring groups -> (scheme_id in routes YAML, route letter).
# Distinctive tokens so "handpump kharab" is water, not crop (kharab alone is not crop).
_INTENT_TABLE = [
    (("handpump", "paani", "borewell", "pipe", "jal ", " jal", "water"),
     "water_supply", "C"),
    (("streetlight", "street light", "gali bulb", "bulb", "lamp", "saubhagya"),
     "streetlight", "C"),
    (("sadak", "road", "kichad"), "road_repair", "C"),
    (("drain", "naali", "sewage", "ganda paani"), "drainage", "C"),
    (("garbage", "kachra"), "garbage", "C"),
    (("pollution",), "pollution", "C"),
    (("pmfby", "fasal", "crop"), "crop_loss", "A"),
    (("mgnrega", "nrega", "majdoori", "wage", "kaam", "rozgar"), "wage_work", "B"),
]

# SLA clock category keys (protected ISSUE_CLOCKS) for tracking; YAML hours still on the case.
_SLA_CATEGORY = {
    "water_supply": "handpump",
    "streetlight": "streetlight",
    "road_repair": "road",
    "drainage": "drain",
    "garbage": "garbage",
    "pollution": "general",
    "crop_loss": "general",
    "wage_work": "general",
}

DOCS = {
    "A": ["Aadhaar", "bank passbook", "land record (khasra/khuni)"],
    "B": ["Aadhaar", "bank passbook", "ration card / income certificate as applicable"],
    "C": ["none — facilitator logs location + photo evidence"],
    "D": ["none — identity protected; escalation reference only"],
    "HUMAN": ["facilitator will ask one clarifying question"],
}
REQUIRED = {"A": ["insured", "crop", "event_when"], "B": [], "C": [], "D": [], "HUMAN": []}
_ASK = {
    "insured": "Kya aap PMFBY ke tahat beema karwaya tha? (Insured under PMFBY?)",
    "crop": "Kaunsi fasal thi? (Which crop?)",
    "event_when": "Nuksaan kab hua — aaj ya kal? (When did the loss happen?)",
}
CONSENTS = ("named", "ward_only", "anonymous")
LABEL = "Facilitator guidance. Final decision by competent authority."
NEVER_DENY = "Automated denial precluded by construction (Sec 3)."
HUMAN_QUEUE = ("HUMAN", 48, "facilitator review")

# Strong scheme facts only. is_woman is omitted: extractor 'stree' matches inside 'streetlight'.
_ENTITLEMENT_FACTS = {
    "age", "annual_income_inr", "is_widow", "is_disabled",
    "has_pucca_house", "is_farmer", "is_sc_st", "is_bpl",
    "has_school_child", "has_land", "is_pregnant_or_lactating", "is_student",
    "is_girl_child", "is_single_woman",
}


def normalize_consent(raw):
    s = (raw or "named").strip().lower()
    return s if s in CONSENTS else "named"


def extract_slots(text):
    t = (text or "").lower()
    slots = {}
    m = re.search(r"(\d+)\s*(mahine|month|mahina)", t)
    if m:
        slots["months_unpaid"] = int(m.group(1))
    m = re.search(r"(\d+)\s*(din|day)", t)
    if m:
        slots["days_pending"] = int(m.group(1))
    if re.search(r"(gehu|wheat|rice|dhan|bajra|kharif|rabi|fasal|crop)", t):
        slots["crop"] = True
    if re.search(r"(insured|pmfby|bima|haan|i am|yes)", t) and not re.search(r"(nahi|no|not|uninsured)", t):
        slots["insured"] = True
    if re.search(r"(nahi|no|not|uninsured|bima nahi)", t) and re.search(r"(insured|pmfby|bima)", t):
        slots["insured"] = False
    if re.search(r"(aaj|today)", t):
        slots["event_when"] = "today"
    if re.search(r"(kal|yesterday|last night|raat)", t):
        slots["event_when"] = "yesterday"
    return slots


def next_question(route, slots):
    for f in REQUIRED.get(route, []):
        if f not in (slots or {}):
            return {"field": f, "ask": _ASK.get(f, f"Please confirm: {f}")}
    return None


def _yaml_meta(scheme_id):
    rows, _ = _catalog()
    for r in rows:
        if r.get("scheme_id") == scheme_id:
            return {
                "clock_hours": r.get("clock_hours"),
                "desk": r.get("desk") or "",
                "contact": r.get("contact"),
                "documents": list(r.get("documents") or []),
            }
    return {}


def detect_intents(text):
    """Return civic intents for an utterance. Empty text / no keywords -> []."""
    s = " " + (text or "").strip().lower() + " "
    if not (text or "").strip():
        return []
    out, seen = [], set()
    for keys, scheme_id, route in _INTENT_TABLE:
        if any(k in s or k in (text or "").lower() for k in keys):
            if scheme_id in seen:
                continue
            seen.add(scheme_id)
            out.append({"intent": scheme_id, "scheme_id": scheme_id, "route": route,
                        "confidence": 0.85, "abstain": False})
    return out


def route_for(intent):
    s = (intent or "").lower()
    for keys, scheme_id, route in _INTENT_TABLE:
        if s == scheme_id or any(k.strip() in s for k in keys if k.strip()):
            meta = _yaml_meta(scheme_id)
            hours = meta.get("clock_hours")
            desk = meta.get("desk") or ""
            if hours is None:
                hours = ISSUE_CLOCKS.get(_SLA_CATEGORY.get(scheme_id, "general"), DEFAULT_HOURS)
            return route, int(hours), desk, meta.get("contact"), scheme_id
    h, d = HUMAN_QUEUE[1], HUMAN_QUEUE[2]
    return HUMAN_QUEUE[0], h, d, None, None


def is_entitlement_facts(facts):
    facts = facts or {}
    return any(k in facts for k in _ENTITLEMENT_FACTS)


def classify_utterance(text, facts=None):
    """Decide civic / entitlement / split / abstain. Conflicting overlapping civic+unsure stays split-or-civic."""
    intents = detect_intents(text)
    facts = facts or {}
    empty = not (text or "").strip()
    if empty:
        return "abstain", []
    if intents and is_entitlement_facts(facts):
        return "split", intents
    if intents:
        return "civic", intents
    if is_entitlement_facts(facts):
        return "entitlement", []
    return "abstain", []


def _new_cid(intent, n):
    h = hashlib.sha256(f"{intent}-{time.time()}-{n}".encode()).hexdigest()[:6].upper()
    return f"HS-{time.strftime('%Y%m%d')}-{h}"


def open_case(intent_rec, text, consent="named", actor_role="mitra", pii_fields=None,
              extra_payload=None, case_id=None):
    """Open one civic_intake on the unified ledger. PII via vault only."""
    if not event_bus.is_ready():
        event_bus.init()
    consent = normalize_consent(consent)
    intent = intent_rec.get("intent") or intent_rec.get("scheme_id") or "other"
    route, clock, desk, contact, scheme_id = route_for(intent)
    if intent_rec.get("route"):
        route = intent_rec["route"]
    meta = _yaml_meta(scheme_id or intent)
    if meta.get("clock_hours") is not None:
        clock = int(meta["clock_hours"])
    if meta.get("desk"):
        desk = meta["desk"]
    if meta.get("contact") is not None:
        contact = meta["contact"]
    slots = extract_slots(text)
    nq = next_question(route, slots)
    docs = meta.get("documents") or DOCS.get(route, DOCS["HUMAN"])
    deadline = (datetime.now() + timedelta(hours=clock)).isoformat(timespec="minutes")
    cid = case_id or _new_cid(intent, 1)
    cat = _SLA_CATEGORY.get(scheme_id or intent, "general")
    payload = {
        "category": cat,
        "intent": intent,
        "scheme_id": scheme_id or intent,
        "route": route,
        "clock_hours": clock,
        "desk": desk,
        "contact": contact,
        "consent": consent,
        "documents": docs,
    }
    if extra_payload:
        for k in ("ward", "photo_hash", "byte_length", "gps"):
            if extra_payload.get(k) is not None:
                payload[k] = extra_payload[k]
    pii = None if consent == "anonymous" else pii_fields
    ev = event_bus.emit(actor_role, cid, "civic_intake", payload, pii_fields=pii)
    case = {
        "case_id": cid,
        "intent": intent,
        "route": route,
        "clock_hours": clock,
        "deadline": deadline,
        "owner_desk": desk,
        "contact": contact,
        "confidence": round(float(intent_rec.get("confidence") or 0.85), 3),
        "abstain": bool(intent_rec.get("abstain", False)),
        "documents": docs,
        "next_question": nq,
        "ledger_hash": ev.get("payload_hash") or ev.get("signature"),
        "seq": ev.get("seq"),
        "consent": consent,
        "label": LABEL,
        "never_deny": NEVER_DENY,
        "category": cat,
        "scheme_id": scheme_id or intent,
    }
    return case, ev


def intake(text, consent="named", actor_role="mitra", pii_fields=None, extra_payload=None,
           block_url=None):
    """Orchestrator intake() shape on the unified ledger. Never stores transcript."""
    consent = normalize_consent(consent)
    text = (text or "").strip()
    if not text:
        return {"error": "no speech", "decision": "abstained", "cases": [], "n_issues": 0,
                "never_deny": NEVER_DENY}
    intents = detect_intents(text)
    slots = extract_slots(text)
    if not intents:
        return {"decision": "abstained", "cases": [], "n_issues": 0, "slots": slots,
                "consent": consent, "never_deny": NEVER_DENY,
                "reason": "low_confidence_or_unsure"}
    cases = []
    for i, rec in enumerate(intents):
        case, ev = open_case(rec, text, consent=consent, actor_role=actor_role,
                             pii_fields=pii_fields if i == 0 else None,
                             extra_payload=extra_payload)
        cases.append(case)
        if block_url:
            outbox.enqueue(f"DEL-{case['case_id']}", block_url,
                           {"kind": "civic", "case_id": case["case_id"],
                            "category": case["category"], "ward": (extra_payload or {}).get("ward"),
                            "photo_hash": (extra_payload or {}).get("photo_hash")})
    return {"decision": "civic", "n_issues": len(cases), "cases": cases, "slots": slots,
            "consent": consent, "never_deny": NEVER_DENY, "case_id": cases[0]["case_id"]}
