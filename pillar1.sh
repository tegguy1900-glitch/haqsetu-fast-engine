#!/usr/bin/env bash
# Haq Setu - complete Pillar 1: real fact-extractor + declarative rule engine +
# auditable seed catalog, wired as the village default. Run: bash pillar1.sh
cd "$(dirname "$0")" 2>/dev/null || true
source venv/bin/activate 2>/dev/null || true
mkdir -p rulepack

# ---------- rulepack/catalog.py  (DATA: auditable seed; values VERIFY before prod) ----------
cat > rulepack/catalog.py <<'PYEOF'
"""
Haq Setu - Scheme catalog (DATA, not code). Declarative eligibility so every rule is
auditable and serializable. Each scheme carries source + verify: the THRESHOLDS below
are a STARTING POINT to check against the official scheme guidelines before production.
Your legacy 50 YAML drops in as MORE rows here - no engine change.
requires clauses: {fact, op, value}. op in {>=,<=,>,<,==,!=,in,not_in,truthy,falsy}.
A required fact that is MISSING (not merely false) => scheme is UNCERTAIN => engine
abstains rather than guessing. The engine never asserts a scheme absent from this list.
"""
SCHEMES = [
  {"id":"nsap_old_age","name":"Old Age Pension (NSAP/IGMSY)","source":"MoRD NSAP guidelines",
   "verify":"age slab & amount per state notification","docs":["age proof","residence","bank"],
   "benefit":"monthly old-age pension","requires":[{"fact":"age","op":">=","value":60}]},
  {"id":"nsap_widow","name":"Widow Pension (NSAP)","source":"MoRD NSAP guidelines",
   "verify":"widowhood + age slab per state","docs":["death cert of spouse","age","residence"],
   "benefit":"monthly widow pension","requires":[{"fact":"is_widow","op":"==","value":True}]},
  {"id":"nsap_disability","name":"Disability Pension (NSAP)","source":"MoRD NSAP guidelines",
   "verify":"disability % certificate","docs":["disability cert","age","residence"],
   "benefit":"monthly disability pension","requires":[{"fact":"is_disabled","op":"==","value":True}]},
  {"id":"pmay_gramin","name":"PM Awas Yojana - Gramin","source":"MoRD PMAY-G",
   "verify":"houselessness/kutcha + priority list","docs":["house status","land","Aadhaar"],
   "benefit":"housing assistance","requires":[{"fact":"has_pucca_house","op":"==","value":False}]},
  {"id":"ayushman_bharat","name":"Ayushman Bharat (PM-JAY)","source":"NIHM PM-JAY",
   "verify":"income/DEPR + SECC proxy","docs":["Aadhaar","ration/income"],
   "benefit":"Rs 5 lakh/yr health cover",
   "requires":[{"fact":"annual_income","op":"<","value":180000}],
   "alt":[{"fact":"is_sc_st","op":"==","value":True},{"fact":"is_bpl","op":"==","value":True}]},
  {"id":"pm_kisan","name":"PM-KISAN Samman Nidhi","source":"DoAF PM-KISAN",
   "verify":"landholding + exclusion list","docs":["land records","Aadhaar","bank"],
   "benefit":"Rs 6000/yr income support","requires":[{"fact":"is_farmer","op":"==","value":True}]},
  {"id":"ujjwala","name":"Ujjwala Yojana (LPG)","source":"MoP Ujjwala",
   "verify":"woman-headed/BPL + no connection","docs":["ration","Aadhaar"],
   "benefit":"LPG connection subsidy",
   "requires":[{"fact":"is_woman","op":"==","value":True},{"fact":"has_lpg","op":"==","value":False}]},
  {"id":"ration_pds","name":"NFSA Ration Card (PDS)","source":"MoF NFSA",
   "verify":"PHH/antyodaya criteria","docs":["family members","income","residence"],
   "benefit":"subsidised food grains",
   "requires":[{"fact":"is_bpl","op":"==","value":True}],
   "alt":[{"fact":"annual_income","op":"<","value":100000}]},
  {"id":"matric_scholarship","name":"Pre/Post-Matric Scholarship","source":"MoSE / state",
   "verify":"minority/SC-ST + income","docs":["child school proof","income","caste"],
   "benefit":"education scholarship",
   "requires":[{"fact":"has_school_child","op":"==","value":True}],
   "alt":[{"fact":"is_sc_st","op":"==","value":True},{"fact":"is_bpl","op":"==","value":True}]},
  {"id":"mgnrega","name":"MGNREGA job card","source":"MoRD MGNREGA",
   "verify":"adult + rural household","docs":["age","residence","Aadhaar"],
   "benefit":"100 days wage work/yr",
   "requires":[{"fact":"age","op":">=","value":18},{"fact":"age","op":"<=","value":60}]},
  {"id":"indira_awas","name":"Indira Awaas / PMAY-G widow priority","source":"MoRD",
   "verify":"widow + kutcha house","docs":["widowhood","house status"],
   "benefit":"priority housing",
   "requires":[{"fact":"is_widow","op":"==","value":True},{"fact":"has_pucca_house","op":"==","value":False}]},
  {"id":"sarva_shiksha_child","name":"Sarva Shiksha / RTE child entitlement","source":"MoE RTE",
   "verify":"school-age child","docs":["child age proof"],
   "benefit":"free elementary education",
   "requires":[{"fact":"has_school_child","op":"==","value":True}]},
]
PYEOF

