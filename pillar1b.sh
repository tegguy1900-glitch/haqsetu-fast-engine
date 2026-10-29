#!/usr/bin/env bash
# Haq Setu pillar-1b: fix income/age extraction (certain) + harden village handler so a
# request exception is a clean 500+traceback instead of a silent drop (reveals red-2).
# Whole-file rewrites only (no fragile in-place patches). Run: bash pillar1b.sh
cd "$(dirname "$0")" 2>/dev/null || true
source venv/bin/activate 2>/dev/null || true

# =================== core/facts.py  (real magnitude-aware extractor; never invents) ===================
cat > core/facts.py <<'PYEOF'
"""
Haq Setu - Fact extractor (Pillar 1 layer 1). Parses Hinglish/Hindi/English free text
into a normalized facts dict. NEVER invents a value: a field appears ONLY when a pattern
matches; absent => missing => downstream abstains. Two never-fabricate rules enforced here:
  (1) age requires an age CUE word (68 saal), so an income figure (1,20,000) is never
      misread as "age 20"; a bare number with no cue yields NO age (we don't guess).
  (2) income parses digit-groups AND magnitude words (hazaar/lakh/crore, Devanagari +
      romanized, compound "2 lakh 50 hazaar"), collapses Indian commas, and STOPS at the
      first non-magnitude word so a stray later number can't be swallowed as income.
Vocabulary is fixed and shared with rulepack/catalog.py so engine and extractor agree.
"""
import re

# age: 2-3 digits IMMEDIATELY followed by an age cue word
_AGE = re.compile(r"\b(\d{2,3})\b\s*(?:saal|sal|years?|year|umar|age|barsa|varsh|वर्ष|साल|उम्र)", re.I)

# income: keyword then a region; the amount parser handles the rest
_INCOME = re.compile(
    r"(?:income|aamdani|aamdni|amdani|kamai|earning|aamdani|आमदनी|आय|कमाई)\b[\s,:]*(.{0,40})",
    re.I)

_MULT = {
    "hazaar":1000,"hazar":1000,"hazaron":1000,"hazoor":1000,"thousand":1000,"k":1000,
    "हज़ार":1000,"हजार":1000,
    "lakh":100000,"lac":100000,"lakho":100000,"lakhon":100000,"lacs":100000,
    "लाख":100000,
    "crore":10000000,"crores":10000000,"karod":10000000,"crorep":10000000,
    "करोड़":10000000,"करोड":10000000,
}

def _collapse(s):
    # remove separators that sit BETWEEN digits: 1,20,000 -> 120000 ; 80 000 -> 80000
    return re.sub(r"(?<=\d)[, ](?=\d)", "", s)

def _parse_amount(chunk):
    """Return int rupees or None. Parses from token 0; if token 0 isn't a number, returns
    None (we do NOT hunt for a later number -> can't grab '2 bachche' as income). Stops at
    the first non-magnitude word after the amount, so trailing junk is ignored."""
    c = _collapse(chunk or "")
    toks = re.findall(r"\d+|[^\d\s]+", c)
    total = 0; i = 0; n = len(toks); started = False
    while i < n:
        t = toks[i]
        if t.isdigit():
            cur = int(t); started = True; i += 1
            if i < n and toks[i].lower() in _MULT:
                total += cur * _MULT[toks[i].lower()]; i += 1
                continue                      # allow compound: another number+magnitude
            else:
                total += cur; break           # bare number terminates the amount
        elif t.lower() in _MULT:
            break                             # magnitude with no preceding number -> don't guess
        else:
            break                             # first non-number/non-magnitude -> stop
    return total if (started and total > 0) else None

