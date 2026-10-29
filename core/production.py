"""HaqSetu PRODUCTION CORE: SQLite truth, signed ledger, auth, DPDP PII store,
device-bound OTP, geo-distance closure, weekly anchors. Stdlib only.
Exhibit mode (default): auth open. Pilot mode: set HAQ_AUTH=1 to enforce logins."""
import hashlib, hmac, json, math, os, secrets, sqlite3, time
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, "ledger", "haqsetu.db")
KEYFILE = os.path.join(BASE, "ledger", "actor_keys.json")
GEO_TOLERANCE_M = 200
router = APIRouter()

def _db():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    con = sqlite3.connect(DB); con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL"); return con

def init():
    con = _db()
    con.executescript("""
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE, role TEXT, salt TEXT, pass_hash TEXT);
    CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user_id INTEGER, expires INTEGER);
    CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, case_id TEXT, actor TEXT, action TEXT, payload TEXT, prev_hash TEXT, sig TEXT, ts TEXT);
    CREATE TABLE IF NOT EXISTS pii(id INTEGER PRIMARY KEY, case_id TEXT, field TEXT, value TEXT, created TEXT, erased_at TEXT);
    CREATE TABLE IF NOT EXISTS otp(case_id TEXT, code TEXT, device_token TEXT, issued TEXT, used INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS devices(case_id TEXT, token TEXT PRIMARY KEY, seen TEXT);
    CREATE TABLE IF NOT EXISTS anchors(week TEXT PRIMARY KEY, chain_code TEXT, place TEXT, ts TEXT);""")
    con.commit(); con.close()
    if not os.path.exists(KEYFILE):
        json.dump({r: secrets.token_hex(32) for r in ("facilitator","official","verifier","system","citizen")}, open(KEYFILE,"w"))
init()

def _keys(): return json.load(open(KEYFILE))
def sign(actor, msg): return hmac.new(_keys().get(actor,"k?").encode(), msg.encode(), hashlib.sha256).hexdigest()[:32]
def pbkdf2(pw, salt): return hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 120000).hex()

def record(case_id, actor, action, payload=None):
    con = _db()
    row = con.execute("SELECT sig FROM events ORDER BY id DESC LIMIT 1").fetchone()
    prev = row["sig"] if row else hashlib.sha256(b"genesis").hexdigest()[:32]
    ts = datetime.now().isoformat(timespec="seconds")
    body = json.dumps({"case":case_id,"actor":actor,"action":action,"payload":payload or {},"prev":prev,"ts":ts}, sort_keys=True)
    sig = sign(actor, body)
    con.execute("INSERT INTO events(case_id,actor,action,payload,prev_hash,sig,ts) VALUES(?,?,?,?,?,?,?)",
                (case_id, actor, action, json.dumps(payload or {}), prev, sig, ts))
    con.commit(); con.close(); return sig

def verify_chain():
    con = _db(); rows = con.execute("SELECT * FROM events ORDER BY id").fetchall(); con.close()
    prev = hashlib.sha256(b"genesis").hexdigest()[:32]
    for r in rows:
        body = json.dumps({"case":r["case_id"],"actor":r["actor"],"action":r["action"],"payload":json.loads(r["payload"]),"prev":prev,"ts":r["ts"]}, sort_keys=True)
        if r["prev_hash"] != prev or r["sig"] != sign(r["actor"], body):
            return {"ok": False, "broken_id": r["id"], "last_sig": prev}
        prev = r["sig"]
    return {"ok": True, "n": len(rows), "last_sig": prev}

class Cred(BaseModel): username: str; password: str; role: str = "facilitator"
@router.post("/auth/register")
def register(c: Cred):
    if c.role not in ("facilitator","official","verifier"): raise HTTPException(400, "role not allowed")
    salt = secrets.token_hex(8); con = _db()
    try: con.execute("INSERT INTO users(username,role,salt,pass_hash) VALUES(?,?,?,?)", (c.username, c.role, salt, pbkdf2(c.password, salt)))
    except sqlite3.IntegrityError: raise HTTPException(409, "user exists")
    con.commit(); con.close(); record("SYSTEM","system","user_registered",{"user":c.username,"role":c.role}); return {"ok": True}

@router.post("/auth/login")
def login(c: Cred):
    con = _db(); u = con.execute("SELECT * FROM users WHERE username=?", (c.username,)).fetchone()
    if not u or u["pass_hash"] != pbkdf2(c.password, u["salt"]): raise HTTPException(401, "bad credentials")
    tok = secrets.token_hex(16)
    con.execute("INSERT INTO sessions VALUES(?,?,?)", (tok, u["id"], int(time.time())+28800)); con.commit(); con.close()
    return {"token": tok, "role": u["role"]}

def authed(request: Request, roles=None):
    if os.environ.get("HAQ_AUTH", "0") != "1":
        return (roles or ["facilitator"])[0]
    tok = request.headers.get("x-haq-token","")
    con = _db(); s = con.execute("SELECT * FROM sessions WHERE token=? AND expires>?", (tok, int(time.time()))).fetchone()
    if not s: raise HTTPException(401, "login required")
    role = con.execute("SELECT role FROM users WHERE id=?", (s["user_id"],)).fetchone()["role"]; con.close()
    if roles and role not in roles: raise HTTPException(403, "role not permitted")
    return role

