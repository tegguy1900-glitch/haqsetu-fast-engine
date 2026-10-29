import re
import json
import sys

def extract_slots(text):
    text_lower = text.lower()
    slots = {"crop_name": None, "loss_percentage": None, "days_since_demand": None}
    
    crops = {"wheat": ["wheat", "gehu"], "rice": ["rice", "paddy", "chawal"], "cotton": ["cotton", "kapas"]}
    for crop, keywords in crops.items():
        if any(kw in text_lower for kw in keywords):
            slots["crop_name"] = crop
            break
            
    match = re.search(r'(\d+(?:\.\d+)?)\s*(?:%|percent|pratishat)', text_lower)
    if match:
        slots["loss_percentage"] = float(match.group(1))
        
    match = re.search(r'(\d+)\s*(?:days?|din)', text_lower)
    if match:
        slots["days_since_demand"] = int(match.group(1))
        
    return slots

if __name__ == "__main__":
    text = sys.argv[1] if len(sys.argv) > 1 else "My wheat crop was destroyed, about 40 percent loss."
    print(json.dumps(extract_slots(text), indent=2))