import re

with open('village/server.py', 'r') as f:
    code = f.read()

# 1. Add Import at top (after existing imports)
if 'from core.nlp_engine import predict_intent' not in code:
    # Find the last import line before the class definition
    lines = code.split('\n')
    insert_idx = 0
    for i, line in enumerate(lines):
        if line.strip().startswith('import ') or line.strip().startswith('from '):
            insert_idx = i + 1
    
    lines.insert(insert_idx, 'from core.nlp_engine import predict_intent')
    code = '\n'.join(lines)
    print("✅ Added NLP Import.")

# 2. Replace handle_voice_match function
# We look for the exact function signature and replace until the next 'def ' or end of class
pattern = r'(    def handle_voice_match\(self, data\):.*?)(?=\n    def |\Z)'
replacement = '''    def handle_voice_match(self, data):
        raw_text = data.get("text", "").strip()
        if not raw_text:
            self._send_json(400, {"error": "Empty text"})
            return
            
        # USE AI MODEL INSTEAD OF REGEX
        try:
            result = predict_intent(raw_text)
            intent = result["intent"]
            conf = result["confidence"]
        except Exception as e:
            # Fallback to simple keyword matching if AI fails
            print(f"⚠️ NLP Error: {e}. Falling back to keywords.")
            lower_txt = raw_text.lower()
            if "vidhwa" in lower_txt or "widow" in lower_txt:
                intent = "VIDHWA_PENSION"; conf = 0.8
            elif "kaam" in lower_txt or "work" in lower_txt:
                intent = "MGNREGA"; conf = 0.8
            else:
                intent = "UNKNOWN"; conf = 0.0

        schemes = []
        
        # Map Intent to Scheme Objects
        if intent == "MGNREGA":
            schemes.append({"id": "MGNREGA", "name": "MGNREGA Job Card", "can_apply": True})
        elif intent == "OLD_AGE_PENSION":
            schemes.append({"id": "OLD_AGE_PENSION", "name": "Old Age Pension", "can_apply": True, "req_doc": "AGE_PROOF"})
        elif intent == "VIDHWA_PENSION":
            schemes.append({"id": "VIDHWA_PENSION", "name": "Widow Pension", "can_apply": True, "req_doc": "DEATH_CERT"})
        elif intent == "INFRA_BROKEN":
             self._send_json(200, {"intent": "INFRA", "message": f"Detected Infrastructure Issue (Conf: {conf})", "confidence": conf})
             return
        else:
            # Fallback for low confidence or unknown intents
            if conf < 0.6:
                 schemes.append({"id": "NONE", "name": "Low Confidence Match", "can_apply": False})
            else:
                 schemes.append({"id": "GENERAL", "name": "General Inquiry", "can_apply": False})

        self._send_json(200, {"schemes": schemes, "ai_confidence": conf, "detected_intent": intent})'''

if re.search(pattern, code, re.DOTALL):
    code = re.sub(pattern, replacement, code, flags=re.DOTALL)
    with open('village/server.py', 'w') as f:
        f.write(code)
    print("✅ Server Patched with NLP Logic Safely.")
else:
    print("❌ Could not find function pattern. Aborting.")