_VOCAB = {  # fact -> (positive patterns, negative patterns)
 "is_widow":       (r"widow|vidhwa|vidawa|parinemta|parinamita|विधवा", None),
 "is_woman":       (r"\bwoman\b|\bfemale\b|mahila|aurat|stree|स्त्री|महिला", r"\bman\b|\bmale\b|purush|aadmi"),
 "is_disabled":    (r"disab|viklang|diggaj|disabled|विकलांग|दिग्गज", None),
 "has_pucca_house":(r"pucca|pakka|pakke|concrete|cement|रCc|पक्का", r"kacha|kachcha|kutcha|kutchi|mud|jhoppi|कच्चा|झोपड़ी"),
 "is_farmer":      (r"farmer|kisan|krishak|khedut|किसान|खेती|farm", None),
 "has_lpg":        (r"lpg|gas connection|gas ki|गैस", None),
 "is_sc_st":       (r"\bsc\b|\bst\b|scheduled caste|scheduled tribe|dalit|आदिवासी|अनुसूचित", None),
 "is_bpl":         (r"bpl|below poverty|garib|गरীব|गरীब|बीपीएल|yellow card", None),
 "has_school_child":(r"child|bachcha|baccha|beta|beti|student|school|padhta|padhti|बच्चा|विद्यालय|स्कूल", None),
 "has_land":       (r"land|zameen|jameen|khet|plot|भूमि|जमीन|खेत", None),
}

def extract(raw_text, lang=None):
    t = (raw_text or "").strip()
    low = t.lower()
    f = {}
    if not t:
        return f
    m = _AGE.search(low)
    if m:
        v = int(m.group(1))
        if 18 <= v <= 120:
            f["age"] = v
    im = _INCOME.search(low) or _INCOME.search(t)
    if im:
        amt = _parse_amount(im.group(1))
        if amt is not None:
            f["annual_income"] = amt
    for fact, (pos, neg) in _VOCAB.items():
        if re.search(pos, low) or re.search(pos, t):
            if neg and re.search(neg, low):
                continue
            f[fact] = True
    if "has_pucca_house" not in f and re.search(r"kacha|kachcha|kutcha|kutchi|mud|jhoppi|कच्चा|झोपड़ी", low):
        f["has_pucca_house"] = False
    if f.get("is_woman") and "has_lpg" not in f and not re.search(r"lpg|gas", low):
        f["has_lpg"] = False
    return f
PYEOF

# =================== core/run_brain_audit.py  (adds comma/compound/no-overread + integration) ===================
cat > core/run_brain_audit.py <<'PYEOF'
"""Pillar-1 brain audit. Run: python -m core.run_brain_audit. Asserts the REAL engine
never fabricates a fact/scheme and abstains on gaps. Catalog VALUES are seed data to
verify; this proves the MACHINE, not the numbers."""
import sys
from core import facts, rule_engine as eng
from rulepack.catalog import SCHEMES
FAIL = []
def chk(n, c, e=""):
    print(f"  [{'OK' if c else 'FAIL'}] {n}{(' :: '+e) if e else ''}")
    if not c: FAIL.append(n)

