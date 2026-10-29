import json
import sys
import os

# Add current directory to path so imports work from root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from triage.baselines import predict
    from triage.slots import extract_slots
except ImportError:
    from baselines import predict
    from slots import extract_slots

# If confidence is below 45%, the AI refuses to guess.
CONFIDENCE_THRESHOLD = 0.45 

def triage_with_abstention(text):
    """
    The final safety gate. 
    1. Gets AI intent and slots.
    2. Checks confidence.
    3. Abstains if unsure, Accepts if confident.
    """
    intent_result = predict(text)
    slots = extract_slots(text)
    
    labels = intent_result.get("labels", [])
    scores = intent_result.get("scores", {})
    
    # Find the highest confidence score
    max_conf = max(scores.values()) if scores else 0.0
    
    # GATE: If confidence is too low, or no labels found -> ABSTAIN
    if max_conf < CONFIDENCE_THRESHOLD or not labels:
        return {
            "action": "ABSTAIN",
            "risk": "HIGH",
            "confidence": round(max_conf, 3),
            "fallback_reason": "Confidence below threshold. Falling back to pictogram menu.",
            "intent": intent_result,
            "slots": slots
        }
        
    # Otherwise -> ACCEPT and route
    return {
        "action": "ACCEPT",
        "risk": "LOW",
        "confidence": round(max_conf, 3),
        "labels": labels,
        "intent": intent_result,
        "slots": slots
    }

if __name__ == "__main__":
    text = sys.argv[1] if len(sys.argv) > 1 else "um... I need help with something maybe..."
    print(json.dumps(triage_with_abstention(text), indent=2))
