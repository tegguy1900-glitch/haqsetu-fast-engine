"""
Synthetic Village Generator
Creates realistic synthetic villager profiles for testing and simulation.
"""
import random
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any

# Realistic distributions based on rural Indian demographics
AGE_DISTRIBUTION = {
    "young": (18, 35, 0.35),
    "middle": (36, 59, 0.40),
    "senior": (60, 85, 0.25)
}

INCOME_DISTRIBUTION = {
    "bpl": (0, 50000, 0.45),
    "apl_low": (50001, 100000, 0.30),
    "apl_high": (100001, 300000, 0.25)
}

COMMON_ISSUES = [
    ("name_mismatch", 0.15),  # 15% have name spelling issues
    ("missing_ekyc", 0.20),   # 20% haven't done e-KYC
    ("bank_not_seeded", 0.25), # 25% bank not linked
    ("land_record_issue", 0.10), # 10% land record problems
    ("no_issues", 0.30)       # 30% have no issues
]

FIRST_NAMES = ["Ram", "Sita", "Mohan", "Radha", "Krishna", "Lakshmi", "Arjun", "Gita", "Raj", "Priya"]
LAST_NAMES = ["Kumar", "Devi", "Singh", "Sharma", "Yadav", "Verma", "Gupta", "Patel"]

def generate_synthetic_villager(villager_id: int) -> Dict[str, Any]:
    """Generate a single synthetic villager profile."""
    
    # Generate age
    age_group = random.choices(
        list(AGE_DISTRIBUTION.keys()),
        weights=[v[2] for v in AGE_DISTRIBUTION.values()]
    )[0]
    age_min, age_max, _ = AGE_DISTRIBUTION[age_group]
    age = random.randint(age_min, age_max)
    
    # Generate income
    income_group = random.choices(
        list(INCOME_DISTRIBUTION.keys()),
        weights=[v[2] for v in INCOME_DISTRIBUTION.values()]
    )[0]
    income_min, income_max, _ = INCOME_DISTRIBUTION[income_group]
    annual_income = random.randint(income_min, income_max)
    
    # Generate name
    first_name = random.choice(FIRST_NAMES)
    last_name = random.choice(LAST_NAMES)
    full_name = f"{first_name} {last_name}"
    
    # Generate issues
    issue = random.choices(
        [i[0] for i in COMMON_ISSUES],
        weights=[i[1] for i in COMMON_ISSUES]
    )[0]
    
    # Build profile
    profile = {
        "villager_id": f"VIL-{villager_id:04d}",
        "name": full_name,
        "age": age,
        "annual_income_inr": annual_income,
        "haryana_domicile": random.random() < 0.95,  # 95% are domiciled
        "has_ration_card": random.random() < 0.70,   # 70% have ration card
        "ekyc_done": issue != "missing_ekyc",
        "bank_seeded": issue != "bank_not_seeded",
        "name_matches_records": issue != "name_mismatch",
        "land_records_clear": issue != "land_record_issue",
        "receives_other_govt_pension": age >= 60 and random.random() < 0.30,
        "crop_loss_percentage": random.choice([0, 0, 0, 40, 60]) if random.random() < 0.10 else 0,
        "days_since_work_demand": random.randint(0, 30) if random.random() < 0.20 else 0,
        "issue_type": issue
    }
    
    return profile

def generate_synthetic_village(num_villagers: int = 500) -> List[Dict[str, Any]]:
    """Generate a complete synthetic village."""
    villagers = [generate_synthetic_villager(i+1) for i in range(num_villagers)]
    
    # Calculate summary statistics
    summary = {
        "total_population": num_villagers,
        "age_groups": {
            "young (18-35)": sum(1 for v in villagers if 18 <= v["age"] <= 35),
            "middle (36-59)": sum(1 for v in villagers if 36 <= v["age"] <= 59),
            "senior (60+)": sum(1 for v in villagers if v["age"] >= 60),
        },
        "income_groups": {
            "BPL (<50k)": sum(1 for v in villagers if v["annual_income_inr"] < 50000),
            "APL Low (50k-100k)": sum(1 for v in villagers if 50000 <= v["annual_income_inr"] < 100000),
            "APL High (>100k)": sum(1 for v in villagers if v["annual_income_inr"] >= 100000),
        },
        "common_issues": {
            issue: sum(1 for v in villagers if v["issue_type"] == issue)
            for issue, _ in COMMON_ISSUES
        },
        "eligible_for_pension": sum(1 for v in villagers if v["age"] >= 60 and v["annual_income_inr"] < 30000),
        "ekyc_pending": sum(1 for v in villagers if not v["ekyc_done"]),
        "bank_seeding_pending": sum(1 for v in villagers if not v["bank_seeded"]),
    }
    
    return {
        "village_id": f"SYN-VILLAGE-{datetime.now().strftime('%Y%m%d')}",
        "generated_at": datetime.now().isoformat(),
        "summary": summary,
        "villagers": villagers
    }

if __name__ == "__main__":
    # Generate a synthetic village with 500 villagers
    village = generate_synthetic_village(500)
    
    # Save to file
    output_file = "eval/synthetic_village_data.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(village, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Generated synthetic village with {village['summary']['total_population']} villagers")
    print(f"📊 Saved to: {output_file}")
    print("\n📈 Summary Statistics:")
    for key, value in village["summary"].items():
        if isinstance(value, dict):
            print(f"\n{key}:")
            for k, v in value.items():
                print(f"  {k}: {v}")
        else:
            print(f"{key}: {value}")