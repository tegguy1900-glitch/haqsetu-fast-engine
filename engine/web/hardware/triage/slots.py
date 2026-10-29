from __future__ import annotations

import argparse
import json
import re
from typing import Any


# -------------------------
# Keyword dictionaries
# -------------------------

CROP_KEYWORDS = {
    "wheat": ["wheat", "gehu", "gehun", "गेहूं"],
    "rice": ["rice", "paddy", "chawal", "dhan", "चावल", "धान"],
    "cotton": ["cotton", "kapas", "kapaas", "कपास"],
    "mustard": ["mustard", "sarson", "सरसों"],
    "maize": ["maize", "corn", "makka", "मक्का"],
    "sugarcane": ["sugarcane", "ganna", "गन्ना"],
}

INSURANCE_POSITIVE = [
    "insured", "bima", "policy", "beemit", "covered", "बीमित", "बिमा", "पॉलिसी"
]

INSURANCE_NEGATIVE = [
    "uninsured", "no insurance", "bima nahi", "no policy", "not insured", "बीमा नहीं"
]

GRIEVANCE_CATEGORIES = {
    "pension_delay": ["pension", "pashan", "pension delay", "पेंशन"],
    "ration_denial": ["ration", "rashan", "ration shop", "quota", "राशन"],
    "ayushman_issue": ["ayushman", "hospital", "health card", "treatment", "आयुष्मान"],
    "kisan_issue": ["kisan", "pm kisan", "installment", "किसान"],
}


# -------------------------
# Extraction functions
# -------------------------


def normalize_text(text: str) -> str:
    if text is None:
        return ""
    return str(text).lower().strip()


def extract_crop_name(text: str) -> str | None:
    normalized = normalize_text(text)
    for crop, keywords in CROP_KEYWORDS.items():
        for kw in keywords:
            if kw in normalized:
                return crop
    return None


def extract_insurance_status(text: str) -> bool | None:
    normalized = normalize_text(text)
    
    # Check for negative first, because "not insured" contains "insured"
    for kw in INSURANCE_NEGATIVE:
        if kw in normalized:
            return False
            
    for kw in INSURANCE_POSITIVE:
        if kw in normalized:
            return True
            
    return None


def extract_loss_percentage(text: str) -> float | None:
    normalized = normalize_text(text)
    
    # Pattern 1: "40 percent", "50%", "30 pratishat"
    match = re.search(r'(\d+(?:\.\d+)?)\s*(?:%|percent|pratishat|प्रतिशत)', normalized)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            pass
            
    # Pattern 2: "loss of 40", "kharab 50", "damage is 60"
    match = re.search(
        r'(?:loss|damage|kharab|nuksan|nuqsan|नुकसान)\s*(?:of|is|was|hai)?\s*(\d+(?:\.\d+)?)', 
        normalized
    )
    if match:
        try:
            val = float(match.group(1))
            # Sanity check: percentage usually <= 100
            if val <= 100:
                return val
        except ValueError:
            pass
            
    return None


def extract_days_since_demand(text: str) -> int | None:
    normalized = normalize_text(text)
    
    # Pattern: "15 days", "2 weeks", "10 din"
    match = re.search(r'(\d+)\s*(?:days?|din|दिन)', normalized)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            pass
            
    match = re.search(r'(\d+)\s*(?:weeks?|hafte|सप्ताह|हफ्ते)', normalized)
    if match:
        try:
            return int(match.group(1)) * 7
        except ValueError:
            pass
            
    match = re.search(r'(\d+)\s*(?:months?|mahine|महीने)', normalized)
    if match:
        try:
            return int(match.group(1)) * 30
        except ValueError:
            pass
            
    return None


def extract_grievance_category(text: str) -> str | None:
    normalized = normalize_text(text)
    for category, keywords in GRIEVANCE_CATEGORIES.items():
        for kw in keywords:
            if kw in normalized:
                return category
    return None


# -------------------------
# Main extraction function
# -------------------------


def extract_slots(text: str) -> dict[str, Any]:
    """
    Extract all possible slots from the text.
    Returns a dictionary where missing slots are set to None.
    """
    return {
        "crop_name": extract_crop_name(text),
        "has_insurance": extract_insurance_status(text),
        "loss_percentage": extract_loss_percentage(text),
        "days_since_demand": extract_days_since_demand(text),
        "grievance_category": extract_grievance_category(text),
    }


# -------------------------
# CLI / Demo
# -------------------------


def run_demo() -> None:
    sample_texts = [
        "My wheat crop was destroyed, about 40 percent loss.",
        "I have crop insurance but it's delayed.",
        "Mera gehu kharab ho gaya, bima nahi hai. 50% nuksan.",
        "I applied for wage work 15 days ago but no job card yet.",
        "My old age pension is delayed for 2 months.",
        "The ration shop denied my quota yesterday.",
        "Just saying hello, no specific details."
    ]
    
    for text in sample_texts:
        slots = extract_slots(text)
        print(f"Text: {text}")
        print(json.dumps(slots, ensure_ascii=False, indent=2))
        print("-" * 80)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="HaqSetu slot extraction from citizen text."
    )
    
    parser.add_argument(
        "--text",
        help="Text to extract slots from.",
    )
    
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run sample texts through the extractor.",
    )
    
    args = parser.parse_args()
    
    if args.demo:
        run_demo()
        return
        
    if not args.text:
        parser.error("Provide --text or --demo.")
        
    slots = extract_slots(args.text)
    print(json.dumps(slots, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()