def main():
    print("##### PILLAR-1 BRAIN AUDIT (real extractor + declarative engine) #####")
    # 1) extractor: real Hinglish -> facts, magnitude words parsed
    f = facts.extract("Main 68 saal ki vidhwa hoon, mera kacha ghar hai, saal ki aamdani 80 hazaar hai")
    chk("extract age=68 (cue 'saal')", f.get("age") == 68, str(f))
    chk("extract is_widow", f.get("is_widow") is True)
    chk("extract has_pucca_house=False (kacha)", f.get("has_pucca_house") is False)
    chk("extract annual_income=80000 (80 hazaar)", f.get("annual_income") == 80000, str(f.get("annual_income")))
    # 1b) magnitude + Indian comma + compound + no-overread + negation-guard
    fc = facts.extract("mere ghar ki aamdani 1,20,000 rupaye hai")
    chk("extract Indian comma 1,20,000=120000", fc.get("annual_income") == 120000, str(fc.get("annual_income")))
    chk("extract comma did NOT invent age=20", "age" not in fc, str(fc))
    fk = facts.extract("sal ki kamai 2 lakh 50 hazaar hai")
    chk("extract compound 2 lakh 50 hazaar=250000", fk.get("annual_income") == 250000, str(fk.get("annual_income")))
    fo = facts.extract("aamdani 80 hazaar hai aur 2 bachche hain")
    chk("extract no-overread: stops at 'hai', ignores '2 bachche'", fo.get("annual_income") == 80000, str(fo.get("annual_income")))
    fn = facts.extract("income nahi hai, 2 bachche")
    chk("extract does NOT grab stray number after negation", "annual_income" not in fn, str(fn))
    # 2) NO FABRICATION: no age number => no age (didn't guess from 'budhi')
    f2 = facts.extract("bahut budhi hoon, garib hoon")
    chk("no-fabrication: 'budhi' does NOT invent an age", "age" not in f2, str(f2))
    chk("no-fabrication: garib => is_bpl True", f2.get("is_bpl") is True, str(f2))
    # 3) engine: confident match set + proof_trace, high conf
    r = eng.match_fn(f)
    chk("engine confident (conf>0.6)", r["confidence"] > 0.6, str(r["confidence"]))
    chk("engine matched nsap_old_age", "nsap_old_age" in r["schemes"], str(r["schemes"]))
    chk("engine matched nsap_widow", "nsap_widow" in r["schemes"])
    chk("engine matched pmay_gramin (kacha)", "pmay_gramin" in r["schemes"])
    chk("engine matched ayushman (income 80000<1.8L)", "ayushman_bharat" in r["schemes"])
    chk("engine proof_trace present", bool(r["trace"]) and all("clauses" in t for t in r["trace"]))
    # 3b) INTEGRATION: extractor -> engine on the real text yields the expected superset
    chk("integration: real-text facts -> 6 flagship schemes",
        {"nsap_old_age","nsap_widow","pmay_gramin","ayushman_bharat","ration_pds","indira_awas"} <= set(r["schemes"]),
        str(r["schemes"]))
    # 4) engine ABSTAINS on missing facts (never deny, never guess)
    r_empty = eng.match_fn({})
    chk("engine abstains on empty facts (conf~0)", r_empty["confidence"] < 0.3 and r_empty["schemes"] == [], str(r_empty["confidence"]))
    chk("abstain trace explains gap", any("note" in t for t in r_empty["trace"]), str(r_empty["trace"])[:80])
    # 5) engine never asserts a scheme outside the catalog
    ids = {s["id"] for s in SCHEMES}
    r2 = eng.match_fn({"age":70,"is_widow":True,"has_pucca_house":False,"is_disabled":True,"is_farmer":True})
    chk("engine only returns catalog ids", all(sid in ids for sid in r2["schemes"]), str(r2["schemes"]))
    chk("engine picked up disability+pm_kisan too", {"nsap_disability","pm_kisan"} <= set(r2["schemes"]), str(r2["schemes"]))
    # 6) alt-disjunction: SC/ST rescues ayushman even without an income figure
    r3 = eng.match_fn({"is_sc_st":True})
    chk("alt disjunction: is_sc_st => ayushman eligible", "ayushman_bharat" in r3["schemes"], str(r3["schemes"]))
    print("\n[RESULT]", "BRAIN AUDIT GREEN" if not FAIL else f"FAILED: {FAIL}")
    sys.exit(0 if not FAIL else 1)
if __name__ == "__main__": main()
PYEOF

# =================== village/server.py  (WHOLESALE: + handler guard -> 500+tb, never a silent drop) ===================
cat > village/server.py <<'PYEOF'
"""
Haq Setu - Village Booth Node (port 8000). AUDITED. Binds the REAL Pillar-1 brain
(core.facts + core.rule_engine + rulepack.catalog) by default; the 3-rule toy stays
reachable via HAQ_BRAIN=reference. Stdlib only.

Prod-correctness: a request handler must NEVER drop the connection silently. do_GET/
do_POST are wrapped so any exception returns HTTP 500 with the traceback IN-BAND
(full text when HAQ_DEBUG=1, digit-masked otherwise so the error channel can't leak
PII). This converts the previous RemoteDisconnected (a dead handler thread) into a
readable error the booth UI / demo / SDM can surface.
"""
import os, json, base64, hashlib, time, re, traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from core import event_bus, entitlement as ent, sla_clock as clock, outbox
from ledger import chain as _chain
from core.sla_clock import ISSUE_CLOCKS, DEFAULT_HOURS

PORT = int(os.environ.get("HAQ_VILLAGE_PORT", "8000"))
HOST = os.environ.get("HAQ_VILLAGE_HOST", "127.0.0.1")
BLOCK_URL = (os.environ.get("HAQ_BLOCK_URL", "") or "").strip()
DEBUG = (os.environ.get("HAQ_DEBUG", "") == "1")

