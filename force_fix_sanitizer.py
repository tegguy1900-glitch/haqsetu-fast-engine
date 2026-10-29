with open('village/server.py', 'r') as f:
    lines = f.readlines()

new_lines = []
skip_next = False

for line in lines:
    # Detect start of broken function
    if 'def sanitize_input(text):' in line:
        skip_next = True
        # Insert clean replacement immediately
        new_lines.append("def sanitize_input(text):\n")
        new_lines.append("    if not text: return ''\n")
        new_lines.append("    # Simple removal of dangerous chars without complex regex\n")
        new_lines.append("    safe_chars = ''.join(c for c in str(text) if c.isalnum() or c in ' .,-_/()')\n")
        new_lines.append("    return safe_chars[:500]\n")
        continue
    
    # Skip until we hit the next function definition or class
    if skip_next:
        if line.strip().startswith('def ') or line.strip().startswith('class '):
            skip_next = False
            new_lines.append(line)
        else:
            continue # Discard old broken lines
            
    new_lines.append(line)

with open('village/server.py', 'w') as f:
    f.writelines(new_lines)

print("✅ SANITIZER REPLACED WITH FOOLPROOF VERSION.")