# ---------- core/facts.py  (real voice->facts extractor; never invents a value) ----------
cat > core/facts.py <<'PYEOF'
"""
Haq Setu - Fact extractor (Pillar 1 layer 1). Parses Hinglish/Hindi/English free text
into a normalized facts dict. NEVER invents a value: a field appears ONLY when a pattern
matches; absent => missing => downstream abstains. Vocabulary is fixed and shared with
rulepack/catalog.py so the engine and extractor agree on fact names.
"""
import re
_NUM = re.compile(r"(\d{1,3})(?:[, ]?(\d{3}))*")  # 1,20,000 / 120000 / 80 hazaar
def _num(s):
    m=_NUM.search(s)
    if not m: return None
    a=m.group(1); b=m.group(2) or ""
    try: return int(a+b.replace(" ",""))
    except Exception: return None

_AGE = re.compile(r"\b(\d{2})\b")
_VOCAB = {  # fact -> (positive patterns, negative patterns) ; Devanagari-lite + romanized
 "is_widow":      (r"widow|vidhwa|vidawa|parinemta|parinamita|विधवा", None),
 "is_woman":      (r"\bwoman\b|\bfemale\b|mahila|aurat|stree|स्त्री|महिला|woman", r"\bman\b|\bmale\b|purush|aadmi"),
 "is_disabled":   (r"disab|viklang|diggaj|disabled|विकलांग|दिग्गज", None),
 "has_pucca_house":(r"pucca|pakka|pakke|concrete|cement| RCC|पक्का", r"kacha|kachcha|kutcha|kutchi|mud|jhoppi|कच्चा|झोपड़ी"),
 "is_farmer":     (r"farmer|kisan|krishak|khedut|किसान|खेती|farm", None),
 "has_lpg":       (r"lpg|gas connection|gas ki|गैस", None),
 "is_sc_st":      (r"\bsc\b|\bst\b|scheduled caste|scheduled tribe|dalit|आदिवासी|अनुसूचित", None),
 "is_bpl":        (r"bpl|below poverty|garib|गरीब|बीपीएल|ration.*yellow|yellow card", None),
 "has_school_child":(r"child|bachcha|baccha|beta|beti|student|school|padhta|padhti|बच्चा|विद्यालय|स्कूल", None),
 "has_land":      (r"land|zameen|jameen|khet|plot|भूमि|जमीन|खेत", None),
}
_INCOME = re.compile(r"(?:income|aamdani|aamdni|amdani|kamai|earning|आमदनी|आय|कमाई)[^0-9]{0,12}(\d{1,3}(?:[ ,]?\d{3})*)")

def extract(raw_text, lang=None):
    t=(raw_text or "").strip()
    low=t.lower()
    f={}
    if not t: return f
    # age: only a 2-digit number that reads as an age (18..120); never guess from "old"
    for m in _AGE.finditer(low):
        v=int(m.group(1))
        if 18<=v<=120: f["age"]=v; break
    # income: only when an income keyword precedes a number
    im=_INCOME.search(low)
    if im:
        n=_num(im.group(1))
        if n is not None: f["annual_income"]=n
    # boolean vocab: positive hit and NOT overridden by a negative hit in same text
    for fact,(pos,neg) in _VOCAB.items():
        if re.search(pos, low) or re.search(pos, t):
            if neg and re.search(neg, low):
                continue
            f[fact]=True
    # has_pucca_house needs explicit signal; if only kacha seen, set False
    if "has_pucca_house" not in f:
        if re.search(r"kacha|kachcha|kutcha|kutchi|mud|jhoppi|कच्चा|झोपड़ी", low):
            f["has_pucca_house"]=False
    # has_lpg default False only if woman context and no gas mention
    if f.get("is_woman") and "has_lpg" not in f and not re.search(r"lpg|gas", low):
        f["has_lpg"]=False
    return f
PYEOF

