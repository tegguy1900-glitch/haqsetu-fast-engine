import re

with open('village/server.py', 'r') as f:
    code = f.read()

# 1. Import the generator at top
if 'from core.pdf_gen import generate_sdm_report' not in code:
    lines = code.split('\n')
    insert_idx = 0
    for i, line in enumerate(lines):
        if 'from core.parser import' in line:
            insert_idx = i + 1
            break
    lines.insert(insert_idx, 'from core.pdf_gen import generate_sdm_report')
    code = '\n'.join(lines)

# 2. Add Route Handler Logic
handler_code = '''
    def handle_generate_report(self, data):
        try:
            filepath = generate_sdm_report()
            self._send_json(200, {
                "status": "success",
                "message": "Report Generated Successfully",
                "download_url": "/reports/" + os.path.basename(filepath)
            })
        except Exception as e:
            traceback.print_exc()
            self._send_json(500, {"error": str(e)})
'''

# Insert handler before main execution block or after last handler
if 'def handle_get_agenda' in code:
    # Find end of handle_get_agenda and insert after it
    pattern = r'(    def handle_get_agenda\(self\):.*?return)'
    match = re.search(pattern, code, re.DOTALL)
    if match:
        idx = match.end()
        code = code[:idx] + '\n' + handler_code + code[idx:]
        print("✅ Added handle_generate_report function.")
    else:
        print("⚠️ Could not find insertion point for handler.")
else:
    print("❌ Missing handle_get_agenda. Cannot auto-patch.")

# 3. Register Route in do_POST
route_check = '/api/meeting/report'
if route_check not in code:
    # Find the chain of elif statements in do_POST
    # We look for the fallback else statement to inject before it
    pattern_else = r'(        else:\s*self\._send_json\(404, \{"error": "Endpoint not found"\}\))'
    replacement = f'''        elif path == "{route_check}":
            self.handle_generate_report(data)
        \\1'''
    
    if re.search(pattern_else, code):
        code = re.sub(pattern_else, replacement, code)
        print("✅ Registered /api/meeting/report route.")
    else:
        print("⚠️ Could not find else block in do_POST. Manual check needed.")

with open('village/server.py', 'w') as f:
    f.write(code)
    
print("\n🎉 SERVER PATCHED FOR PDF GENERATION.")
