import re

with open('village/server.py', 'r') as f:
    code = f.read()

# Find where we construct the output dictionary for matched schemes
# Look for: out["schemes"] = res["schemes"];
old_line = 'out["schemes"] = res["schemes"];'
new_line = '''# Add apply capability metadata to each matched scheme
            enriched_schemes = []
            for s in res.get("schemes", []):
                s_copy = dict(s) # shallow copy
                # Only enable apply for known automatable schemes
                if s_copy.get("scheme_id") in ["MGNREGA", "PMAY", "OLD_AGE_PENSION"]:
                    s_copy["can_apply"] = True
                    s_copy["form_type"] = "voice_application"
                else:
                    s_copy["can_apply"] = False
                
                enriched_schemes.append(s_copy)
            
            out["schemes"] = enriched_schemes;'''

if old_line in code:
    code = code.replace(old_line, new_line)
    print("✅ Added 'can_apply' flag logic to /voice route.")
else:
    print("⚠️ Could not find exact line. Checking alternative structure...")
    # Fallback: Try finding just the assignment part
    pattern = r'(out\["schemes"\]\s*=\s*)res\["schemes"\];'
    match = re.search(pattern, code)
    if match:
        replacement = match.group(1) + '''[
                {**s, "can_apply": s.get("scheme_id") in ["MGNREGA", "PMAY", "OLD_AGE_PENSION"]} 
                for s in res["schemes"]
            ];'''
        code = code[:match.start()] + replacement + code[match.end():]
        print("✅ Injected dynamic can_apply flags via regex fallback.")
    else:
        print("❌ Structure unexpected. Manual inspection needed.")

with open('village/server.py', 'w') as f:
    f.write(code)