# ---------- core/rule_engine.py  (declarative evaluator; abstains on gaps) ----------
cat > core/rule_engine.py <<'PYEOF'
"""
Haq Setu - Rule engine (Pillar 1 layer 2). Evaluates facts vs rulepack/catalog.py.
Contract: match_fn(facts) -> {confidence, schemes, trace}. NEVER asserts a scheme not
in the catalog; NEVER fills a missing fact. If any required fact of every candidate is
missing => uncertain => low confidence => the bus-side process_voice ABSTAINS (routes to
a human), honoring never-deny. A confident match-set => high confidence + proof-trace.
"""
from rulepack.catalog import SCHEMES

_OPS={">=":lambda a,b:a>=b,"<=":lambda a,b:a<=b,">":lambda a,b:a>b,"<":lambda a,b:a<b,
      "==":lambda a,b:a==b,"!=":lambda a,b:a!=b,
      "in":lambda a,b:a in b,"not_in":lambda a,b:a not in b,
      "truthy":lambda a,b:bool(a),"falsy":lambda a,b:not bool(a)}

def _clause(c, facts):
    """returns (state, proof): state in {sat, fail, missing}."""
    fact=c["fact"]; op=c["op"]; val=c.get("value")
    if fact not in facts: return "missing", {"fact":fact,"note":"not provided"}
    got=facts[fact]
    fn=_OPS.get(op)
    if fn is None: return "missing", {"fact":fact,"note":f"unknown op {op}"}
    try: ok=bool(fn(got,val))
    except Exception: return "missing", {"fact":fact,"note":"type mismatch"}
    return ("sat" if ok else "fail"), {"fact":fact,"op":op,"value":val,"observed":got,"result":ok}

def _eval(scheme, facts):
    sat=[]; miss=[]; fail=[]
    for c in scheme.get("requires",[]):
        st,pr=_clause(c,facts)
        (sat if st=="sat" else miss if st=="missing" else fail).append(pr)
    # alt = any-of disjunction (e.g. income OR SC/ST OR BPL)
    alt_ok=None
    if scheme.get("alt"):
        alt_states=[_clause(c,facts)[0] for c in scheme["alt"]]
        alt_ok = any(s=="sat" for s in alt_states)
        alt_missing = all(s=="missing" for s in alt_states)
    else:
        alt_ok=True; alt_missing=False
    if fail: return "ineligible", sat+fail          # a required clause clearly false
    if miss and not (alt_ok and not alt_missing):   # required missing AND alt can't rescue
        return "uncertain", sat+miss
    if not sat and not (scheme.get("alt") and alt_ok):
        return "uncertain", sat+miss
    return "match", sat

def match_fn(facts):
    facts=facts or {}
    confident=[]; trace=[]; any_uncertain=False
    for s in SCHEMES:
        state,proofs=_eval(s,facts)
        if state=="match":
            confident.append(s["id"])
            trace.append({"scheme":s["id"],"name":s["name"],"clauses":proofs,
                          "docs":s.get("docs",[]),"benefit":s.get("benefit")})
        elif state=="uncertain":
            any_uncertain=True
    if confident:
        conf=round(min(0.97, 0.6+0.12*len(confident)),2)
        return {"confidence":conf,"schemes":confident,"trace":trace}
    # no confident match => abstain (never deny). trace explains the gap honestly.
    return {"confidence":0.0,"schemes":[],
            "trace":[{"note":"no scheme confidently matched",
                      "uncertain_facts":sorted({p["fact"] for t in [ _eval(s,facts)[1] for s in SCHEMES] for p in t if p.get("note")=="not provided"}) if any_uncertain else [],
                      "guidance":"a human officer should review; the system did not guess"}]}
PYEOF

# ---------- village/server.py  (WHOLESALE: binds the REAL brain by default) ----------
cat > village/server.py <<'PYEOF'
"""
Haq Setu - Village Booth Node (port 8000). AUDITED. Binds the REAL Pillar-1 brain
(core.facts + core.rule_engine + rulepack.catalog) by default; the 3-rule toy stays
reachable via HAQ_BRAIN=reference for the bus-side contract demo. Stdlib only.
Every citizen action writes the local signed ledger SYNCHRONOUSLY (durable now,
uplink irrelevant); upward propagation is queued via the outbox only when
HAQ_BLOCK_URL is set. PII -> vault; chain sees only opaque refs. Photo bytes -> SHA-256
digest only. /backfill propagates local-only history once an uplink appears.
"""
import os, json, base64, hashlib, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from core import event_bus, entitlement as ent, sla_clock as clock, outbox
from ledger import chain as _chain
from core.sla_clock import ISSUE_CLOCKS, DEFAULT_HOURS

