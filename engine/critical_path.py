"""
Time-To-Benefit-Ready (TTBR) Critical Path Calculator
Calculates the absolute minimum time for benefit delivery, isolating
bureaucratic delay from systemic dependencies.
"""
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any

# Average processing times (in days) for each desk/task
DESK_PROCESSING_TIMES = {
    "csc": 2,           # e-KYC, form filling
    "bank": 15,         # Aadhaar seeding (bank-side delay)
    "panchayat_secretary": 3,  # Local verification
    "patwari": 5,       # Land record checks
    "block_development_officer": 7,  # Block-level approval
    "district_collector": 10, # District escalation
}

# Dependency chains: task -> [prerequisite tasks]
DEPENDENCY_GRAPH = {
    "pm_kisan_seeding": ["ekyc_complete", "bank_account_seeded"],
    "bank_account_seeded": ["ekyc_complete"],
    "pension_approval": ["age_verified", "income_verified", "domicile_verified"],
    "ration_card": ["income_verified", "domicile_verified"],
}

def calculate_ttbr(
    scheme: str,
    current_status: Dict[str, bool],
    start_date: datetime = None
) -> Dict[str, Any]:
    """
    Calculate Time-To-Benefit-Ready with critical path analysis.
    
    Args:
        scheme: The welfare scheme (e.g., "pm_kisan")
        current_status: Dict of completed prerequisites
        start_date: When the process started (default: now)
    
    Returns:
        TTBR analysis with critical path and bottleneck identification
    """
    if start_date is None:
        start_date = datetime.now()
    
    # Get the dependency chain for this scheme
    if scheme == "pm_kisan":
        final_task = "pm_kisan_seeding"
    elif scheme == "pension":
        final_task = "pension_approval"
    elif scheme == "ration_card":
        final_task = "ration_card"
    else:
        return {"error": f"Unknown scheme: {scheme}"}
    
    # Calculate remaining tasks
    remaining_tasks = []
    completed_tasks = [k for k, v in current_status.items() if v]
    
    def get_all_prerequisites(task):
        """Recursively get all prerequisites for a task."""
        if task in completed_tasks:
            return []
        prereqs = DEPENDENCY_GRAPH.get(task, [])
        all_prereqs = []
        for prereq in prereqs:
            if prereq not in completed_tasks:
                all_prereqs.append(prereq)
                all_prereqs.extend(get_all_prerequisites(prereq))
        return list(set(all_prereqs))
    
    remaining_tasks = get_all_prerequisites(final_task)
    if final_task not in completed_tasks:
        remaining_tasks.append(final_task)
    
    # Calculate critical path (longest sequential dependency chain)
    critical_path = []
    max_days = 0
    
    def find_critical_path(task, current_path, current_days):
        nonlocal critical_path, max_days
        
        current_path.append(task)
        
        # Get the desk for this task
        desk = _get_desk_for_task(task)
        days = DESK_PROCESSING_TIMES.get(desk, 3)  # Default 3 days
        current_days += days
        
        # Check if this task has prerequisites
        prereqs = DEPENDENCY_GRAPH.get(task, [])
        if not prereqs or all(p in completed_tasks for p in prereqs):
            # This is a leaf node or all prereqs are done
            if current_days > max_days:
                max_days = current_days
                critical_path = current_path.copy()
        else:
            # Recurse into prerequisites
            for prereq in prereqs:
                if prereq not in completed_tasks:
                    find_critical_path(prereq, current_path.copy(), current_days)
    
    find_critical_path(final_task, [], 0)
    
    # Calculate TTBR
    ttbr_days = max_days
    ttbr_date = start_date + timedelta(days=ttbr_days)
    
    # Identify bottleneck (longest single task)
    bottleneck_task = None
    bottleneck_days = 0
    for task in remaining_tasks:
        desk = _get_desk_for_task(task)
        days = DESK_PROCESSING_TIMES.get(desk, 3)
        if days > bottleneck_days:
            bottleneck_days = days
            bottleneck_task = task
    
    return {
        "scheme": scheme,
        "ttbr_days": ttbr_days,
        "ttbr_date": ttbr_date.isoformat(),
        "critical_path": critical_path,
        "remaining_tasks": remaining_tasks,
        "completed_tasks": completed_tasks,
        "bottleneck": {
            "task": bottleneck_task,
            "desk": _get_desk_for_task(bottleneck_task) if bottleneck_task else None,
            "days": bottleneck_days
        },
        "systemic_delay_days": ttbr_days,  # This is unavoidable
        "analysis": f"Minimum {ttbr_days} days required. {len(remaining_tasks)} tasks remaining."
    }

def _get_desk_for_task(task: str) -> str:
    """Map task to responsible desk."""
    task_desk_map = {
        "ekyc_complete": "csc",
        "bank_account_seeded": "bank",
        "pm_kisan_seeding": "csc",
        "age_verified": "panchayat_secretary",
        "income_verified": "patwari",
        "domicile_verified": "panchayat_secretary",
        "pension_approval": "block_development_officer",
        "ration_card": "csc",
    }
    return task_desk_map.get(task, "csc")

if __name__ == "__main__":
    # Demo: PM-KISAN farmer with e-KYC done but bank not seeded
    result = calculate_ttbr(
        scheme="pm_kisan",
        current_status={
            "ekyc_complete": True,
            "bank_account_seeded": False,
        }
    )
    
    print(json.dumps(result, indent=2, default=str))
    print("\n📊 TTBR Analysis:")
    print(f"   Minimum time to benefit: {result['ttbr_days']} days")
    print(f"   Bottleneck: {result['bottleneck']['task']} ({result['bottleneck']['days']} days)")
    print(f"   Critical path: {' → '.join(result['critical_path'])}")