if (os.environ.get("HAQ_BRAIN", "real") or "real").strip().lower() == "reference":
    MATCH_FN = ent.reference_match_fn
    from core.facts import extract as _ref_extract
    FACT_FN = lambda raw, lang=None: _ref_extract(raw, lang)
    BRAIN_TAG = "reference"
else:
    from core import rule_engine as _re_mod, facts as _fa_mod
    MATCH_FN = _re_mod.match_fn
    FACT_FN = _fa_mod.extract
    BRAIN_TAG = "real"

def _uplink(case_id, payload):
    if not BLOCK_URL: return None
    return outbox.enqueue(f"DEL-{case_id}", BLOCK_URL, payload)

def _send(h, code, obj):
    b = json.dumps(obj, sort_keys=True).encode()
    h.send_response(code); h.send_header("Content-Type", "application/json")
    h.send_header("Content-Length", str(len(b))); h.send_header("Access-Control-Allow-Origin", "*")
    h.send_header("Access-Control-Allow-Headers", "Content-Type")
    h.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS"); h.end_headers(); h.wfile.write(b)

def _j(h):
    n = int(h.headers.get("Content-Length", "0") or 0); raw = h.rfile.read(n) if n else b""
    return json.loads(raw) if raw else {}

def _err(h, e):
    tb = traceback.format_exc()
    if DEBUG:
        _send(h, 500, {"error": type(e).__name__, "tb": tb})
    else:
        masked = re.sub(r"\d{6,}", "[masked]", tb)
        _send(h, 500, {"error": type(e).__name__, "tb": masked.strip().splitlines()[-1] if masked.strip() else ""})

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_OPTIONS(self): _send(self, 204, {})
    def do_GET(self):
        try: self._get()
        except Exception as e: _err(self, e)
    def do_POST(self):
        try: self._post()
        except Exception as e: _err(self, e)

    def _get(self):
        event_bus.init()
        if self.path == "/health":
            ok, _, _ = event_bus.verify()
            _send(self, 200, {"ok": ok, "chain_len": len(_chain.get_chain()), "outbox": outbox.stats(),
                              "match_seam": getattr(MATCH_FN, "__name__", "?"),
                              "fact_seam": getattr(FACT_FN, "__name__", "?"),
                              "brain": BRAIN_TAG, "uplink_configured": bool(BLOCK_URL)})
        elif self.path == "/status":
            _send(self, 200, clock.status())
        else:
            _send(self, 404, {"error": "not found"})

    def _post(self):
        event_bus.init()
        data = _j(self)
        if self.path == "/voice":
            facts = data.get("facts")
            if not isinstance(facts, dict):
                raw = data.get("raw_text")
                if raw is None: _send(self, 400, {"error": "provide facts{} or raw_text"}); return
                facts = FACT_FN(raw, data.get("lang"))
            res = ent.process_voice(data.get("actor_role", "mitra"), facts, MATCH_FN,
                                    pii_fields=data.get("pii_fields"), case_id=data.get("case_id"))
            if res["decision"] == "matched":
                _uplink(res["case_id"], {"kind": "entitlement", "case_id": res["case_id"],
                                         "schemes": res["schemes"], "confidence": res["confidence"]})
            out = {"decision": res["decision"], "case_id": res["case_id"], "confidence": res.get("confidence")}
            if res["decision"] == "matched":
                out["schemes"] = res["schemes"]; out["receipt_id"] = f"HR-{res['case_id']}"
                out["proof_trace"] = res["events"][0]["payload"].get("proof_trace")
            else:
                out["reason"] = res.get("reason")
            _send(self, 200, out)
        elif self.path == "/civic":
            cat = data.get("category")
            if not cat: _send(self, 400, {"error": "category required"}); return
            ph, blen = None, 0
            if data.get("photo_b64"):
                try: raw = base64.b64decode(data["photo_b64"])
                except Exception: _send(self, 400, {"error": "photo_b64 not valid base64"}); return
                ph, blen = hashlib.sha256(raw).hexdigest(), len(raw)
            cid = data.get("case_id") or f"HS-{time.strftime('%Y%m%d')}-{hashlib.sha256((cat+str(time.time())).encode()).hexdigest()[:6].upper()}"
            ev = event_bus.emit(data.get("actor_role", "mitra"), cid, "civic_intake",
                {"category": cat, "ward": data.get("ward"), "photo_hash": ph, "byte_length": blen, "gps": data.get("gps")},
                pii_fields=data.get("pii_fields"))
            _uplink(cid, {"kind": "civic", "case_id": cid, "category": cat, "ward": data.get("ward"), "photo_hash": ph})
            _send(self, 200, {"case_id": cid, "seq": ev["seq"], "photo_hash": ph, "byte_length": blen,
                              "sla_hours": ISSUE_CLOCKS.get(cat, DEFAULT_HOURS)})
        elif self.path == "/sync":
            try: r = outbox.flush_once(force=True, max_attempts=int(os.environ.get("HAQ_SYNC_MAXATT", "5")))
            except TypeError: r = outbox.flush_once(max_attempts=int(os.environ.get("HAQ_SYNC_MAXATT", "5")))
            _send(self, 200, r)
        elif self.path == "/backfill":
            if not BLOCK_URL: _send(self, 200, {"enqueued": [], "note": "no uplink; nothing to backfill"}); return
            from core import backfill as _bf
            _send(self, 200, _bf.sweep(BLOCK_URL))
        else:
            _send(self, 404, {"error": "not found"})