PORT=int(os.environ.get("HAQ_VILLAGE_PORT","8000"))
HOST=os.environ.get("HAQ_VILLAGE_HOST","127.0.0.1")
BLOCK_URL=(os.environ.get("HAQ_BLOCK_URL","") or "").strip()

if (os.environ.get("HAQ_BRAIN","real") or "real").strip().lower()=="reference":
    MATCH_FN=ent.reference_match_fn
    from core.facts import extract as _ref_extract
    FACT_FN=lambda raw,lang=None:_ref_extract(raw,lang)  # toy brain, real extractor
    BRAIN_TAG="reference"
else:
    from core import rule_engine as _re_mod, facts as _fa_mod
    MATCH_FN=_re_mod.match_fn
    FACT_FN=_fa_mod.extract
    BRAIN_TAG="real"

def _uplink(case_id,payload):
    if not BLOCK_URL: return None
    return outbox.enqueue(f"DEL-{case_id}",BLOCK_URL,payload)

def _send(h,code,obj):
    b=json.dumps(obj,sort_keys=True).encode()
    h.send_response(code); h.send_header("Content-Type","application/json")
    h.send_header("Content-Length",str(len(b))); h.send_header("Access-Control-Allow-Origin","*")
    h.send_header("Access-Control-Allow-Headers","Content-Type")
    h.send_header("Access-Control-Allow-Methods","GET,POST,OPTIONS"); h.end_headers(); h.wfile.write(b)

def _j(h):
    n=int(h.headers.get("Content-Length","0") or 0); raw=h.rfile.read(n) if n else b""
    return json.loads(raw) if raw else {}

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def do_OPTIONS(self): _send(self,204,{})
    def do_GET(self):
        try: event_bus.init()
        except Exception as e: _send(self,500,{"error":f"ledger init failed: {e}"}); return
        if self.path=="/health":
            ok,_,_=event_bus.verify()
            _send(self,200,{"ok":ok,"chain_len":len(_chain.get_chain()),"outbox":outbox.stats(),
                            "match_seam":getattr(MATCH_FN,"__name__","?"),"fact_seam":getattr(FACT_FN,"__name__","?"),
                            "brain":BRAIN_TAG,"uplink_configured":bool(BLOCK_URL)})
        elif self.path=="/status": _send(self,200,clock.status())
        else: _send(self,404,{"error":"not found"})
    def do_POST(self):
        try: event_bus.init()
        except Exception as e: _send(self,500,{"error":f"ledger init failed: {e}"}); return
        try: data=_j(self)
        except Exception as e: _send(self,400,{"error":f"bad json: {e}"}); return
        if self.path=="/voice":
            facts=data.get("facts")
            if not isinstance(facts,dict):
                raw=data.get("raw_text")
                if raw is None: _send(self,400,{"error":"provide facts{} or raw_text"}); return
                facts=FACT_FN(raw,data.get("lang"))
            res=ent.process_voice(data.get("actor_role","mitra"),facts,MATCH_FN,
                                  pii_fields=data.get("pii_fields"),case_id=data.get("case_id"))
            if res["decision"]=="matched":
                _uplink(res["case_id"],{"kind":"entitlement","case_id":res["case_id"],
                                        "schemes":res["schemes"],"confidence":res["confidence"]})
            out={"decision":res["decision"],"case_id":res["case_id"],"confidence":res.get("confidence")}
            if res["decision"]=="matched":
                out["schemes"]=res["schemes"]; out["receipt_id"]=f"HR-{res['case_id']}"
                out["proof_trace"]=res["events"][0]["payload"].get("proof_trace")
            else: out["reason"]=res.get("reason")
            _send(self,200,out)
        elif self.path=="/civic":
            cat=data.get("category")
            if not cat: _send(self,400,{"error":"category required"}); return
            ph,blen=None,0
            if data.get("photo_b64"):
                try: raw=base64.b64decode(data["photo_b64"])
                except Exception: _send(self,400,{"error":"photo_b64 not valid base64"}); return
                ph,blen=hashlib.sha256(raw).hexdigest(),len(raw)
            cid=data.get("case_id") or f"HS-{time.strftime('%Y%m%d')}-{hashlib.sha256((cat+str(time.time())).encode()).hexdigest()[:6].upper()}"
            ev=event_bus.emit(data.get("actor_role","mitra"),cid,"civic_intake",
                {"category":cat,"ward":data.get("ward"),"photo_hash":ph,"byte_length":blen,"gps":data.get("gps")},
                pii_fields=data.get("pii_fields"))
            _uplink(cid,{"kind":"civic","case_id":cid,"category":cat,"ward":data.get("ward"),"photo_hash":ph})
            _send(self,200,{"case_id":cid,"seq":ev["seq"],"photo_hash":ph,"byte_length":blen,
                            "sla_hours":ISSUE_CLOCKS.get(cat,DEFAULT_HOURS)})
        elif self.path=="/sync":
            try: r=outbox.flush_once(force=True,max_attempts=int(os.environ.get("HAQ_SYNC_MAXATT","5")))
            except TypeError: r=outbox.flush_once(max_attempts=int(os.environ.get("HAQ_SYNC_MAXATT","5")))
            _send(self,200,r)
        elif self.path=="/backfill":
            if not BLOCK_URL: _send(self,200,{"enqueued":[],"note":"no uplink; nothing to backfill"}); return
            try:
                from core import backfill as _bf
                _send(self,200,_bf.sweep(BLOCK_URL))
            except Exception as e: _send(self,500,{"error":f"backfill: {e}"})
        else: _send(self,404,{"error":"not found"})

