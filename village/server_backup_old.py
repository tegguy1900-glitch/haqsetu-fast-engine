import http.server
import json
import core.scheme_application as scheme_app

class Handler(http.server.BaseHTTPRequestHandler):
    def _post(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        data = json.loads(post_data.decode('utf-8'))

        if self.path == '/apply_step':
            scheme = data.get('scheme')
            step = data.get('step')
            text = data.get('text')
            result = scheme_app.process_voice_step(scheme, step, text)
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"result": result}).encode('utf-8'))

        elif self.path == '/upload_doc':
            scheme = data.get('scheme')
            doc_type = data.get('doc_type')
            filename = data.get('filename')
            result = scheme_app.verify_document(scheme, doc_type, filename)
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"result": result}).encode('utf-8'))

        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Not Found')

    def do_POST(self):
        self._post()

    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b'Hello, world!')