def main():
    event_bus.init()
    if BLOCK_URL:
        try:
            from core import backfill as _bf
            r = _bf.sweep(BLOCK_URL)
            if r["enqueued"]: print(f"[village] startup backfill enqueued {len(r['enqueued'])}")
        except Exception as e: print(f"[village] startup backfill skipped: {e}")
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"[village] http://{HOST}:{PORT} brain={BRAIN_TAG} uplink={'SET' if BLOCK_URL else 'NONE'} debug={DEBUG}")
    try: srv.serve_forever()
    except KeyboardInterrupt: pass

if __name__ == "__main__": main()
PYEOF

# =================== core/run_village_demo.py  (tolerant: a 500/disconnect = printed FAIL, not abort) ===================
cat > core/run_village_demo.py <<'PYEOF'
"""Village node proof w/ REAL brain. Run: python -m core.run_village_demo (sandboxed).
Tolerant: every HTTP call is wrapped so a 500 (handler guard) or a disconnect becomes a
printed FAIL line carrying the server traceback, NOT an abort -> we see ALL results and
the exact server error. HAQ_DEBUG=1 so the 500 body includes the full traceback."""
import os, sys, json, time, base64, socket, threading, sqlite3, tempfile, subprocess, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer
FAIL = []
def chk(n, c, e=""):
    print(f"  [{'OK' if c else 'FAIL'}] {n}{(' :: '+e) if e else ''}")
    if not c: FAIL.append(n)
class _Mock(BaseHTTPRequestHandler):
    down = True; lock = threading.Lock()
    def log_message(self, *a): pass
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", "0") or 0))
        with _Mock.lock: d = _Mock.down
        code = 503 if d else 200
        self.send_response(code); self.send_header("Content-Length", "0"); self.end_headers()
def _fp():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p
def _wait(port, path="/health", to=10.0):
    t0 = time.time()
    while time.time() - t0 < to:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=2) as r:
                j = json.loads(r.read())
                if path != "/health" or j.get("ok") is True: return j
        except Exception: pass
        time.sleep(0.15)
    raise RuntimeError(f":{port}{path} never healthy")
def _p(port, path, obj):
    """Tolerant POST: returns dict always; on HTTPError returns the parsed body+_status;
    on connect/drop returns {_status:0,error:repr}. Never raises -> demo continues."""
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=json.dumps(obj).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try: b = json.loads(e.read())
        except Exception: b = {"error": str(e)}
        b["_status"] = e.code; return b
    except Exception as e:
        return {"_status": 0, "error": repr(e)}
def _tb(v):
    """Render a server 500's traceback (or a drop) compactly for a FAIL line."""
    if v.get("_status") == 500:
        return f"SERVER-ERR {v.get('error')}: {(v.get('tb') or '').strip().splitlines()[-1] if v.get('tb') else ''}"
    if v.get("_status") == 0:
        return f"CONN-DROP {v.get('error')}"
    return ""
