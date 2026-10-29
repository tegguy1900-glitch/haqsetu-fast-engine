"""Bind literal triage/abstain.py (CONFIDENCE_THRESHOLD + triage_with_abstention).

Map ACCEPT / CONFIRM / ABSTAIN -> include / one-targeted-question / abstain-to-human.
Missing slots lower coverage and can force abstain; never fill a missing slot.
Pictogram menu is the safe abstain fallback. Never deny.
"""
from triage.abstain import CONFIDENCE_THRESHOLD, triage_with_abstention
from triage.baselines import pictogram_menu_baseline, keyword_baseline, HAS_SKLEARN, predict
from triage.slots import extract_slots

SLOT_NEED = {
    "pmfby": ["crop_name", "loss_percentage"],
    "crop_loss": ["crop_name", "loss_percentage"],
    "mgnrega": ["days_since_demand"],
    "wage_work": ["days_since_demand"],
}
_ASK = {
    "crop_name": "Kaunsi fasal thi? (Which crop?)",
    "loss_percentage": "Kitna nuksaan hua — percent? (What percent loss?)",
    "days_since_demand": "Kaam ki maang ko kitne din ho gaye? (Days since work demand?)",
}

ROUTE = {
    "ACCEPT": "include",
    "CONFIRM": "one-targeted-question",
    "ABSTAIN": "abstain-to-human",
}


def _missing_for(labels, slots):
    need, seen = [], set()
    for lab in labels or []:
        for k in SLOT_NEED.get(lab, []):
            if k not in seen:
                seen.add(k); need.append(k)
    return [k for k in need if slots.get(k) in (None, "", [])], need


def bind(text):
    """Run the FILE's triage_with_abstention, then coverage/confirm mapping. Never guess slots."""
    raw = triage_with_abstention(text)
    action = raw.get("action") or "ABSTAIN"
    slots = raw.get("slots") if isinstance(raw.get("slots"), dict) else extract_slots(text)
    labels = list(raw.get("labels") or (raw.get("intent") or {}).get("labels") or [])
    conf = float(raw.get("confidence") or 0.0)
    missing, need = _missing_for(labels, slots)
    coverage = 1.0 if not need else round((len(need) - len(missing)) / float(len(need)), 3)

    # Missing slots lower coverage and can force CONFIRM or ABSTAIN. Never invent values.
    if action == "ACCEPT" and missing:
        if coverage < 0.5:
            action = "ABSTAIN"
            raw = dict(raw)
            raw["fallback_reason"] = "Missing slots; refusing to guess harder."
            raw["risk"] = "HIGH"
        else:
            action = "CONFIRM"
            raw = dict(raw)
            raw["risk"] = "MEDIUM"

    if action == "ACCEPT" and conf < CONFIDENCE_THRESHOLD:
        action = "ABSTAIN"

    routed = ROUTE.get(action, "abstain-to-human")
    nq = None
    if action == "CONFIRM" and missing:
        f = missing[0]
        nq = {"field": f, "ask": _ASK.get(f, f"Please confirm: {f}")}

    pic = None
    if action == "ABSTAIN":
        pic = pictogram_menu_baseline(text)
        routed = "abstain-to-human"

    return {
        "action": action,
        "routed": routed,
        "confidence": conf,
        "threshold": CONFIDENCE_THRESHOLD,
        "labels": labels,
        "slots": slots,
        "missing_slots": missing,
        "coverage": coverage,
        "next_question": nq,
        "pictogram": pic,
        "never_deny": True,
        "has_sklearn": HAS_SKLEARN,
        "raw": raw,
        "keyword": keyword_baseline(text),
    }


def decide_voice(text, engine_decision=None):
    """Seam for /voice: never override a confident engine include with a guess; never deny."""
    b = bind(text)
    if engine_decision == "matched":
        b["routed"] = "include"
        return b
    if b["action"] == "ABSTAIN":
        b["decision"] = "abstained"
    elif b["action"] == "CONFIRM":
        b["decision"] = "confirm"
    else:
        b["decision"] = "include"
    return b
