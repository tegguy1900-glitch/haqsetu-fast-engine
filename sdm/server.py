"""
Haq Setu - SDM dashboard PREVIEW host (port 8110; stdlib only).
Launch:  python -m sdm.server   (from project root)
NOTE: 8100 is reserved for the real SDM node (node/block.py). This process is a
preview/render host so we can prove the board without the legacy source. In
production, mount view_model.build() inside node/block.py's /api/sdm instead.
Routes:
  GET /            -> board.html (the wall board)
  GET /board.html  -> same
  GET /api/view    -> JSON view-model (live now)
  GET /health      -> {ok, chain_len, counts}
"""
import os, json, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from sdm import view_model

PORT = int(os.environ.get("HAQ_SDM_PORT", "8110"))
HOST = os.environ.get("HAQ_SDM_HOST", "127.0.0.1")
HERE = os.path.dirname(__file__)

def _send(h, code, body, ctype="application/json"):
    b = body if isinstance(body, bytes) else json.dumps(body, sort_keys=True).encode()
    h.send_response(code)
    h.send_header("Content-Type", ctype)
    h.send_header("Content-Length", str(len(b)))
    h.send_header("Access-Control-Allow-Origin", "*")
    h.end_headers(); h.wfile.write(b)

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        if self.path in ("/", "/board.html", "/index.html"):
            with open(os.path.join(HERE, "board.html"), "rb") as f:
                _send(self, 200, f.read(), "text/html; charset=utf-8")
        elif self.path == "/api/view":
            _send(self, 200, view_model.build(now=time.time()))
        elif self.path == "/health":
            v = view_model.build(now=time.time())
            _send(self, 200, {"ok": v["integrity"]["chain_ok"],
                              "chain_len": v["integrity"]["chain_len"],
                              "counts": v["counts"]})
        else:
            _send(self, 404, {"error": "not found"})

def main():
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"[sdm-preview] http://{HOST}:{PORT}  sdm_db={os.environ.get('SDM_DB','sdm/sdm.db')}  "
          f"chain={os.environ.get('HAQ_CHAIN','ledger/chain.jsonl')}")
    try: srv.serve_forever()
    except KeyboardInterrupt: pass

if __name__ == "__main__":
    main()
