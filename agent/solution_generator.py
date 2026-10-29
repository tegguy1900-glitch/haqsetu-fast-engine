"""
The Empathy Engine (Solution Generator)
Translates cold JSON logic into empathetic, spoken solutions for the villager.
"""
import json

def generate_spoken_solution(scheme: str, outcome: str, facts: dict, ttbr_data: dict = None, proof_data: dict = None) -> str:
    """
    Generates the exact script the AI will speak to the villager.
    """
    script = []
    
    # 1. The Greeting & Acknowledgment
    script.append(f"Namaste. I have reviewed your application for the {scheme.replace('_', ' ').title()} scheme.")
    
    # 2. The Decision
    if outcome == "include":
        script.append("Good news. Based on the documents you provided, you are fully eligible and approved.")
        script.append("I am generating your approval certificate now.")
        
    elif outcome == "needs_official_decision":
        script.append("I cannot approve this instantly because we are missing some required information. But do not worry, I will not reject you. I am escalating this to the Panchayat Secretary for manual review.")
        
        # Use the Proof Trace to explain WHY
        if proof_data and proof_data.get("formal_logic"):
            missing = [cond["field"] for rule in proof_data.get("failed_rules", []) for cond in rule.get("conditions", []) if not cond["met"] and cond["actual"] is None]
            if missing:
                script.append(f"To get approved, you just need to bring your {', '.join(missing).replace('_', ' ')} to the desk.")
                
    else:
        script.append("Your case requires verification. I have logged it securely.")

    # 3. The TTBR (Time-To-Benefit-Ready) Promise
    if ttbr_data and "ttbr_days" in ttbr_data:
        days = ttbr_data["ttbr_days"]
        bottleneck = ttbr_data.get("bottleneck", {}).get("task", "processing")
        script.append(f"Let me be honest about the time. The absolute minimum time for this benefit to reach your bank account is {days} days.")
        script.append(f"The main wait is for the {bottleneck.replace('_', ' ')}. If it takes longer than {days} days, the system will automatically alert the Block Officer.")
        
    # 4. The Next Step (The 1-Visit Plan)
    script.append("I have added this to the public ledger. Your case ID is locked. Is there anything else the Panchayat can help you with today?")
    
    return " ".join(script)

if __name__ == "__main__":
    # Demo: A farmer asking about PM-KISAN
    spoken_text = generate_spoken_solution(
        scheme="pm_kisan",
        outcome="needs_official_decision",
        facts={"ekyc_done": False, "bank_seeded": True},
        ttbr_data={"ttbr_days": 15, "bottleneck": {"task": "bank_account_seeding"}},
        proof_data={"failed_rules": [{"conditions": [{"field": "ekyc_done", "met": False, "actual": None}]}]}
    )
    
    print("\n🗣️ AI AGENT SPEAKS:")
    print("-" * 40)
    print(spoken_text)
    print("-" * 40)