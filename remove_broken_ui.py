import re

with open('web_demo/index.html', 'r') as f:
    html = f.read()

# Find and remove the entire <div id="scheme-app">...</div> block
pattern = r'<div id="scheme-app".*?</div>'
html_cleaned = re.sub(pattern, '', html, flags=re.DOTALL)

# Also remove any leftover scripts related to it if they exist separately
# But usually they are inside or appended after. 
# Let's just ensure the file is saved clean.

with open('web_demo/index.html', 'w') as f:
    f.write(html_cleaned)

print("✅ Removed broken 'Interactive Application UI' section.")
