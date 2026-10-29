from __future__ import annotations

import argparse
import json
import re
from typing import Any

try:
    from .baselines import (
        ROUTES,
        keyword_baseline,
        pictogram_menu_baseline,
        train_tfidf_lr,
        tfidf_lr_predict,
    )
except ImportError:
    from baselines import (
        ROUTES,
        keyword_baseline,
        pictogram_menu_baseline,
        train_tfidf_lr,
        tfidf_lr_predict,
    )


_TFIDF_MODEL = None
_TFIDF_MODEL_FAILED = False


SPLIT_REGEX = re.compile(
    r"""
    \b(?:
        and
        | also
        | as\ well\ as
        | plus
        | aur
        | or
        | but
    )\b
    |
    [;,!?]
    |
    और
    """,
    flags=re.IGNORECASE | re.UNICODE | re.VERBOSE,
)


# -------------------------
# Model helper
# -------------------------


def get_tfidf_model() -> dict[str, Any] | None:
    """
    Load and cache the TF-IDF baseline model.
    """
    global _TFIDF_MODEL, _TFIDF_MODEL_FAILED

    if _TFIDF_MODEL_FAILED:
        return None

    if _TFIDF_MODEL is None:
        try:
            _TFIDF_MODEL = train_tfidf_lr()
        except Exception:
            _TFIDF_MODEL_FAILED = True
            return None

    return _TFIDF_MODEL


# -------------------------
# Request splitting
# -------------------------


def split_requests(text: str) -> list[str]:
    """
    Split text into possible separate requests.

    Examples:
        "crop loss and wage work"
        -> ["crop loss", "wage work"]

        "My pension is delayed; also I need work"
        -> ["My pension is delayed", "also I need work"]
    """
    if not text:
        return []

    raw_text = str(text)

    parts = SPLIT_REGEX.split(raw_text)

    cleaned = []

    for part in parts:
        part = part.strip(" \t\n\r.")

        if len(part) < 3:
            continue

        cleaned.append(part)

    unique = []
    seen = set()

    for part in cleaned:
        key = part.casefold()

        if key not in seen:
            seen.add(key)
            unique.append(part)

    if not unique:
        return [raw_text.strip()]

    return unique


# -------------------------
# Confidence helpers
# -------------------------


def _keyword_confidence(matches: list[str]) -> float:
    """
    Convert keyword matches into a transparent confidence score.

    0 matches: 0.0
    1 match:   0.55
    2 matches: 0.80
    3+:        0.95
    """
    count = len(matches)

    if count == 0:
        return 0.0

    if count == 1:
        return 0.55

    if count == 2:
        return 0.80

    return 0.95


def _keyword_scores_from_result(
    keyword_result: dict[str, Any],
) -> tuple[dict[str, float], dict[str, list[str]]]:
    scores: dict[str, float] = {}
    matched: dict[str, list[str]] = {}

    for route in ROUTES:
        matches = keyword_result.get("matched_keywords", {}).get(route, [])
        scores[route] = _keyword_confidence(matches)
        matched[route] = matches

    return scores, matched


def _tfidf_scores(text: str) -> tuple[dict[str, float], str | None]:
    model = get_tfidf_model()

    if model is None:
        return {}, "TF-IDF baseline unavailable."

    try:
        # threshold=-1 means we only want scores, not final labels.
        result = tfidf_lr_predict(model, text, threshold=-1.0)
        return result.get("scores", {}), None
    except Exception as exc:
        return {}, str(exc)


# -------------------------
# Main intent classifier
# -------------------------