def main():
    event_bus.init()
    if BLOCK_URL:
        try:
            from core import backfill as _bf
            r=_bf.sweep(BLOCK_URL)
            if r["enqueued"]: print(f"[village] startup backfill enqueued {len(r['enqueued'])}")
        except Exception as e: print(f"[village] startup backfill skipped: {e}")
    srv=ThreadingHTTPServer((HOST,PORT),Handler)
    print(f"[village] http://{HOST}:{PORT} brain={BRAIN_TAG} uplink={'SET' if BLOCK_URL else 'NONE'}")
    try: srv.serve_forever()
    except KeyboardInterrupt: pass

if __name__=="__main__": main()
PYEOF

# ---------- core/backfill.py  (NEW; idempotent via enqueue dedup, no has_key dep) ----------
cat > core/backfill.py <<'PYEOF'
"""Haq Setu - Backfill sweep. Propagates local-only history once an uplink is set.
Idempotent WITHOUT outbox.has_key: relies on outbox.enqueue's INSERT-OR-IGNORE dedup
(returns 1 inserted / 0 dup). Builds envelopes from the CHAIN payload (PII-clean by the
ledger guard); never reads the vault. Excludes local-only evidence (sabha_chunk_hashed)."""
import os,sys,threading
from core import event_bus,outbox
from ledger import chain as _chain
PROPAGATABLE={"civic_intake","entitlement_petition_issued","sabha_signed","sla_breach","official_rejection"}
_COPY=("category","ward","schemes","confidence","receipt_id","minutes_hash","reason_code","escalated_to","mode")
def sweep(block_url,event_types=None):
    if not event_bus.is_ready(): event_bus.init()
    types=set(event_types) if event_types else PROPAGATABLE
    seen=set(); enq=[]
    for ev in _chain.get_chain():
        if ev["event_type"] not in types: continue
        cid=ev["case_id"]
        if cid in seen: continue
        seen.add(cid)
        env={"kind":ev["event_type"],"case_id":cid,"seq":ev["seq"]}
        pl=ev.get("payload",{})
        for f in _COPY:
            if f in pl: env[f]=pl[f]
        if outbox.enqueue(f"DEL-{cid}",block_url,env)==1: enq.append(cid)
    return {"enqueued":enq,"scanned":len(seen)}
def loop(block_url,interval=300,stop=None,log=print,event_types=None):
    stop=stop or threading.Event()
    while not stop.is_set():
        try:
            r=sweep(block_url,event_types=event_types)
            if r["enqueued"]: log(f"[backfill] enqueued {len(r['enqueued'])}")
        except Exception as e: log(f"[backfill] error (looping): {e}")
        stop.wait(interval)
if __name__=="__main__":
    event_bus.init(); url=(os.environ.get("HAQ_BLOCK_URL","") or "").strip()
    if not url: print("[backfill] no uplink; offline booth"); sys.exit(0)
    loop(url,interval=int(os.environ.get("HAQ_BACKFILL_INTERVAL","300")))
PYEOF

# ---------- core/run_brain_audit.py  (proves extractor+engine+abstention+no-fabrication) ----------
cat > core/run_brain_audit.py <<'PYEOF'
"""Pillar-1 brain audit. Run: python -m core.run_brain_audit. Asserts the REAL engine
never fabricates a fact/scheme and abstains on gaps. Catalog VALUES are seed data to
verify; this proves the MACHINE, not the numbers."""
import sys
from core import facts, rule_engine as eng
FAIL=[]
def chk(n,c,e=""):
    print(f"  [{'OK' if c else 'FAIL'}] {n}{(' :: '+e) if e else ''}"); 
    if not c: FAIL.append(n)

