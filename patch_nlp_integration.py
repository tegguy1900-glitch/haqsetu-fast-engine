import re

with open('village/server.py', 'r') as f:
    code = f.read()

# 1. Add Import at top
if 'from core.nlp_engine import predict_intent' not in code:
    code = code.replace(
        "from core.parser import parse_user_input, parse_image_input",
        "from core.parser import parse_user_input, parse_image_input\nfrom core.nlp_engine import predict_intent"
    )
    print("✅ Added NLP Import.")

# 2. Replace handle_voice_match function entirely
old_func_pattern = r'(    def handle_voice_match\(self, data\):.*?return)'
new_func_code = '''    def handle_voice_match(self, data):
        raw_text = data.get("text", "").strip()
        if not raw_text:
            self._send_json(400, {"error": "Empty text"})
            return
            
        # USE AI MODEL INSTEAD OF REGEX
        result = predict_intent(raw_text)
        intent = result["intent"]
        conf = result["confidence"]
        
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

if re.search(old_func_pattern, code, re.DOTALL):
    code = re.sub(old_func_pattern, new_func_code, code, flags=re.DOTALL)
    with open('village/server.py', 'w') as f:
        f.write(code)
    print("✅ Server Patched with NLP Logic.")
else:
    print("⚠️ Could not find exact function pattern. Manual check needed.")
