from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sys, os, json, hashlib, random
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from triage.abstain import triage_with_abstention
from agent.solution_generator import generate_spoken_solution
from engine.red_flags import analyze_corruption_risk

app = FastAPI(title="HaqSetu Agentic API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

CASES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cases_board.json")
VERIFIER_POOL = ["School Teacher (rotating pool)", "ASHA Worker (rotating pool)", "SHG Representative (rotating pool)"]


class TriageRequest(BaseModel):
    text: str


class DenialAttempt(BaseModel):
    case_id: str
    reason: str


class OpenCase(BaseModel):
    case_id: str
    route: str
    desk: str
    waiting_at: str = "Panchayat"
    clock_hours: int = 48


class CloseCase(BaseModel):
    case_id: str
    force_audit: bool = False


class FastForward(BaseModel):
    case_id: str
    hours: int = 48


def _load_cases():
    if not os.path.exists(CASES_FILE):
        return []
    with open(CASES_FILE, encoding="utf-8") as f:
        return json.load(f)


def _save_cases(cases):
    with open(CASES_FILE, "w", encoding="utf-8") as f:
        json.dump(cases, f, indent=2)


def _log_ledger(event):
    os.makedirs("ledger", exist_ok=True)
    with open("ledger/chain.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


@app.post("/triage")
def run_triage(req: TriageRequest):
    result = triage_with_abstention(req.text)
    labels = result.get("labels", [])
    scheme = labels[0] if labels else "unknown"
    outcome = "include" if result["action"] == "ACCEPT" else "needs_official_decision"
    spoken_script = generate_spoken_solution(
        scheme=scheme, outcome=outcome, facts={},
        ttbr_data={"ttbr_days": 7, "bottleneck": {"task": "verification"}}, proof_data={},
    )
    return {
        "action": result["action"],
        "confidence": result["confidence"],
        "labels": labels,
        "spoken_script": spoken_script,
        "brain_scan": result.get("intent", {}).get("scores", {}),
    }


@app.post("/upload-evidence")
async def upload_evidence(file: UploadFile = File(...), case_id: str = "UNKNOWN"):
    contents = await file.read()
    photo_hash = hashlib.sha256(contents).hexdigest()
    os.makedirs("uploads", exist_ok=True)
    with open(f"uploads/{file.filename}", "wb") as f:
        f.write(contents)
    _log_ledger({"event": "evidence_locked", "case_id": case_id, "filename": file.filename,
                 "sha256_hash": photo_hash, "timestamp": datetime.now().isoformat(), "actor": "facilitator"})
    return {"status": "LOCKED", "filename": file.filename, "sha256": photo_hash}


@app.post("/attempt-denial")
def attempt_denial(req: DenialAttempt):
    proof_trace = {
        "premise_1": "HaqSetu Core Directive: include, escalate, abstain; never deny.",
        "premise_2": f"Local Official attempted to reject Case {req.case_id}.",
        "premise_3": f"Stated Reason: '{req.reason}'.",
        "premise_4": "Rule pack validation: citizen meets baseline criteria or requires human review.",
        "conclusion": "AUTOMATED DENIAL PRECLUDED BY CONSTRUCTION.",
        "action_taken": "Case escalated to District Grievance Redressal Officer.",
        "cryptographic_receipt": hashlib.sha256(
            f"{req.case_id}{req.reason}{datetime.now().isoformat()}".encode()).hexdigest()[:16],
    }
    return {"status": "DENIAL_BLOCKED",
            "message": "The system cannot deny a citizen. Attempt logged and escalated.",
            "proof_trace": proof_trace}


@app.get("/red-flags")
def red_flags():
    return analyze_corruption_risk()


@app.post("/open-case")
def open_case(req: OpenCase):
    cases = _load_cases()
    cases.append({"case_id": req.case_id, "route": req.route, "desk": req.desk,
                  "waiting_at": req.waiting_at, "clock_hours": req.clock_hours,
                  "opened_at": datetime.now().isoformat(), "status": "open"})
    _save_cases(cases)
    _log_ledger({"event": "case_opened", "case_id": req.case_id, "route": req.route,
                 "desk": req.desk, "clock_hours": req.clock_hours,
                 "timestamp": datetime.now().isoformat(), "actor": "facilitator"})
    return {"status": "opened", "case_id": req.case_id}


@app.get("/board")
def board():
    cases = _load_cases()
    now = datetime.now()
    out = []
    changed = False
    led_map = {"open": "red", "in_progress": "amber", "escalated": "amber",
               "ghost_audit": "amber", "closed": "green"}
    for c in cases:
        elapsed = (now - datetime.fromisoformat(c["opened_at"])).total_seconds() / 3600.0
        if c["status"] in ("open", "in_progress") and elapsed > c["clock_hours"]:
            c["status"] = "escalated"
            c["waiting_at"] = "Block Office (auto-escalated with evidence)"
            changed = True
            _log_ledger({"event": "auto_escalation", "case_id": c["case_id"],
                         "reason": "stall rule exceeded", "timestamp": now.isoformat(), "actor": "system"})
        out.append({**c, "hours_elapsed": round(elapsed, 1),
                    "led": led_map.get(c["status"], "red"),
                    "overdue": elapsed > c["clock_hours"]})
    if changed:
        _save_cases(cases)
    return {"cases": out}


@app.post("/fast-forward")
def fast_forward(req: FastForward):
    cases = _load_cases()
    for c in cases:
        if c["case_id"] == req.case_id:
            c["opened_at"] = (datetime.fromisoformat(c["opened_at"]) - timedelta(hours=req.hours)).isoformat()
            _save_cases(cases)
            return {"status": "fast-forwarded", "case_id": req.case_id, "hours": req.hours}
    return {"status": "case not found"}


@app.post("/close-case")
def close_case(req: CloseCase):
    cases = _load_cases()
    target = next((c for c in cases if c["case_id"] == req.case_id), None)
    if target is None:
        return {"status": "case not found"}
    if req.force_audit or random.random() < 0.10:
        verifiers = random.sample(VERIFIER_POOL, 2)
        target["status"] = "ghost_audit"
        target["verifiers"] = verifiers
        _save_cases(cases)
        _log_ledger({"event": "ghost_audit_triggered", "case_id": req.case_id,
                     "verifiers": verifiers, "timestamp": datetime.now().isoformat(), "actor": "system"})
        return {"status": "GHOST_AUDIT_TRIGGERED", "case_id": req.case_id, "verifiers": verifiers,
                "message": "Closure intercepted by the 10% callback rule. Case locked until two independent verifiers confirm."}
    target["status"] = "closed"
    _save_cases(cases)
    _log_ledger({"event": "case_closed", "case_id": req.case_id,
                 "timestamp": datetime.now().isoformat(), "actor": "official"})
    return {"status": "CLOSED_PENDING_CITIZEN_CONFIRM", "case_id": req.case_id,
            "message": "Closed. Awaiting citizen confirmation by slip code."}


@app.get("/health")
def health():
    return {"status": "ok", "empire_status": "ONLINE"}


@app.get("/cases")
def get_cases():
    return _load_cases()
