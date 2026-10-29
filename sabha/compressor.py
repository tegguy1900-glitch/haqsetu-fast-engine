"""
Haq Setu - Sabha Compressor (Pillar 2, deterministic MVP, v2).
raw transcript [{speaker,text}] -> structured, ANONYMIZED minutes.
v2 fixes three classification bugs from v1:
  (1) a fund/approval sentence is a DECISION, never a grievance;
  (2) an official's dated promise is a COMMITMENT (action_item), recovered
      from the speaker ROLE (roles are safe; personal names are not stored);
  (3) grievances require COMPLAINT semantics, so promises/approvals stop
      polluting the civic-case Glue and the next-Sabha agenda.
Output keys are UNCHANGED so core/event_bus + sabha/push_sdm contracts hold.
NEVER copy a raw speaker label into any emitted field (Never Leak, layer 1).
"""
import re, time

PURPOSE_KW = ["drain","naali","sewage","road","sadak","streetlight","bijli","light",
              "handpump","nal","water","pani","sanitation","school","anganwadi","tap"]
DECISION_KW = ["approved","passes","passed","resolved","sanctioned","allocated",
               "manzoor","pasand","agree","consensus","unanimous","decided"]
APPROVE_CUES = ["approved","passed","resolved","sanctioned","allocated","manzoor",
                "pasand","unanimous","consensus"]
OWNER_KW = {"secretary":"secretary","sarpanch":"sarpanch","mitra":"mitra",
            "engineer":"engineer","panchayat":"panchayat","prdhan":"sarpanch",
            "patwari":"patwari","ashA":"ashaworker"}  # canonical roles only
CAT_KW = {"handpump":"handpump","nal":"handpump","pani":"water","water":"water",
          "drain":"drain","naali":"drain","sewage":"drain","streetlight":"streetlight",
          "light":"streetlight","bijli":"streetlight","road":"road","sadak":"road",
          "anganwadi":"anganwadi","school":"school","tap":"water"}
COMPLAINT_CUES = ["broken","not working","no water","dry","clog","jam","pothole",
                  "dangerous","unsafe","dirty","stink","smell","leak","overflow",
                  "delay","late","pending","fault","out of order","garbage","trash",
                  "mud","nahi aa","band hai","toota","sookha","gand","khatarnak",
                  "no light","not lit","since","has been"]
COMMIT_VERBS = ["fix","repair","arrange","provide","complete","finish","construct",
                "build","install","get it done","karwaunga","banwa"]
FIRSTPERSON = ["i will","we will","i shall","we shall","i'll","we'll",
               "main kar","hum kar","kar dunga","de dunga","karwaunga"]

_AMT = re.compile(r"(?:rs\.?|₹|inr|rupees?)\s*([\d][\d,]*)", re.I)
_WARD = re.compile(r"ward\s*(\d+)|(\d+)\s*(?:number\s*)?ward|no\.?\s*(\d+)\s*ward", re.I)
_DEADLINE = re.compile(r"\b(?:by|within)\b[^.]*|\b\d+\s*days?\b|\btomorrow\b|"
                       r"\bfriday\b|\bmonday\b|\bsaturday\b|kal|shukrawar|somwar", re.I)
_PHONE = re.compile(r"(?<!\d)[6-9]\d{9}(?!\d)")
_AADHAAR = re.compile(r"(?<!\d)\d{12}(?!\d)")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")

def _scrub(t):
    t = _PHONE.sub("[redacted]", t); t = _AADHAAR.sub("[redacted]", t)
    return _EMAIL.sub("[redacted]", t)

def _ward(seg):
    m = _WARD.search(seg)
    if not m: return None
    return int(next(g for g in m.groups() if g))

def _role_from(label):
    if not label: return None
    return OWNER_KW.get(str(label).strip().lower())   # None if it's a personal name

def compress(raw_segments, gp="GP-UNKNOWN", date=None):
    date = date or time.strftime("%Y-%m-%d")
    decisions, funds, actions, grievances = [], [], [], []
    for seg in raw_segments:
        if isinstance(seg, dict):
            text = seg.get("text", ""); speaker = seg.get("speaker")
        else:
            text, speaker = str(seg), None
        low = text.lower()
        has_amount = bool(_AMT.search(text))
        deadline = _DEADLINE.search(text)
        firstperson = any(k in low for k in FIRSTPERSON)
        commit_verb = any(k in low for k in COMMIT_VERBS)
        approve = any(k in low for k in APPROVE_CUES)
        decision_kw = any(k in low for k in DECISION_KW)
        complaint = any(k in low for k in COMPLAINT_CUES)
        owner_speaker = _role_from(speaker)
        owner_body = next((v for k, v in OWNER_KW.items() if k in low), None)

        # FUNDS: any rupee figure -> allocate to a purpose
        if has_amount:
            m = _AMT.search(text); amt = int(m.group(1).replace(",", ""))
            purpose = next((k for k in PURPOSE_KW if k in low), "general")
            funds.append({"amount": amt, "purpose": purpose})

        # DECISIONS: approval/resolution language (NOT a grievance)
        is_decision = (has_amount and approve) or decision_kw
        if is_decision:
            decisions.append(_scrub(text.strip()))

        # COMMITMENTS: a dated promise by an identifiable role -> action_item
        is_commitment = bool(deadline) and (firstperson or commit_verb) and (owner_speaker or owner_body)
        if is_commitment:
            owner = owner_body or owner_speaker          # prefer named executor
            actions.append({"owner": owner, "task": _scrub(text.strip()),
                            "deadline_raw": deadline.group(0).strip()})

        # GRIEVANCES: genuine complaints only -> feed the civic Glue
        is_grievance = complaint and not is_commitment and not is_decision
        if is_grievance:
            cat = next((v for k, v in CAT_KW.items() if k in low), None)
            if cat:
                grievances.append({"category": cat, "ward": _ward(text),
                                   "summary": _scrub(text.strip())})

    return {"gp": gp, "meeting_date": date, "segment_count": len(raw_segments),
            "decisions": decisions, "funds_mentioned": funds,
            "action_items": actions, "grievances": grievances,
            "agenda_next": [g["summary"] for g in grievances],
            "compressed_at": time.time()}

def llm_compress(raw_segments, gp="GP-UNKNOWN", date=None):  # pragma: no cover
    raise NotImplementedError("Swap in Bhashini/LLM summarizer here; return same shape.")