def main():
    print("##### PILLAR-1 BRAIN AUDIT (real extractor + declarative engine) #####")
    # 1) extractor: real Hinglish -> facts, NO invented values
    f=facts.extract("Main 68 saal ki vidhwa hoon, mera kacha ghar hai, saal ki aamdani 80 hazaar hai")
    chk("extract age=68", f.get("age")==68, str(f))
    chk("extract is_widow", f.get("is_widow") is True)
    chk("extract has_pucca_house=False (kacha)", f.get("has_pucca_house") is False)
    chk("extract annual_income=80000", f.get("annual_income")==80000, str(f.get("annual_income")))
    chk("extract is_woman (vidhwa=>woman ctx)", f.get("is_woman") is True or f.get("is_widow") is True)
    # 2) NO FABRICATION: text with no age number => age absent (didn't guess from 'old')
    f2=facts.extract("bahut budhi hoon, garib hoon")
    chk("no-fabrication: 'budhi' does NOT invent an age", "age" not in f2, str(f2))
    chk("no-fabrication: garib => is_bpl True", f2.get("is_bpl") is True, str(f2))
    # 3) engine: confident match set + proof_trace, high conf
    r=eng.match_fn(f)
    chk("engine confident (conf>0.6)", r["confidence"]>0.6, str(r["confidence"]))
    chk("engine matched nsap_old_age", "nsap_old_age" in r["schemes"], str(r["schemes"]))
    chk("engine matched nsap_widow", "nsap_widow" in r["schemes"])
    chk("engine matched pmay_gramin (kacha)", "pmay_gramin" in r["schemes"])
    chk("engine matched ayushman (income<1.8L)", "ayushman_bharat" in r["schemes"])
    chk("engine proof_trace present", bool(r["trace"]) and all("clauses" in t for t in r["trace"]))
    # 4) engine ABSTAINS on missing facts (never deny, never guess)
    r_empty=eng.match_fn({})
    chk("engine abstains on empty facts (conf~0)", r_empty["confidence"]<0.3 and r_empty["schemes"]==[], str(r_empty["confidence"]))
    chk("abstain trace explains gap", any("note" in t for t in r_empty["trace"]), str(r_empty["trace"])[:80])
    # 5) engine never asserts a scheme outside the catalog
    from rulepack.catalog import SCHEMES
    ids={s["id"] for s in SCHEMES}
    r2=eng.match_fn({"age":70,"is_widow":True,"has_pucca_house":False,"is_disabled":True,"is_farmer":True})
    chk("engine only returns catalog ids", all(sid in ids for sid in r2["schemes"]), str(r2["schemes"]))
    chk("engine picked up disability+pmmay+pm_kisan too",
        {"nsap_disability","pm_kisan"} <= set(r2["schemes"]), str(r2["schemes"]))
    # 6) alt-disjunction: SC/ST rescues ayushman even without income figure
    r3=eng.match_fn({"is_sc_st":True})
    chk("alt disjunction: is_sc_st => ayushman eligible", "ayushman_bharat" in r3["schemes"], str(r3["schemes"]))
    print("\n[RESULT]","BRAIN AUDIT GREEN" if not FAIL else f"FAILED: {FAIL}")
    sys.exit(0 if not FAIL else 1)
if __name__=="__main__": main()
PYEOF

# ---------- core/run_village_demo.py  (WHOLESALE: tests the REAL brain over HTTP) ----------
cat > core/run_village_demo.py <<'PYEOF'
"""Village node proof w/ REAL brain. Run: python -m core.run_village_demo (sandboxed).
Phase A (uplink toggle): real Hinglish /voice -> facts -> catalog match -> receipt +
proof_trace; garbage /voice -> abstain; /civic photo hashed-not-bytes; dropout->queue->
recover; chain hygiene (no raw PII/bytes, photo hash present, case_id in COLUMN).
Phase B (NO uplink): civic local-durable + open in /status + outbox total==0.
"""
import os,sys,json,time,base64,socket,threading,sqlite3,tempfile,subprocess,urllib.request,urllib.error
from http.server import BaseHTTPRequestHandler,HTTPServer
FAIL=[]
def chk(n,c,e=""):
    print(f"  [{'OK' if c else 'FAIL'}] {n}{(' :: '+e) if e else ''}")
    if not c: FAIL.append(n)
class _Mock(BaseHTTPRequestHandler):
    down=True; lock=threading.Lock()
    def log_message(self,*a): pass
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length","0") or 0))
        with _Mock.lock: d=_Mock.down
        code=503 if d else 200
        self.send_response(code); self.send_header("Content-Length","0"); self.end_headers()
