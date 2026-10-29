import re

with open('village/server.py', 'r') as f:
    lines = f.readlines()

# Find the line containing the broken regex
for i, line in enumerate(lines):
    if 'clean = re.sub(r\'[<>\\"\']\', \'\', str(text))' in line or "clean = re.sub(r'[<>\"']", in line:
        # Replace with a safe, simple regex that removes dangerous chars
        lines[i] = "    clean = re.sub(r'[<>\"\\'&]', '', str(text))\n"
        print(f"✅ Fixed Line {i+1}: {lines[i].strip()}")
        break
else:
    print("⚠️ Could not find exact broken line. Checking for partial matches...")
    for i, line in enumerate(lines):
        if 're.sub(r' in line and '[' in line and '<>' in line:
            lines[i] = "    clean = re.sub(r'[<>\"\\'&]', '', str(text))\n"
            print(f"✅ Fixed Partial Match at Line {i+1}")
            break

with open('village/server.py', 'w') as f:
    f.writelines(lines)

print("\n🎉 SANITIZER REGEX FIXED.")
