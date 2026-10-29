from __future__ import annotations

import argparse
import json
from typing import Any

try:
    from .intent import classify_intent
    from .slots import extract_slots
except ImportError:
    from intent import classify_intent
    from slots import extract_slots


# -------------------------
# Thresholds
# -------------------------

# If confidence is below this, we ask for confirmation.
DEFAULT_CONFIRM_THRESHOLD = 0.55

# If confidence is below this fraction of the threshold, we abstain fully.
ABSTAIN_FRACTION = 0.60

# Minimum useful text length before we get suspicious.
MIN_USEFUL_LENGTH = 12


# -------------------------
# Conflict detection
# -------------------------


def assess_conflicts(
    intent_labels: list[str],
    slots: dict[str, Any],
) -> list[str]:
    """
    Check whether the intent and the extracted slots contradict
    or leave obvious gaps.

    These are not errors. They are signals that the system should
    ask the citizen or facilitator to confirm.
    """
    conflicts: list[str] = []

    if "crop_loss" in intent_labels:
        if slots.get("crop_name") is None and slots.get("loss_percentage") is None:
            conflicts.append(
                "Intent says crop loss, but no crop name or loss percentage was found."
            )

    if "wage_work" in intent_labels:
        if slots.get("days_since_demand") is None:
            conflicts.append(
                "Intent says wage work, but no time since work demand was found."
            )

    if "grievance" in intent_labels:
        if slots.get("grievance_category") is None:
            conflicts.append(
                "Intent says grievance, but no scheme/category was identified."
            )

    return conflicts


# -------------------------
# Confidence calculation
# -------------------------


def calculate_confidence(
    intent_result: dict[str, Any],
    slots: dict[str, Any],
    text: str,
) -> tuple[float, list[str]]:
    """
    Produce a confidence score from 0 to 1.

    Components:
    - intent score
    - text quality
    - slot coverage
    - conflict penalty
    """
    scores = intent_result.get("scores", {})
    labels = intent_result.get("labels", [])

    # 1. Intent confidence: best route score.
    max_intent_score = max(scores.values()) if scores else 0.0

    # 2. Text quality: very short text is less reliable.
    text_length = len(str(text).strip())
    text_quality = min(1.0, text_length / 50.0)

    # 3. Slot coverage: how many useful slots were extracted.
    extracted_slots = [value for value in slots.values() if value is not None]
    slot_coverage = len(extracted_slots) / max(len(slots), 1)

    # 4. Conflict penalty.
    conflicts = assess_conflicts(labels, slots)
    conflict_penalty = 0.15 * len(conflicts)

    confidence = (
        0.50 * max_intent_score
        + 0.20 * text_quality
        + 0.30 * slot_coverage
    ) - conflict_penalty

    confidence = max(0.0, min(1.0, confidence))

    return confidence, conflicts


# -------------------------
# Main abstention logic
# -------------------------


def triage_with_abstention(
    text: str,
    confirm_threshold: float = DEFAULT_CONFIRM_THRESHOLD,
) -> dict[str, Any]:
    """
    Full triage pipeline:

    text
      -> intent classification
      -> slot extraction
      -> confidence scoring
      -> ACCEPT / CONFIRM / ABSTAIN
    """
    original_text = str(text or "").strip()

    if not original_text:
        return {
            "text": original_text,
            "action": "ABSTAIN",
            "risk": "HIGH",
            "confidence": 0.0,
            "threshold": confirm_threshold,
            "intent": {"labels": [], "scores": {}, "abstain": True},
            "slots": {},
            "conflicts": ["Empty text."],
            "fallback_reason": "No text provided.",
        }

    # Step 1: intent
    intent_result = classify_intent(original_text)

    # Step 2: slots
    slots = extract_slots(original_text)

    # Step 3: confidence
    confidence, conflicts = calculate_confidence(
        intent_result=intent_result,
        slots=slots,
        text=original_text,
    )

    # Step 4: decision
    intent_abstained = intent_result.get("abstain", False)
    abstain_threshold = confirm_threshold * ABSTAIN_FRACTION

    if intent_abstained or confidence < abstain_threshold:
        action = "ABSTAIN"
        risk = "HIGH"
        fallback_reason = (
            "Intent model abstained."
            if intent_abstained
            else "Confidence too low for automatic routing."
        )
    elif confidence < confirm_threshold:
        action = "CONFIRM"
        risk = "MEDIUM"
        fallback_reason = None
    else:
        action = "ACCEPT"
        risk = "LOW"
        fallback_reason = None

    result: dict[str, Any] = {
        "text": original_text,
        "action": action,
        "risk": risk,
        "confidence": round(confidence, 3),
        "threshold": confirm_threshold,
        "intent": {
            "labels": intent_result.get("labels", []),
            "scores": intent_result.get("scores", {}),
            "abstain": intent_result.get("abstain", False),
            "segments": intent_result.get("segments", []),
        },
        "slots": slots,
        "conflicts": conflicts,
    }

    if fallback_reason:
        result["fallback_reason"] = fallback_reason

    if action == "ABSTAIN":
        result["fallback"] = intent_result.get("fallback")

    return result


# -------------------------
# CLI / demo
# -------------------------


def run_demo() -> None:
    sample_texts = [
        # Clear crop-loss case.
        "My wheat crop was destroyed by heavy rain. About 40 percent loss.",
        # Clear wage-work case.
        "I have a job card but no work was given for 15 days.",
        # Combined request.
        "Crop loss and no wage work.",
        # Vague text.
        "I need help with my scheme.",
        # Very short / unclear.
        "Help",
        # Empty-ish.
        "   ",
    ]

    for text in sample_texts:
        result = triage_with_abstention(text)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print("\n" + "-" * 80 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="HaqSetu abstention and selective prediction layer."
    )

    parser.add_argument(
        "--text",
        help="Text to triage.",
    )

    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run sample texts through the abstention pipeline.",
    )

    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_CONFIRM_THRESHOLD,
        help="Confidence threshold for ACCEPT vs CONFIRM.",
    )

    args = parser.parse_args()

    if args.demo:
        run_demo()
        return

    if not args.text:
        parser.error("Provide --text or --demo.")

    result = triage_with_abstention(args.text, confirm_threshold=args.threshold)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()