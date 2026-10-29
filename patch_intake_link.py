import re

with open('village/server.py', 'r') as f:
    code = f.read()

# Find where we send the matched schemes back
# Look for: out["schemes"] = res["schemes"];
old_line = 'out["schemes"] = res["schemes"];'
new_line = '''out["schemes"] = [
                {
                    "id": s.get("scheme_id", "UNKNOWN"),
                    "name": s.get("name", "Unknown Scheme"),
                    "confidence": s.get("confidence", 0),
                    "can_apply": True, # Flag to show Apply Button
                    "form_endpoint": "/apply_step" 
                } for s in res["schemes"]
            ];'''

if old_line in code:
    code = code.replace(old_line, new_line)
    print("✅ Updated /voice response to include 'can_apply' flags.")
else:
    print("⚠️ Could not find exact line. Checking structure...")
    # Fallback: Just ensure schemes are dicts if they aren't already handled by JS

with open('village/server.py', 'w') as f:
    f.write(code)