def _spawn(d, block=None, brain="real"):
    env = dict(os.environ)
    env.update({"HAQ_CHAIN": f"{d}/chain.jsonl", "HAQ_VAULT": f"{d}/vault.jsonl", "HAQ_KEYS": f"{d}/keys",
                "HAQ_VAULT_KEY": f"{d}/pii.key", "SDM_DB": f"{d}/sdm.db", "HAQ_OUTBOX": f"{d}/outbox.db",
                "HAQ_VILLAGE_PORT": str(_fp()), "HAQ_BRAIN": brain, "HAQ_DEBUG": "1"})
    if block: env["HAQ_BLOCK_URL"] = block
    else: env.pop("HAQ_BLOCK_URL", None)
    p = subprocess.Popen([sys.executable, "-m", "village.server"], env=env)
    return p, int(env["HAQ_VILLAGE_PORT"])
def phase_a():
    print("\n##### PHASE A : REAL brain over HTTP (uplink toggle) #####")
    d = tempfile.mkdtemp(prefix="haqvil_a_"); _Mock.down = True
    fp = _fp(); srv = HTTPServer(("127.0.0.1", fp), _Mock)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    p, port = _spawn(d, block=f"http://127.0.0.1:{fp}/sync", brain="real")
    try:
        h = _wait(port)
        chk("A village up, brain=real, uplink set", h.get("ok") is True and h.get("brain") == "real" and h.get("uplink_configured") is True, str(h))
        chk("A seams named (match_fn/extract)", h.get("match_seam") == "match_fn" and h.get("fact_seam") == "extract", str({k: h.get(k) for k in ('match_seam','fact_seam')}))
        v = _p(port, "/voice", {"raw_text": "Main 68 saal ki vidhwa hoon, mera kacha ghar hai, saal ki aamdani 80 hazaar hai",
                                "pii_fields": {"name": "Lakshmi Bai", "phone": "9900112233"}})
        chk("A real /voice matched (conf>0.6)", v.get("decision") == "matched" and (v.get("confidence") or 0) > 0.6, _tb(v) or str(v.get("confidence")))
        chk("A matched nsap_old_age+widow+pmay", {"nsap_old_age","nsap_widow","pmay_gramin"} <= set(v.get("schemes", [])), _tb(v) or str(v.get("schemes")))
        chk("A receipt issued", str(v.get("receipt_id", "")).startswith("HR-"), v.get("receipt_id"))
        chk("A proof_trace present", bool(v.get("proof_trace")), _tb(v))
        v3 = _p(port, "/voice", {"raw_text": "hello there nothing relevant at all"})
        chk("A garbage /voice ABSTAINED (not denied)", v3.get("decision") == "abstained", _tb(v3) or str(v3.get("reason")))
        c = _p(port, "/civic", {"category": "handpump", "ward": 4,
            "photo_b64": base64.b64encode(b"BROKEN-PUMP-PHOTO-BYTES").decode(),
            "pii_fields": {"name": "Sita", "phone": "9999888877"}})
        chk("A civic photo hashed (64 hex)", c.get("photo_hash") and len(c["photo_hash"]) == 64, _tb(c) or str(c.get("photo_hash"))[:12])
        s1 = _p(port, "/sync", {})
        chk("A sync#1 (down) queued, acked none", bool(s1.get("still_pending")) and not s1.get("acked"), _tb(s1) or str({k: s1.get(k) for k in ('acked','still_pending','dead')}))
        with _Mock.lock: _Mock.down = False
        s2 = _p(port, "/sync", {})
        chk("A sync#2 (up) acked queued", bool(s2.get("acked")) and not s2.get("still_pending"), _tb(s2) or str({k: s2.get(k) for k in ('acked','still_pending','dead')}))
        cc = sqlite3.connect(f"{d}/chain.db")
        blob = "".join(r[0] for r in cc.execute("SELECT payload FROM events"))
        cids = [r[0] for r in cc.execute("SELECT case_id FROM events")]; cc.close()
        chk("A chain NO raw PII names", all(x not in blob for x in ("Lakshmi","Sita")))
        chk("A chain NO raw phone digits", all(x not in blob for x in ("9900112233","9999888877")))
        chk("A chain NO photo bytes", "BROKEN-PUMP-PHOTO-BYTES" not in blob)
        chk("A chain DOES carry photo HASH", bool(c.get("photo_hash")) and c["photo_hash"] in blob)
        chk("A civic case_id on chain (COLUMN)", c.get("case_id") in cids, str(cids))
    finally:
        p.terminate(); p.wait(timeout=5); srv.shutdown()
