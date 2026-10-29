import os

server_file = 'village/server.py'
with open(server_file, 'r') as f:
    content = f.read()

# 1. Add helpers if missing
if '_demo_html' not in content:
    helpers = """
import os
_DEMO_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web_demo", "index.html")
def _demo_html():
    try:
        with open(_DEMO_PATH, encoding="utf-8") as f: return f.read()
    except Exception: return "<h1>demo missing</h1>"
def _send_html(h, code, text):
    b = text.encode("utf-8")
    h.send_response(code); h.send_header("Content-Type","text/html"); h.send_header("Content-Length",str(len(b))); h.end_headers(); h.wfile.write(b)
"""
    content = content.replace("import os", "import os" + helpers)

# 2. Add route to _get
if 'u.path in ("/", "/index.html")' not in content:
    route = """
        if u.path in ("/", "/index.html"):
            _send_html(self, 200, _demo_html())
            return
"""
    content = content.replace("def _get(self):", "def _get(self):" + route)

with open(server_file, 'w') as f:
    f.write(content)
print("Server patched to serve UI!")