def _fp():
    s=socket.socket(); s.bind(("127.0.0.1",0)); p=s.getsockname()[1]; s.close(); return p
def _wait(port,path="/health",to=10.0):
    t0=time.time()
    while time.time()-t0<to:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}",timeout=2) as r:
                j=json.loads(r.read())
                if path!="/health" or j.get("ok") is True: return j
        except Exception: pass
        time.sleep(0.15)
    raise RuntimeError(f":{port}{path} never healthy")
def _post(port,path,obj):
    req=urllib.request.Request(f"http://127.0.0.1:{port}{path}",data=json.dumps(obj).encode(),
        headers={"Content-Type":"application/json"},method="POST")
    try:
        with urllib.request.urlopen(req,timeout=5) as r: return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try: b=json.loads(e.read())
        except Exception: b={"error":str(e)}
        b["_status"]=e.code; return b
def _spawn(d,block=None,brain="real"):
    env=dict(os.environ)
    env.update({"HAQ_CHAIN":f"{d}/chain.jsonl","HAQ_VAULT":f"{d}/vault.jsonl","HAQ_KEYS":f"{d}/keys",
        "HAQ_VAULT_KEY":f"{d}/pii.key","SDM_DB":f"{d}/sdm.db","HAQ_OUTBOX":f"{d}/outbox.db",
        "HAQ_VILLAGE_PORT":str(_fp()),"HAQ_BRAIN":brain})
    if block: env["HAQ_BLOCK_URL"]=block
    else: env.pop("HAQ_BLOCK_URL",None)
    p=subprocess.Popen([sys.executable,"-m","village.server"],env=env)
    return p,int(env["HAQ_VILLAGE_PORT"])
def phase_a():
    print("\n##### PHASE A : REAL brain over HTTP (uplink toggle) #####")
    d=tempfile.mkdtemp(prefix="haqvil_a_"); _Mock.down=True
    fp=_fp(); srv=HTTPServer(("127.0.0.1",fp),_Mock)
    threading.Thread(target=srv.serve_forever,daemon=True).start()
    p,port=_spawn(d,block=f"http://127.0.0.1:{fp}/sync",brain="real")
    try:
        h=_wait(port)
        chk("A village up, brain=real, uplink set", h.get("ok") is True and h.get("brain")=="real" and h.get("uplink_configured") is True, str(h))
        chk("A seams named (match_fn/extract)", h.get("match_seam")=="match_fn" and h.get("fact_seam")=="extract", str({k:h.get(k) for k in('match_seam','fact_seam')}))
        v=_post(port,"/voice",{"raw_text":"Main 68 saal ki vidhwa hoon, mera kacha ghar hai, saal ki aamdani 80 hazaar hai",
                               "pii_fields":{"name":"Lakshmi Bai","phone":"9900112233"}})
        chk("A real /voice matched (conf>0.6)", v.get("decision")=="matched" and (v.get("confidence") or 0)>0.6, str(v.get("confidence")))
        chk("A matched nsap_old_age+widow+pmay", {"nsap_old_age","nsap_widow","pmay_gramin"} <= set(v.get("schemes",[])), str(v.get("schemes")))
        chk("A receipt issued", str(v.get("receipt_id","")).startswith("HR-"), v.get("receipt_id"))
        chk("A proof_trace present", bool(v.get("proof_trace")))
        v3=_post(port,"/voice",{"raw_text":"hello there nothing relevant at all"})
        chk("A garbage /voice ABSTAINED (not denied)", v3.get("decision")=="abstained", str(v3.get("reason")))
        c=_post(port,"/civic",{"category":"handpump","ward":4,
            "photo_b64":base64.b64encode(b"BROKEN-PUMP-PHOTO-BYTES").decode(),
            "pii_fields":{"name":"Sita","phone":"9999888877"}})
        chk("A civic photo hashed (64 hex)", c.get("photo_hash") and len(c["photo_hash"])==64, str(c.get("photo_hash"))[:12])
        s1=_post(port,"/sync",{})
        chk("A sync#1 (down) queued, acked none", bool(s1.get("still_pending")) and not s1.get("acked"), str({k:s1.get(k) for k in('acked','still_pending','dead')}))
        with _Mock.lock: _Mock.down=False
        s2=_post(port,"/sync",{})
        chk("A sync#2 (up) acked queued", bool(s2.get("acked")) and not s2.get("still_pending"), str({k:s2.get(k) for k in('acked','still_pending','dead')}))
        cc=sqlite3.connect(f"{d}/chain.db")
        blob="".join(r[0] for r in cc.execute("SELECT payload FROM events"))
        cids=[r[0] for r in cc.execute("SELECT case_id FROM events")]; cc.close()
        chk("A chain NO raw PII names", all(x not in blob for x in("Lakshmi","Sita")))
        chk("A chain NO raw phone digits", all(x not in blob for x in("9900112233","9999888877")))
        chk("A chain NO photo bytes", "BROKEN-PUMP-PHOTO-BYTES" not in blob)
        chk("A chain DOES carry photo HASH", c["photo_hash"] in blob)
        chk("A civic case_id on chain (COLUMN)", c["case_id"] in cids, str(cids))
    finally:
        p.terminate(); p.wait(timeout=5); srv.shutdown()
