# Simulating LangChain RAG with local logic for demo stability
# In production, replace with actual ChromaDB + Llama3/GPT calls

def analyze_eligibility(user_data: dict):
    """
    Checks user profile against scheme rules using Vector Search logic.
    """
    scheme = user_data.get("scheme_id")
    age = user_data.get("age", 0)
    income = user_data.get("income", 0)
    
    eligible = False
    reason = ""
    
    if scheme == "OLD_AGE_PENSION":
        if age >= 60 and income < 10000:
            eligible = True
            reason = "Matches criteria: Age > 60, Income < ₹10k."
        else:
            reason = "Rejected: Age too low or income exceeds limit."
            
    elif scheme == "MGNREGA":
        if income < 5000:
            eligible = True
            reason = "Matches criteria: Below poverty line."
        else:
            reason = "Rejected: Income above threshold."
            
    else:
        reason = "Scheme not recognized by AI Agent."
        
    return {
        "eligible": eligible,
        "reason": reason,
        "confidence_score": 0.95 if eligible else 0.40
    }
