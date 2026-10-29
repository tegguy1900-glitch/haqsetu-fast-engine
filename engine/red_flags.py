"""
The Red Flag Extortion Engine
Analyzes the ledger to identify desks that exhibit patterns of corruption
(high stall rates, high rejection rates, or excessive "needs official decision" delays).
"""
import json
import random
from datetime import datetime

def analyze_corruption_risk(ledger_data=None):
    """
    Simulates an analysis of the Sabha Ledger to find corruption bottlenecks.
    In production, this reads from chain.jsonl and the SQLite DB.
    """
    # Simulated desk statistics from the ledger
    desks = [
        {"desk": "CSC Operator", "total_cases": 120, "stalled": 10, "rejected": 5, "escalated": 2},
        {"desk": "Panchayat Secretary", "total_cases": 85, "stalled": 15, "rejected": 8, "escalated": 5},
        {"desk": "Local Patwari (Land Records)", "total_cases": 45, "stalled": 38, "rejected": 22, "escalated": 18}, # RED FLAG
        {"desk": "Block Development Officer", "total_cases": 60, "stalled": 5, "rejected": 2, "escalated": 1},
    ]
    
    red_flags = []
    
    for d in desks:
        stall_rate = (d["stalled"] / d["total_cases"]) * 100 if d["total_cases"] > 0 else 0
        reject_rate = (d["rejected"] / d["total_cases"]) * 100 if d["total_cases"] > 0 else 0
        
        risk_level = "LOW"
        reason = []
        
        # Thresholds based on governance baselines
        if stall_rate > 50:
            risk_level = "CRITICAL"
            reason.append(f"Extreme Delay ({stall_rate:.0f}% stalled past 48h SLA)")
        elif stall_rate > 30:
            risk_level = "HIGH"
            reason.append(f"Chronic Delay ({stall_rate:.0f}% stalled)")
            
        if reject_rate > 30:
            risk_level = "CRITICAL"
            reason.append(f"Mass Rejections ({reject_rate:.0f}% rejected without clear proof)")
            
        if d["escalated"] > (d["total_cases"] * 0.20):
            risk_level = "CRITICAL"
            reason.append("High Auto-Escalation Rate")
            
        if risk_level in ["HIGH", "CRITICAL"]:
            red_flags.append({
                "desk": d["desk"],
                "risk_level": risk_level,
                "stall_rate": round(stall_rate, 1),
                "reject_rate": round(reject_rate, 1),
                "reasons": reason,
                "action_required": "Trigger Block-Level Audit & Ghost Callback"
            })
            
    return {
        "timestamp": datetime.now().isoformat(),
        "total_desks_monitored": len(desks),
        "corruption_alerts": len(red_flags),
        "flags": red_flags
    }

if __name__ == "__main__":
    report = analyze_corruption_risk()
    print(json.dumps(report, indent=2))
    
    if report["corruption_alerts"] > 0:
        print("\n🚨 CORRUPTION ALERT 🚨")
        for flag in report["flags"]:
            print(f" - {flag['desk']}: {flag['risk_level']} RISK")
            for r in flag["reasons"]:
                print(f"     -> {r}")