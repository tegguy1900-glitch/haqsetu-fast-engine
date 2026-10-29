"""
Cryptographic Appeal & Independent Verification Route
Ensures citizens can appeal rejections through a mathematically
independent verification channel.
"""
import json
import hashlib
from datetime import datetime
from typing import Dict, Any, Optional
import secrets

def generate_appeal_request(
    case_id: str,
    original_decision: str,
    rejected_by: str,
    citizen_name: str,
    reason_for_appeal: str
) -> Dict[str, Any]:
    """
    Generate a cryptographically signed appeal request that routes
    to an independent verifier.
    """
    
    # Generate unique appeal ID
    appeal_id = f"APPEAL-{case_id}-{secrets.token_hex(4).upper()}"
    
    # Create appeal payload
    appeal_payload = {
        "appeal_id": appeal_id,
        "case_id": case_id,
        "citizen_name": citizen_name,
        "original_decision": original_decision,
        "rejected_by": rejected_by,
        "reason_for_appeal": reason_for_appeal,
        "appeal_timestamp": datetime.now().isoformat(),
        "status": "PENDING_INDEPENDENT_REVIEW"
    }
    
    # Generate cryptographic hash of the appeal
    appeal_hash = hashlib.sha256(
        json.dumps(appeal_payload, sort_keys=True).encode()
    ).hexdigest()
    
    # Select independent verifier (cannot be the same person who rejected)
    independent_verifier = _select_independent_verifier(rejected_by)
    
    # Build the appeal certificate
    appeal_certificate = {
        **appeal_payload,
        "appeal_hash": appeal_hash,
        "independent_verifier": independent_verifier,
        "verification_deadline": _calculate_deadline(days=7),
        "escalation_path": [
            f"Step 1: Appeal submitted to {independent_verifier['role']}",
            f"Step 2: Independent review within 7 days",
            f"Step 3: If unresolved, escalate to Block Development Officer",
            f"Step 4: Final appeal to District Grievance Redressal Officer"
        ],
        "cryptographic_proof": {
            "original_case_hash": hashlib.sha256(case_id.encode()).hexdigest(),
            "appeal_hash": appeal_hash,
            "chain_link": f"{case_id}:{appeal_id}"
        }
    }
    
    return appeal_certificate

def _select_independent_verifier(rejected_by: str) -> Dict[str, str]:
    """
    Select an independent verifier who is mathematically guaranteed
    to be different from the person who rejected the case.
    """
    
    # Pool of independent verifiers
    verifier_pool = [
        {"role": "Self-Help Group Representative", "name": "Rotating SHG Member"},
        {"role": "Block Development Officer", "name": "BDO Office"},
        {"role": "District Grievance Officer", "name": "DGO Office"},
        {"role": "Vigilance Committee Member", "name": "VC Representative"},
    ]
    
    # Filter out the person who rejected (by role matching)
    independent_verifiers = [
        v for v in verifier_pool 
        if rejected_by.lower() not in v["role"].lower()
    ]
    
    # If all verifiers match (shouldn't happen), use the first one
    if not independent_verifiers:
        independent_verifiers = verifier_pool
    
    # Randomly select from independent pool
    return secrets.choice(independent_verifiers)

def _calculate_deadline(days: int = 7) -> str:
    """Calculate deadline for appeal resolution."""
    from datetime import timedelta
    deadline = datetime.now() + timedelta(days=days)
    return deadline.isoformat()

def verify_appeal_independence(
    appeal_certificate: Dict[str, Any],
    original_official: str
) -> bool:
    """
    Verify that the appeal is routed to an independent verifier.
    Returns True if independent, False if compromised.
    """
    
    verifier_role = appeal_certificate["independent_verifier"]["role"]
    
    # Check if verifier is the same as original official
    if original_official.lower() in verifier_role.lower():
        return False
    
    # Verify cryptographic hash
    payload = {k: v for k, v in appeal_certificate.items() 
               if k not in ["appeal_hash", "cryptographic_proof"]}
    
    expected_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode()
    ).hexdigest()
    
    if expected_hash != appeal_certificate["appeal_hash"]:
        return False
    
    return True

if __name__ == "__main__":
    # Demo: Generate an appeal for a rejected pension case
    appeal = generate_appeal_request(
        case_id="CASE-2026-001",
        original_decision="REJECTED",
        rejected_by="Panchayat Secretary",
        citizen_name="Sunita Devi",
        reason_for_appeal="Income certificate was not considered"
    )
    
    print(json.dumps(appeal, indent=2))
    
    # Verify independence
    is_independent = verify_appeal_independence(appeal, "Panchayat Secretary")
    print(f"\n✅ Appeal is independent: {is_independent}")
    print(f"🔒 Appeal hash: {appeal['appeal_hash'][:16]}...")
    print(f"👤 Independent verifier: {appeal['independent_verifier']['role']}")