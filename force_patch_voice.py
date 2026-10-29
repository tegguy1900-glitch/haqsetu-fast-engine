import re

with open('village/server.py', 'r') as f:
    lines = f.readlines()

new_lines = []
in_voice_block = False
patched = False

for i, line in enumerate(lines):
    # Detect start of /voice handling
    if '/voice' in line and 'elif self.path ==' in line:
        in_voice_block = True
    
    # If we are inside /voice block, look for where schemes are assigned or returned
    if in_voice_block and not patched:
        # Look for common patterns like: out["schemes"] = ... OR return _send(..., out)
        # We will insert our enrichment logic JUST BEFORE the final send/return
        
        # Pattern 1: Assignment to out["schemes"]
        if 'out["schemes"]' in line and '=' in line:
            indent = len(line) - len(line.lstrip())
            spaces = ' ' * indent
            
            # Insert enrichment logic before assignment
            new_lines.append(f"{spaces}# ENRICH SCHEMES WITH APPLY FLAG\n")
            new_lines.append(f"{spaces}schemes_raw = res.get('schemes', [])\n")
            new_lines.append(f"{spaces}enriched_schemes = []\n")
            new_lines.append(f"{spaces}for s in schemes_raw:\n")
            new_lines.append(f"{spaces}    s_copy = dict(s)\n")
            new_lines.append(f"{spaces}    sid = str(s_copy.get('scheme_id', '')).upper()\n")
            new_lines.append(f"{spaces}    name = str(s_copy.get('name', '')).lower()\n")
            new_lines.append(f"{spaces}    if 'MGNREGA' in sid or 'mgnrega' in name:\n")
            new_lines.append(f"{spaces}        s_copy['can_apply'] = True\n")
            new_lines.append(f"{spaces}    else:\n")
            new_lines.append(f"{spaces}        s_copy['can_apply'] = False\n")
            new_lines.append(f"{spaces}    enriched_schemes.append(s_copy)\n")
            new_lines.append(f"{spaces}out['schemes'] = enriched_schemes;\n")
            
            # Skip original line since we replaced it
            continue
            
        # Pattern 2: Direct return/send without intermediate variable (less likely but possible)
        elif '_send(self,' in line and 'out' in line:
             # Too risky to guess here. Stick to Pattern 1.
             pass

    new_lines.append(line)

if not patched:
    print("⚠️ Could not auto-detect injection point. Falling back to manual instruction.")
else:
    with open('village/server.py', 'w') as f:
        f.writelines(new_lines)
    print("✅ Forced Patch Applied Successfully!")
