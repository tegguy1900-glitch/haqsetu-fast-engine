"""
Symbolic Proof Certificate Generator
Generates formal logic proofs for eligibility decisions, ensuring
transparency and auditability.
"""
import json
from datetime import datetime
from typing import Dict, List, Any
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from rulepack.schema import load_pack

def generate_proof_trace(
    scheme: str,
    citizen_facts: Dict[str, Any],
    rulepack_dir: str = "rulepack/schemes"
) -> Dict[str, Any]:
    """
    Generate a symbolic proof trace for an eligibility decision.
    
    Returns a formal logic proof showing:
    - Which rules were evaluated
    - Which conditions failed
    - Why inclusion is impossible at this node
    - What action is required
    """
    # Load the rule pack
    rule_file = Path(rulepack_dir) / f"{scheme}.yaml"
    if not rule_file.exists():
        return {"error": f"Rule pack not found: {rule_file}"}
    
    pack = load_pack(str(rule_file))
    
    # Evaluate each rule
    proof_steps = []
    matched_rules = []
    failed_rules = []
    
    for rule in pack.rules:
        rule_result = {
            "rule_id": rule.id,
            "description": rule.description,
            "conditions": [],
            "matched": True
        }
        
        for condition in rule.when:
            field = condition.field
            op = condition.op
            expected_value = condition.value
            actual_value = citizen_facts.get(field)
            
            # Evaluate condition
            condition_met = _evaluate_condition(actual_value, op, expected_value)
            
            rule_result["conditions"].append({
                "field": field,
                "operator": op,
                "expected": expected_value,
                "actual": actual_value,
                "met": condition_met
            })
            
            if not condition_met:
                rule_result["matched"] = False
        
        if rule_result["matched"]:
            matched_rules.append(rule_result)
        else:
            failed_rules.append(rule_result)
        
        proof_steps.append(rule_result)
    
    # Generate the proof certificate
    if matched_rules:
        # At least one rule matched -> include
        decision = "INCLUDE"
        justification = f"Matched {len(matched_rules)} rule(s): {[r['rule_id'] for r in matched_rules]}"
        action = "Proceed to next step in workflow"
    else:
        # No rules matched -> escalate
        decision = "ESCALATE"
        missing_fields = set()
        for rule in failed_rules:
            for cond in rule["conditions"]:
                if not cond["met"] and cond["actual"] is None:
                    missing_fields.add(cond["field"])
        
        justification = f"No rules matched. Missing or insufficient: {list(missing_fields)}"
        action = f"Escalate to human review with proof certificate"
    
    # Build the formal proof
    proof_certificate = {
        "certificate_id": f"PROOF-{scheme.upper()}-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "timestamp": datetime.now().isoformat(),
        "scheme": scheme,
        "citizen_facts": citizen_facts,
        "decision": decision,
        "justification": justification,
        "action": action,
        "proof_steps": proof_steps,
        "matched_rules": [r["rule_id"] for r in matched_rules],
        "failed_rules": [r["rule_id"] for r in failed_rules],
        "formal_logic": _generate_formal_logic(matched_rules, failed_rules, citizen_facts)
    }
    
    return proof_certificate

def _evaluate_condition(actual, op: str, expected) -> bool:
    """Evaluate a single condition."""
    if actual is None:
        return False
    
    if op == "eq":
        return actual == expected
    elif op == "ne":
        return actual != expected
    elif op == "gt":
        return actual > expected
    elif op == "gte":
        return actual >= expected
    elif op == "lt":
        return actual < expected
    elif op == "lte":
        return actual <= expected
    elif op == "in":
        return actual in expected
    
    return False

def _generate_formal_logic(matched_rules, failed_rules, facts) -> str:
    """Generate a human-readable formal logic proof."""
    lines = ["FORMAL PROOF:"]
    
    if matched_rules:
        lines.append("  ∃ rule ∈ Rules : rule.matches(facts) = TRUE")
        lines.append("  ∴ decision = INCLUDE")
    else:
        lines.append("  ∀ rule ∈ Rules : rule.matches(facts) = FALSE")
        lines.append("  ∴ decision = ESCALATE")
        lines.append("  Proof: No rule conditions satisfied with given facts")
    
    return "\n".join(lines)

if __name__ == "__main__":
    # Demo: Generate proof for a PM-KISAN case with missing e-KYC
    proof = generate_proof_trace(
        scheme="pm_kisan",
        citizen_facts={
            "ekyc_done": False,  # Missing!
            "bank_seeded": True,
        }
    )
    
    print(json.dumps(proof, indent=2))
    print("\n" + "="*60)
    print(proof["formal_logic"])
    print("="*60)