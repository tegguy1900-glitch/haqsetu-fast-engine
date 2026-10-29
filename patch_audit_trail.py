import re

with open('village/server.py', 'r') as f:
    code = f.read()

# 1. Add Hashing Helper Function at top (after imports)
helper_code = '''
def generate_audit_hash(record_dict, prev_hash="GENESIS"):
    """Creates a deterministic hash for tamper-proof logging."""
    payload = json.dumps(record_dict, sort_keys=True) + str(prev_hash)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]
'''

if 'def generate_audit_hash' not in code:
    # Insert after the last import line
    lines = code.split('\n')
    insert_idx = 0
    for i, line in enumerate(lines):
        if line.startswith('from ') or line.startswith('import '):
            insert_idx = i + 1
    lines.insert(insert_idx, helper_code)
    code = '\n'.join(lines)
    print("✅ Added Audit Hash Helper.")

# 2. Patch handle_infra_create to include hash
old_create = r'(def handle_infra_create\(self, data\):.*?ticket_id = c\.lastrowid)'
new_create_logic = '''
        # Calculate Audit Hash before inserting
        audit_data = {"desc": desc, "lat": lat, "lon": lon, "time": time.time()}
        new_hash = generate_audit_hash(audit_data)
        
        c.execute("""INSERT INTO tickets_infra 
                     (description, photo_path, geo_lat, geo_lon, status, audit_hash)
                     VALUES (?, ?, ?, ?, 'open', ?)""",
                  (desc, filepath, lat, lon, new_hash))
                  
        ticket_id = c.lastrowid'''

code = re.sub(old_create, lambda m: m.group(0).replace("ticket_id = c.lastrowid", new_create_logic), code, flags=re.DOTALL)
print("✅ Patched Infra Create with Hashing.")

# 3. Patch handle_execute_bot to include hash
old_exec = r'(def handle_execute_bot\(self, data\):.*?conn\.commit\(\))'
# We need to find the INSERT statement inside and add the hash column
# Since regex replacement inside nested structures is tricky, we'll use a simpler string replace strategy for the specific SQL query part.

sql_insert_pattern = r'c\.execute\("""INSERT INTO applications_scheme[^"]+"""'
replacement_sql = '''c.execute("""INSERT INTO applications_scheme 
                         (citizen_mobile_hash, scheme_name, parsed_data_json, bot_status, reg_id_generated, screenshot_path, audit_hash)
                         VALUES (?, ?, ?, ?, ?, ?, ?)"""'''

if sql_insert_pattern in code:
    code = code.replace(sql_insert_pattern, replacement_sql)
    
    # Now update the values tuple in the same function
    # Find the values line following the execute call
    values_pattern = r'\(mobile_hash, scheme_id, json\.dumps\(user_data\), "success", result\["registration_id"\], result\["screenshot_path"\]\)'
    new_values = '(mobile_hash, scheme_id, json.dumps(user_data), "success", result["registration_id"], result["screenshot_path"], generate_audit_hash(result))'
    
    code = code.replace(values_pattern, new_values)
    print("✅ Patched Bot Execution with Hashing.")
else:
    print("⚠️ Could not auto-patch Bot SQL. Manual check needed.")

with open('village/server.py', 'w') as f:
    f.write(code)
    
print("\n🎉 AUDIT TRAIL PATCH APPLIED.")