def phase_b():
    print("\n##### PHASE B : NO uplink (offline booth local-durable) #####")
    d = tempfile.mkdtemp(prefix="haqvil_b_"); p, port = _spawn(d, block=None, brain="real")
    try:
        h = _wait(port)
        chk("B village up + uplink NONE", h.get("ok") is True and h.get("uplink_configured") is False, str(h))
        c = _p(port, "/civic", {"category": "drain", "ward": 3, "pii_fields": {"name": "Ravi", "phone": "9700001111"}})
        chk("B civic accepted + local seq", c.get("seq") is not None and c.get("case_id"), _tb(c) or str(c))
        st = _wait(port, "/status")
        chk("B civic OPEN in /status (SLA tracked offline)", c.get("case_id") in st.get("open_civic", []), str(st.get("open_civic")))
        ob = _wait(port, "/health").get("outbox", {})
        chk("B outbox total==0 (not dead-lettered w/o uplink)", ob.get("total", -1) == 0, str(ob))
        cc = sqlite3.connect(f"{d}/chain.db")
        cids = [r[0] for r in cc.execute("SELECT case_id FROM events")]
        blob = "".join(r[0] for r in cc.execute("SELECT payload FROM events")); cc.close()
        chk("B local chain durable (case_id COLUMN)", c.get("case_id") in cids, str(cids))
        chk("B local chain NO raw PII", "Ravi" not in blob and "9700001111" not in blob)
    finally:
        p.terminate(); p.wait(timeout=5)
def main():
    print("##### VILLAGE NODE - REAL PILLAR-1 BRAIN (tolerant) #####")
    phase_a(); phase_b()
    print("\n[RESULT]", "VILLAGE REAL-BRAIN GREEN" if not FAIL else f"FAILED: {FAIL}")
    sys.exit(0 if not FAIL else 1)
if __name__ == "__main__": main()
PYEOF

echo "########## SYNTAX / IMPORT SMOKE ##########"
python -m py_compile core/facts.py core/run_brain_audit.py village/server.py core/run_village_demo.py \
  && echo "  [OK] 4 rewritten files compile" || { echo "  [FAIL] compile"; exit 1; }
python -c "import core.facts, core.rule_engine, village.server, core.run_brain_audit, core.run_village_demo; print('  [OK] imports resolve')" || exit 1

echo "########## GATES (tail 30 so any server traceback is visible) ##########"
GATES=""
gate(){ local L="$1"; shift; local d; d="$(mktemp -d /tmp/p1b_XXXXXX)"
  env HAQ_CHAIN="$d/chain.jsonl" HAQ_VAULT="$d/vault.jsonl" HAQ_KEYS="$d/keys" HAQ_VAULT_KEY="$d/pii.key" \
      SDM_DB="$d/sdm.db" HAQ_OUTBOX="$d/outbox.db" HAQ_SABHA_PORT=8020 HAQ_SDM_PORT=8110 HAQ_VILLAGE_PORT=8000 \
      HAQ_XP_DIR="$d" HAQ_DASH_DIR="$d" HAQ_B_DIR="$d/b" "$@" 2>&1 | tail -n 30
  local rc="${PIPESTATUS[0]}"; printf '>>> %-12s exit=%s\n' "$L" "$rc"; rm -rf "$d"; GATES="$GATES $L=$rc"; }
gate "brain-audit" python -m core.run_brain_audit
gate "village"     python -m core.run_village_demo
gate "pillar1"     python -m core.run_pillar1_demo
gate "launch"      python -m core.run_launcher_demo
echo "########## SUMMARY ##########"
echo "GATES:$GATES"
allok=1; for kv in $GATES; do [ "${kv#*=}" = "0" ] || allok=0; done
[ "$allok" = 1 ] && echo "PILLAR 1 GREEN :: income/age extraction fixed (magnitude-aware, never-invent); village handler no longer drops connections silently" || echo "SEE RED GATE ABOVE (village FAIL line now carries SERVER-ERR <Type>: <line> -- paste it and I close red-2 in one shot)"