def classify_intent(
    text: str,
    threshold: float = 0.60,
    use_tfidf: bool = True,
) -> dict[str, Any]:
    """
    Multi-label intent classification with request splitting.

    Returns labels such as:

        ["crop_loss"]
        ["wage_work"]
        ["crop_loss", "wage_work"]
        ["grievance"]

    If uncertain, it abstains and returns the pictogram/menu fallback.
    """
    original_text = str(text or "").strip()

    if not original_text:
        return {
            "text": original_text,
            "labels": [],
            "scores": {route: 0.0 for route in ROUTES},
            "threshold": threshold,
            "method": "intent_ensemble",
            "abstain": True,
            "segments": [],
            "segment_predictions": [],
            "matched_keywords": {},
            "tfidf_scores": {},
            "fallback": pictogram_menu_baseline(original_text),
        }

    segments = split_requests(original_text)

    # Full-text keyword evidence.
    full_keyword_result = keyword_baseline(original_text)
    full_keyword_scores, full_matched_keywords = _keyword_scores_from_result(
        full_keyword_result
    )

    # Full-text TF-IDF evidence.
    full_tfidf_scores: dict[str, float] = {}
    tfidf_error = None

    if use_tfidf:
        full_tfidf_scores, tfidf_error = _tfidf_scores(original_text)

    # Segment-level predictions help with combined requests.
    segment_predictions = []

    for segment in segments:
        segment_keyword_result = keyword_baseline(segment)
        segment_keyword_scores, segment_matched = _keyword_scores_from_result(
            segment_keyword_result
        )

        segment_tfidf_scores: dict[str, float] = {}

        if use_tfidf:
            segment_tfidf_scores, _ = _tfidf_scores(segment)

        segment_scores: dict[str, float] = {}
        segment_labels: list[str] = []

        for route in ROUTES:
            score = max(
                segment_keyword_scores.get(route, 0.0),
                segment_tfidf_scores.get(route, 0.0),
            )

            segment_scores[route] = round(score, 3)

            if score >= threshold:
                segment_labels.append(route)

        segment_predictions.append(
            {
                "text": segment,
                "labels": segment_labels,
                "scores": segment_scores,
                "matched_keywords": segment_matched,
            }
        )

    # Combine full-text and segment-level evidence.
    final_scores: dict[str, float] = {}
    labels: list[str] = []

    for route in ROUTES:
        base_score = max(
            full_keyword_scores.get(route, 0.0),
            full_tfidf_scores.get(route, 0.0),
        )

        segment_score = max(
            [
                prediction["scores"].get(route, 0.0)
                for prediction in segment_predictions
            ],
            default=0.0,
        )

        score = max(base_score, segment_score)
        final_scores[route] = round(score, 3)

        if score >= threshold:
            labels.append(route)

    abstain = len(labels) == 0

    result: dict[str, Any] = {
        "text": original_text,
        "labels": labels,
        "scores": final_scores,
        "threshold": threshold,
        "method": "intent_ensemble",
        "abstain": abstain,
        "segments": segments,
        "segment_predictions": segment_predictions,
        "matched_keywords": full_matched_keywords,
        "tfidf_scores": full_tfidf_scores,
    }

    if tfidf_error:
        result["tfidf_error"] = tfidf_error

    if abstain:
        result["fallback"] = pictogram_menu_baseline(original_text)

    return result


# -------------------------
# CLI
# -------------------------


def run_demo() -> None:
    sample_texts = [
        "My crop was destroyed by heavy rain",
        "I have a job card but no work was given",
        "My pension is delayed",
        "Crop loss and no wage work",
        "I want to complain about delayed ration",
        "Hello",
        "fasal kharab ho gayi aur majdoori nahi mili",
    ]

    for text in sample_texts:
        result = classify_intent(text)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print("\n" + "-" * 80 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="HaqSetu multi-label intent classifier."
    )

    parser.add_argument(
        "--text",
        help="Text to classify.",
    )

    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run sample texts.",
    )

    parser.add_argument(
        "--threshold",
        type=float,
        default=0.60,
        help="Confidence threshold for labels.",
    )

    parser.add_argument(
        "--no-tfidf",
        action="store_true",
        help="Disable TF-IDF baseline and use keywords only.",
    )

    args = parser.parse_args()

    if args.demo:
        run_demo()
        return

    if not args.text:
        parser.error("Provide --text or --demo.")

    result = classify_intent(
        args.text,
        threshold=args.threshold,
        use_tfidf=not args.no_tfidf,
    )

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()