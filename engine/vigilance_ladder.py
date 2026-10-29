"""
The 24/48 Vigilance Ladder & Public Exposure Protocol
Automates the escalation of corruption flags from Local -> District -> State/Public.
"""
from datetime import datetime, timedelta
import json

def evaluate_vigilance_ladder(flagged_cases):
    """
    Evaluates unresolved corruption flags and assigns them an escalation tier.
    Tier 1: < 24h (Local Block Officer)
    Tier 2: 24h - 48h (District Magistrate)
    Tier 3: > 48h (State Vigilance + PUBLIC EXPOSURE)
    """
    ladder_status = {
        "tier_1_local": [],
        "tier_2_district": [],
        "tier_3_public_exposure": []
    }
    
    now = datetime.now()
    
    for case in flagged_cases:
        flagged_at = datetime.fromisoformat(case["flagged_at"])
        hours_elapsed = (now - flagged_at).total_seconds() / 3600
        
        if hours_elapsed >= 48:
            # TIER 3: STATE + PUBLIC
            case["current_owner"] = "State Vigilance Commission"
            case["visibility"] = "PUBLIC_RECORD"
            case["action"] = "Exposed on Public Dashboard & State Portal"
            ladder_status["tier_3_public_exposure"].append(case)
            
        elif hours_elapsed >= 24:
            # TIER 2: DISTRICT
            case["current_owner"] = "District Magistrate (DM)"
            case["visibility"] = "RESTRICTED_DISTRICT"
            case["action"] = "Auto-Escalated to DM Office"
            ladder_status["tier_2_district"].append(case)
            
        else:
            # TIER 1: LOCAL
            case["current_owner"] = "Block Development Officer"
            case["visibility"] = "INTERNAL"
            case["action"] = "24h SLA Active"
            ladder_status["tier_1_local"].append(case)
            
    return ladder_status

if __name__ == "__main__":
    # Simulate 3 corruption flags with different timestamps
    mock_flags = [
        {"case_id": "CORR-001", "type": "Mass Rejections (Patwari)", "flagged_at": (datetime.now() - timedelta(hours=12)).isoformat()},
        {"case_id": "CORR-002", "type": "Whistleblower Route D (Sarpanch Bribe)", "flagged_at": (datetime.now() - timedelta(hours=30)).isoformat()},
        {"case_id": "CORR-003", "type": "Ghost Beneficiary Fraud", "flagged_at": (datetime.now() - timedelta(hours=55)).isoformat()},
    ]
    
    result = evaluate_vigilance_ladder(mock_flags)
    
    print("🚨 VIGILANCE LADDER STATUS 🚨")
    print(f"Tier 1 (Local <24h): {len(result['tier_1_local'])} cases")
    print(f"Tier 2 (District 24-48h): {len(result['tier_2_district'])} cases")
    print(f"Tier 3 (STATE & PUBLIC >48h): {len(result['tier_3_public_exposure'])} cases EXPOSED")
    
    if result['tier_3_public_exposure']:
        print("\n📢 PUBLIC EXPOSURE BOARD:")
        for case in result['tier_3_public_exposure']:
            print(f" - [{case['case_id']}] {case['type']} -> EXPOSED TO STATE & PUBLIC")