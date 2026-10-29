"""Stdlib smoke client for the Sabha seam. Run: python -m sabha.http_client"""
import os, json, base64, urllib.request, urllib.error
BASE = f"http://127.0.0.1:{os.environ.get('HAQ_SABHA_PORT','8020')}"

def _req(path, obj=None):
    try:
        if obj is None:
            with urllib.request.urlopen(BASE + path, timeout=5) as r:
                return json.loads(r.read())
        req = urllib.request.Request(BASE + path, data=json.dumps(obj).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            b = json.loads(e.read())
        except Exception:
            b = {"error": str(e)}
        b["_status"] = e.code
        return b

MOCK = [
    {"speaker": "Sarpanch",   "text": "Today we approved Rs 50,000 for the Ward 3 drain cleaning."},
    {"speaker": "Villager-A", "text": "The handpump in Ward 4 has been broken for two weeks, no water."},
    {"speaker": "Secretary",  "text": "I will fix the streetlights in Ward 2 by Friday."},
    {"speaker": "Villager-B", "text": "The road near the school is full of potholes, very dangerous."},
    {"speaker": "Sarpanch",   "text": "Resolved unanimously that the anganwadi roof repair is passed."},
]
GP, DATE = "GP-SEAM", "2026-10-21"

def main():
    print("health      :", _req("/health"))
    rec = _req("/record", {"gp": GP, "date": DATE, "chunk_index": 0,
                           "audio_b64_chunk": base64.b64encode(b"FAKE-SABHA-AUDIO-WARD9-HANDPUMP").decode()})
    print("record      :", rec)
    print("health+stage:", _req("/health"))
    m1 = _req("/transcribe", {"gp": GP, "date": DATE, "segments": MOCK})["minutes"]
    print(f"transcribe1 : decisions={len(m1['decisions'])} actions={len(m1['action_items'])} grievances={len(m1['grievances'])}")
    print("sign1       :", _req("/sign", {"minutes": m1, "signed": True, "signer_role": "sarpanch", "open_civic": True}))
    p2 = _req("/transcribe", {"gp": GP, "date": DATE, "lang": "hi"})
    mm2 = p2.get("minutes", {})
    print(f"transcribe2 : status={p2.get('_status',200)} via={p2.get('via')} "
          f"actions={len(mm2.get('action_items',[]))} grievances={len(mm2.get('grievances',[]))}")
    print("health+wipe :", _req("/health"))
    print("sign2       :", _req("/sign", {"minutes": mm2, "signed": True, "signer_role": "sarpanch", "open_civic": True}))
    print("retranscribe:", _req("/transcribe", {"gp": GP, "date": DATE}))   # expect 400 (stage gone)
    print("health after:", _req("/health"))

if __name__ == "__main__":
    main()
