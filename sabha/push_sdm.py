"""
Haq Setu - Sabha -> SDM pipeline (Pillar 2 tail + the Glue).
sign/refuse minutes -> emit through the unified bus -> land a row in the
SDM sqlite db. Grievances can auto-open civic cases (cross-pillar link),
gated by consent so we never fabricate a citizen's complaint.
"""
import os, json, time, hashlib, sqlite3
from core import event_bus

SDM_DB = os.environ.get("SDM_DB", "sdm/sdm.db")

def _hash(minutes):
    return hashlib.sha256(json.dumps(minutes, sort_keys=True).encode()).hexdigest()

def _ensure_db():
    os.makedirs(os.path.dirname(SDM_DB) or ".", exist_ok=True)
    c = sqlite3.connect(SDM_DB)
    c.execute("""CREATE TABLE IF NOT EXISTS sabha_minutes(
        id INTEGER PRIMARY KEY AUTOINCREMENT, gp TEXT, meeting_date TEXT,
        minutes_json TEXT, minutes_hash TEXT, ledger_seq INTEGER,
        sarpanch_signed INTEGER, refuse_reason TEXT,
        pushed_at REAL, sdm_ack INTEGER DEFAULT 0)""")
    c.commit(); return c

def push(minutes, signed, signer_role="sarpanch", refuse_reason=None,
         open_civic_from_grievances=False):
    event_bus.init()
    mh = _hash(minutes)
    case_id = f"SABHA-{minutes['gp']}-{minutes['meeting_date']}"
    if signed:
        ev = event_bus.emit(signer_role, case_id, "sabha_signed",
                            {**minutes, "minutes_hash": mh})
        flag, reason = 1, None
    else:
        ev = event_bus.emit(signer_role, case_id, "sabha_unsigned",
                            {"minutes_hash": mh, "reason": refuse_reason or "unspecified"})
        flag, reason = 0, refuse_reason
    c = _ensure_db()
    c.execute("""INSERT INTO sabha_minutes(gp,meeting_date,minutes_json,minutes_hash,
                 ledger_seq,sarpanch_signed,refuse_reason,pushed_at)
                 VALUES(?,?,?,?,?,?,?,?)""",
              (minutes["gp"], minutes["meeting_date"], json.dumps(minutes, sort_keys=True),
               mh, ev["seq"], flag, reason, time.time()))
    c.commit()
    linked = []
    if signed and open_civic_from_grievances:
        for i, g in enumerate(minutes["grievances"]):
            cid = f"HS-{minutes['gp']}-{minutes['meeting_date']}-{i}"
            event_bus.emit("system", cid, "civic_intake",
                           {"category": g["category"], "ward": g["ward"],
                            "source": "sabha_auto", "photo_hash": None,
                            "gps": None, "opened_by_minutes": mh[:12]})
            linked.append(cid)
    c.close()
    return {"event": ev, "minutes_hash": mh, "civic_cases_opened": linked}

def pending_acks():
    c = _ensure_db()
    rows = c.execute("SELECT id,gp,meeting_date,sarpanch_signed FROM sabha_minutes WHERE sdm_ack=0").fetchall()
    c.close(); return rows

def all_rows():
    c = _ensure_db()
    rows = c.execute("SELECT id,gp,meeting_date,minutes_hash,ledger_seq,sarpanch_signed FROM sabha_minutes").fetchall()
    c.close(); return rows

def ack(row_id, ack=1):
    """SDM acknowledges a minutes row (clears the pending-ack amber flag).
    Additive helper; when node/block.py returns, migrate this into the SDM node."""
    c = _ensure_db()
    c.execute("UPDATE sabha_minutes SET sdm_ack=? WHERE id=?", (int(ack), int(row_id)))
    c.commit(); c.close()
    return row_id