class PIIReq(BaseModel): case_id: str; field: str; value: str
class CaseReq(BaseModel): case_id: str
@router.post("/pii/put")
def pii_put(p: PIIReq, request: Request):
    authed(request, ("facilitator",)); con = _db()
    con.execute("INSERT INTO pii(case_id,field,value,created) VALUES(?,?,?,?)", (p.case_id, p.field, p.value, datetime.now().isoformat()))
    con.commit(); con.close(); record(p.case_id,"facilitator","pii_stored",{"field":p.field}); return {"ok": True}
@router.post("/pii/erase")
def pii_erase(p: CaseReq, request: Request):
    authed(request, ("facilitator","official")); con = _db()
    con.execute("UPDATE pii SET erased_at=? WHERE case_id=? AND erased_at IS NULL", (datetime.now().isoformat(), p.case_id))
    con.commit(); con.close(); record(p.case_id,"system","pii_erased",{}); return {"ok": True, "note": "ledger holds codes only; chain intact"}

class PairReq(BaseModel): case_id: str; token: str
@router.post("/device/pair")
def pair(p: PairReq):
    con = _db(); con.execute("INSERT OR REPLACE INTO devices VALUES(?,?,?)", (p.case_id, p.token, datetime.now().isoformat()))
    con.commit(); con.close(); return {"ok": True}

@router.post("/otp/issue")
def otp_issue(p: CaseReq, request: Request):
    authed(request, ("facilitator",)); code = f"{secrets.randbelow(9000)+1000}"; con = _db()
    dev = con.execute("SELECT token FROM devices WHERE case_id=? ORDER BY seen DESC LIMIT 1", (p.case_id,)).fetchone()
    con.execute("INSERT INTO otp VALUES(?,?,?,?,0)", (p.case_id, code, dev["token"] if dev else "", datetime.now().isoformat()))
    con.commit(); con.close()
    ch = "citizen-device" if dev else "read-aloud-fallback"
    record(p.case_id,"facilitator","otp_issued",{"channel":ch})
    return {"channel": ch, "otp": None if dev else code}

@router.get("/otp/mine")
def otp_mine(case: str, token: str):
    con = _db(); o = con.execute("SELECT code,used FROM otp WHERE case_id=? AND device_token=? ORDER BY issued DESC LIMIT 1", (case, token)).fetchone(); con.close()
    return {"otp": o["code"], "used": bool(o["used"])} if o else {"otp": None}

@router.post("/otp/confirm")
def otp_confirm(body: dict):
    case, tok = body.get("case",""), body.get("token","")
    con = _db(); o = con.execute("SELECT * FROM otp WHERE case_id=? AND device_token=? AND used=0 ORDER BY issued DESC LIMIT 1", (case, tok)).fetchone()
    if not o: raise HTTPException(404, "no pending OTP on this device")
    con.execute("UPDATE otp SET used=1 WHERE case_id=? AND code=?", (case, o["code"])); con.commit(); con.close()
    record(case,"citizen","closure_confirmed_by_otp",{}); return {"ok": True}

def otp_used(case):
    con = _db(); r = con.execute("SELECT used FROM otp WHERE case_id=? ORDER BY issued DESC LIMIT 1", (case,)).fetchone(); con.close()
    return bool(r and r["used"])

def otp_verify_code(case, code):
    con = _db(); o = con.execute("SELECT * FROM otp WHERE case_id=? AND code=? AND used=0 ORDER BY issued DESC LIMIT 1", (case, code or "")).fetchone()
    if not o: return False
    con.execute("UPDATE otp SET used=1 WHERE case_id=? AND code=?", (case, code)); con.commit(); con.close()
    record(case,"citizen","closure_confirmed_by_otp_readback",{}); return True

def haversine(a, b):
    la1, lo1 = map(float, a.split(",")); la2, lo2 = map(float, b.split(","))
    p = math.radians; dla = p(la2-la1); dlo = p(lo2-lo1)
    h = math.sin(dla/2)**2 + math.cos(p(la1))*math.cos(p(la2))*math.sin(dlo/2)**2
    return 2*6371000*math.asin(math.sqrt(h))
def geo_ok(g1, g2, tol=GEO_TOLERANCE_M):
    try: return haversine(g1, g2) <= tol
    except Exception: return False

class AnchorReq(BaseModel): place: str
@router.post("/anchor")
def anchor(a: AnchorReq, request: Request):
    authed(request, ("verifier",)); v = verify_chain()
    if not v["ok"]: raise HTTPException(409, "chain broken - repair before anchoring")
    y, w, _ = datetime.now().isocalendar(); wk = f"{y}-W{w:02d}"; con = _db()
    con.execute("INSERT OR REPLACE INTO anchors VALUES(?,?,?,?)", (wk, v["last_sig"], a.place, datetime.now().isoformat()))
    con.commit(); con.close(); return {"week": wk, "chain_code": v["last_sig"]}

@router.get("/audit")
def audit():
    v = verify_chain(); con = _db()
    n = con.execute("SELECT COUNT(*) c FROM events").fetchone()["c"]
    p = con.execute("SELECT COUNT(*) c FROM pii WHERE erased_at IS NULL").fetchone()["c"]; con.close()
    return {**v, "events": n, "live_pii_rows": p}
