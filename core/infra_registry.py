"""
HaqSetu - Realistic Infrastructure Work‑Order Registry (declarative, pure stdlib).

Mirrors the scheme engine's philosophy: the catalogue of fault types, their
official geofence radii, SLA clocks, the enforced state machine, work‑order
number format, location‑based duplicate linking and the physical‑actuator
bridge are all DATA evaluated by generic helpers. Adding a fault type is a
config change, not a code change. No DB, no side effects in this module.

National/municipal lookups (WMS/tax‑jurisdiction, contractor deputation,
utility outage feeds) would need empanelment; they are out of scope here and
the workflow degrades honestly to officer review, exactly like the scheme
adapters.
"""
import time, re

YEAR = time.strftime("%Y")

SEVERITIES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
SEVERITY_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}

# base SLA hours by severity; per‑category overrides for genuinely urgent faults
SEVERITY_SLA = {"CRITICAL": 24, "HIGH": 48, "MEDIUM": 120, "LOW": 240}
CATEGORY_SLA = {"WATER": {"CRITICAL": 12, "HIGH": 24}}  # contaminated/no water is hours, not days

# code = 3‑letter work‑order token; geofence_m = how close a repair GPS must be
# to the complaint to count as "actually at the site"; keywords drive auto‑classify.
CATEGORIES = {
 "WATER":       {"label": "Water supply / handpump", "code": "WTR", "geofence_m": 30,
   "keywords": ["handpump","hand pump","pump","tap","nal","pipeline","pipe","leak","leaking","water","pani","jid","boring","toot","tuta","tuti","dry","no water"]},
 "DRAIN":       {"label": "Drainage / sewer", "code": "DRN", "geofence_m": 40,
   "keywords": ["drain","drainage","sewer","gutter","naali","naal","nalii","storm","overflow","stagnat","blocked","block","jam","clog","filth","kichad","mesh"]},
 "ROAD":        {"label": "Road / pavement", "code": "RD", "geofence_m": 80,
   "keywords": ["road","raasta","raasta","pothole","pit","crack","sink","sinking","damage","damaged","kharab","footpath","pavement","galta","gaddha"]},
 "STREETLIGHT": {"label": "Streetlight / power", "code": "STP", "geofence_m": 50,
   "keywords": ["light","streetlight","pole","bijli","power","dark","lamp","fuse","wire","current","blackout","andhera"]},
 "SANITATION":  {"label": "Sanitation / waste", "code": "SAN", "geofence_m": 50,
   "keywords": ["garbage","waste","trash","sweep","cleaning","toilet","shauchalaya","dust","kachra","litter","dump","odour","badbu"]},
 "OTHER":       {"label": "Other civic issue", "code": "OTH", "geofence_m": 60, "keywords": []},
}
CODE = {k: v["code"] for k, v in CATEGORIES.items()}
_CAT_ORDER = ["WATER", "DRAIN", "ROAD", "STREETLIGHT", "SANITATION", "OTHER"]

# enforced workflow. terminal states have no outgoing edges.
ALLOWED = {
 "open":                       ["assigned", "in_progress", "rejected"],
 "assigned":                   ["in_progress", "awaiting_otp", "rejected"],
 "in_progress":                ["awaiting_otp", "rejected"],
 "awaiting_otp":               ["closed", "reopened"],
 "reopened":                   ["assigned", "in_progress"],
 "closed":                     ["reopened"],
 "rejected":                   [],
}
TERMINAL = ("closed", "rejected")

# physical‑actuator bridge consumed later by the ESP32 (NOT wired in this fence)
HW_INTENT = {"WATER": "pump_lock", "DRAIN": "drain_block", "ROAD": "road_alert",
             "STREETLIGHT": "light_alert", "SANITATION": "sanitation_alert", "OTHER": "generic_alert"}

def classify(text):
    """Best‑effort fault category from free text (Hinglish/English). OTHER if no hit."""
    low = (text or "").lower()
    best, best_hits = "OTHER", 0
    for cat in _CAT_ORDER:
        hits = sum(1 for k in CATEGORIES[cat]["keywords"] if k and k in low)
        if hits > best_hits:
            best, best_hits = cat, hits
    return best

def geofence(cat):
    return CATEGORIES.get(cat, CATEGORIES["OTHER"])["geofence_m"]

def dup_radius(cat):
    return max(geofence(cat), 50)

def sla_for(cat, sev):
    return CATEGORY_SLA.get(cat, {}).get(sev, SEVERITY_SLA.get(sev, 120))

def allowed(frm, to):
    return to in ALLOWED.get(frm, [])

def is_terminal(st):
    return st in TERMINAL

def format_wo(cat, seq):
    return "WO/%s/%s/%05d" % (YEAR, CODE.get(cat, "OTH"), seq)

def hw_intent(cat):
    return HW_INTENT.get(cat, "generic_alert")

def label(cat):
    return CATEGORIES.get(cat, CATEGORIES["OTHER"])["label"]

if __name__ == "__main__":
    print("=== INFRA REGISTRY - HEADLESS DEMO (no DB) ===")
    for ph in ["mera handpump toot gaya hai","naali jam ho gayi paani khada hai",
               "sadak par bada gaddha hai","gali ka light nahi jal raha","kachra utha nahi ja raha",
               "kuch samajh nahi aa raha"]:
        print("  classify[%-34s] -> %s (%s)" % (ph[:34], classify(ph), label(classify(ph))))
    print("  SLA  WATER/CRITICAL =", sla_for("WATER","CRITICAL"), "h (override)")
    print("  SLA  ROAD/LOW       =", sla_for("ROAD","LOW"), "h")
    print("  geofence ROAD =", geofence("ROAD"), "m | dup_radius WATER =", dup_radius("WATER"), "m")
    print("  WO sample      =", format_wo("DRAIN", 7))
    print("  hw bridge      =", {c: hw_intent(c) for c in CATEGORIES})
    checks = [("open","assigned",True),("open","closed",False),("assigned","awaiting_otp",True),
              ("in_progress","awaiting_otp",True),("awaiting_otp","closed",True),
              ("awaiting_otp","reopened",True),("closed","reopened",False),("rejected","assigned",False),
              ("reopened","in_progress",True)]
    bad = [(f,t,e) for f,t,e in checks if allowed(f,t) != e]
    print("  state machine  =", "ALL %d TRANSITIONS CORRECT" % len(checks) if not bad else "MISMATCH %s" % bad)
    print("=== demo complete ===")