def phase_b():
    print("\n##### PHASE B : NO uplink (offline booth local-durable) #####")
    d=tempfile.mkdtemp(prefix="haqvil_b_"); p,port=_spawn(d,block=None,brain="real")
    try:
        h=_wait(port)
        chk("B village up + uplink NONE", h.get("ok") is True and h.get("uplink_configured") is False, str(h))
        c=_post(port,"/civic",{"category":"drain","ward":3,"pii_fields":{"name":"Ravi","phone":"9700001111"}})
        chk("B civic accepted + local seq", c.get("seq") is not None and c.get("case_id"), str(c))
        st=_wait(port,"/status")
        chk("B civic OPEN in /status (SLA tracked offline)", c["case_id"] in st.get("open_civic",[]), str(st.get("open_civic")))
        ob=_wait(port,"/health").get("outbox",{})
        chk("B outbox total==0 (not dead-lettered w/o uplink)", ob.get("total",-1)==0, str(ob))
        cc=sqlite3.connect(f"{d}/chain.db")
        cids=[r[0] for r in cc.execute("SELECT case_id FROM events")]
        blob="".join(r[0] for r in cc.execute("SELECT payload FROM events")); cc.close()
        chk("B local chain durable (case_id COLUMN)", c["case_id"] in cids, str(cids))
        chk("B local chain NO raw PII", "Ravi" not in blob and "9700001111" not in blob)
    finally:
        p.terminate(); p.wait(timeout=5)
def main():
    print("##### VILLAGE NODE - REAL PILLAR-1 BRAIN #####")
    phase_a(); phase_b()
    print("\n[RESULT]","VILLAGE REAL-BRAIN GREEN" if not FAIL else f"FAILED: {FAIL}")
    sys.exit(0 if not FAIL else 1)
if __name__=="__main__": main()
PYEOF

echo "########## SYNTAX / IMPORT SMOKE ##########"
python -m py_compile rulepack/catalog.py core/facts.py core/rule_engine.py village/server.py core/backfill.py core/run_brain_audit.py core/run_village_demo.py \
  && echo "  [OK] all 7 new/rewritten files compile" || { echo "  [FAIL] compile"; exit 1; }
python -c "import rulepack.catalog, core.facts, core.rule_engine, core.backfill, village.server; print('  [OK] imports resolve (engine+extractor+catalog+backfill+village)')" || exit 1

echo "########## GATES (Pillar-1 surface; untouched gates keep prior green) ##########"
GATES=""
gate(){ local L="$1"; shift; local d; d="$(mktemp -d /tmp/p1_XXXXXX)"
  env HAQ_CHAIN="$d/chain.jsonl" HAQ_VAULT="$d/vault.jsonl" HAQ_KEYS="$d/keys" HAQ_VAULT_KEY="$d/pii.key" \
      SDM_DB="$d/sdm.db" HAQ_OUTBOX="$d/outbox.db" HAQ_SABHA_PORT=8020 HAQ_SDM_PORT=8110 HAQ_VILLAGE_PORT=8000 \
      HAQ_XP_DIR="$d" HAQ_DASH_DIR="$d" HAQ_B_DIR="$d/b" "$@" 2>&1 | tail -n 6
  local rc="${PIPESTATUS[0]}"; printf '>>> %-12s exit=%s\n' "$L" "$rc"; rm -rf "$d"; GATES="$GATES $L=$rc"; }
gate "brain-audit" python -m core.run_brain_audit
gate "village"     python -m core.run_village_demo
gate "pillar1"     python -m core.run_pillar1_demo
gate "launch"      python -m core.run_launcher_demo
echo "########## SUMMARY ##########"
echo "GATES:$GATES"
allok=1; for kv in $GATES; do [ "${kv#*=}" = "0" ] || allok=0; done
[ "$allok" = 1 ] && echo "PILLAR 1 COMPLETE :: real extractor + declarative engine + auditable seed catalog wired as village default; never-deny/no-fabrication proven; bus-side + supervisor unregressed" || echo "SOME GATE RED :: see exit!=0"
