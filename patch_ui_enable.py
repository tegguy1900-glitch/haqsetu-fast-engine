import re

with open('village/server.py', 'r') as f:
    code = f.read()

# Find where we return schemes in the /voice route
# We look for: out["schemes"] = res["schemes"];
old_line = 'out["schemes"] = res["schemes"];'
new_line = '''# Enrich schemes with apply capability
            enriched_schemes = []
            for s in res.get("schemes", []):
                s_copy = dict(s)
                # Hardcode eligibility for demo purposes based on scheme ID/Name
                if "MGNREGA" in str(s_copy.get("scheme_id", "")).upper() or "mgnrega" in str(s_copy.get("name", "")).lower():
                    s_copy["can_apply"] = True
                else:
                    s_copy["can_apply"] = False
                enriched_schemes.append(s_copy)
            
            out["schemes"] = enriched_schemes;'''

if old_line in code:
    code = code.replace(old_line, new_line)
    print("✅ Enabled 'can_apply' flag for MGNREGA.")
else:
    print("⚠️ Could not find exact line. Checking structure...")
    # Fallback regex
    pattern = r'(out\["schemes"\]\s*=\s*)res\["schemes"\];'
    match = re.search(pattern, code)
    if match:
        replacement = match.group(1) + '''[
                {**s, "can_apply": "MGNREGA" in str(s.get("scheme_id", "")).upper() or "mgnrega" in str(s.get("name", "")).lower()} 
                for s in res["schemes"]
            ];'''
        code = code[:match.start()] + replacement + code[match.end():]
        print("✅ Injected dynamic can_apply flags via regex fallback.")
    else:
        print("❌ Structure unexpected. Manual edit needed.")

with open('village/server.py', 'w') as f:
    f.write(code)
