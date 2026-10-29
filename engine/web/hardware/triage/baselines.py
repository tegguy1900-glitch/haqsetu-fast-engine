from __future__ import annotations

import argparse
import json
import re
from typing import Any


ROUTES = ["crop_loss", "wage_work", "grievance"]


KEYWORD_RULES: dict[str, list[str]] = {
    "crop_loss": [
        "crop",
        "crops",
        "crop loss",
        "crop damage",
        "damaged crop",
        "crop damaged",
        "crop destroyed",
        "flood",
        "flooded",
        "rain",
        "heavy rain",
        "hail",
        "hailstorm",
        "drought",
        "insurance",
        "crop insurance",
        "pmfby",
        "fasal",
        "fasal bima",
        "kharab",
        "kharif",
        "rabi",
        "field",
        "farm",
        "farmer",
    ],
    "wage_work": [
        "work",
        "wage",
        "wages",
        "employment",
        "job",
        "job card",
        "jobcard",
        "mgnrega",
        "nrega",
        "rozgar",
        "majdoori",
        "mazdoori",
        "labour",
        "labor",
        "payment",
        "wage work",
        "demand work",
        "work demand",
    ],
    "grievance": [
        "complaint",
        "grievance",
        "delay",
        "delayed",
        "denied",
        "rejection",
        "rejected",
        "not received",
        "not getting",
        "corruption",
        "bribe",
        "officer",
        "official",
        "csc",
        "helpline",
        "shikayat",
        "pension",
        "ration",
        "ayushman",
        "kisan",
        "benefit",
        "scheme",
    ],
}


MENU_OPTIONS = [
    {
        "id": "crop_loss",
        "label": "Crop loss / crop damage",
    },
    {
        "id": "wage_work",
        "label": "Wage work / MGNREGA",
    },
    {
        "id": "grievance",
        "label": "Grievance / delay / denial",
    },
    {
        "id": "other",
        "label": "Something else",
    },
]


TRAINING_EXAMPLES: list[tuple[str, list[str]]] = [
    ("My crop was destroyed by heavy rain", ["crop_loss"]),
    ("Crop damaged due to hailstorm", ["crop_loss"]),
    ("I want to claim crop insurance", ["crop_loss"]),
    ("Fasal kharab ho gayi hai", ["crop_loss"]),
    ("Heavy rain flooded my field", ["crop_loss"]),
    ("I need work under MGNREGA", ["wage_work"]),
    ("I have a job card but no work was given", ["wage_work"]),
    ("Wages for last week's work have not come", ["wage_work"]),
    ("Mujhe majdoori chahiye", ["wage_work"]),
    ("I want to register demand for wage work", ["wage_work"]),
    ("My pension has been delayed for two months", ["grievance"]),
    ("Ration shop did not give my quota", ["grievance"]),
    ("I want to file a complaint against CSC", ["grievance"]),
    ("My application was rejected without reason", ["grievance"]),
    ("Shikayat darj karni hai", ["grievance"]),
    ("Crop loss and no wage work", ["crop_loss", "wage_work"]),
    ("My crop was damaged and I want to complain", ["crop_loss", "grievance"]),
    ("Need work and also want to ask about pension", ["wage_work", "grievance"]),
    (
        "Crop insurance delay and MGNREGA work demand",
        ["crop_loss", "wage_work", "grievance"],
    ),
]


# -------------------------
# Text helper
# -------------------------


def normalize_text(text: str) -> str:
    if text is None:
        return ""

    return str(text).casefold().strip()


# -------------------------
# Baseline 1: keyword rules
# -------------------------


def keyword_baseline(text: str, min_matches: int = 1) -> dict[str, Any]:
    """
    Simple keyword matcher.

    This is the most transparent baseline.
    It is useful as a fallback and as a judge-friendly explanation.
    """
    normalized = normalize_text(text)

    if not normalized:
        return {
            "method": "keyword",
            "labels": [],
            "scores": {},
            "matched_keywords": {},
            "abstain": True,
        }

    matched_keywords: dict[str, list[str]] = {}
    scores: dict[str, float] = {}
    labels: list[str] = []

    for route, keywords in KEYWORD_RULES.items():
        matches = []

        for keyword in keywords:
            pattern = r"\b" + re.escape(keyword.casefold()) + r"\b"

            if re.search(pattern, normalized):
                matches.append(keyword)

        matched_keywords[route] = matches

        # Simple confidence: more matched keywords gives higher score.
        scores[route] = min(1.0, len(matches) / 3.0)

        if len(matches) >= min_matches:
            labels.append(route)

    return {
        "method": "keyword",
        "labels": labels,
        "scores": scores,
        "matched_keywords": matched_keywords,
        "abstain": len(labels) == 0,
    }


# -------------------------
# Baseline 2: pictogram/menu fallback
# -------------------------


def pictogram_menu_baseline(text: str | None = None) -> dict[str, Any]:
    """
    This baseline does not try to guess.

    It is the safe fallback:
    show the citizen a menu or pictogram options.
    """
    return {
        "method": "pictogram_menu",
        "labels": [],
        "scores": {},
        "abstain": True,
        "fallback": True,
        "options": MENU_OPTIONS,
        "text": text,
    }


# -------------------------
# Baseline 3: TF-IDF + Logistic Regression
# -------------------------


try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.multiclass import OneVsRestClassifier
    from sklearn.preprocessing import MultiLabelBinarizer

    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False


def train_tfidf_lr(
    examples: list[tuple[str, list[str]]] | None = None,
) -> dict[str, Any]:
    """
    Train a simple multi-label TF-IDF + Logistic Regression classifier.
    """
    if not HAS_SKLEARN:
        raise RuntimeError(
            "scikit-learn is required for the TF-IDF baseline. "
            "Run: pip install scikit-learn"
        )

    if examples is None:
        examples = TRAINING_EXAMPLES

    texts = [text for text, _ in examples]
    labels = [label_list for _, label_list in examples]

    vectorizer = TfidfVectorizer(
        lowercase=True,
        ngram_range=(1, 2),
        min_df=1,
    )

    mlb = MultiLabelBinarizer(classes=ROUTES)

    X = vectorizer.fit_transform(texts)
    Y = mlb.fit_transform(labels)

    clf = OneVsRestClassifier(
        LogisticRegression(
            max_iter=1000,
            C=1.0,
        )
    )

    clf.fit(X, Y)

    return {
        "method": "tfidf_lr",
        "vectorizer": vectorizer,
        "mlb": mlb,
        "clf": clf,
    }


def tfidf_lr_predict(
    model: dict[str, Any],
    text: str,
    threshold: float = 0.35,
) -> dict[str, Any]:
    """
    Predict route labels with the TF-IDF + Logistic Regression baseline.
    """
    vectorizer = model["vectorizer"]
    mlb = model["mlb"]
    clf = model["clf"]

    X = vectorizer.transform([text])

    probabilities = clf.predict_proba(X)[0]

    scores = {}

    for i, route in enumerate(mlb.classes_):
        scores[route] = float(probabilities[i])

    labels = [route for route, score in scores.items() if score >= threshold]

    return {
        "method": "tfidf_lr",
        "labels": labels,
        "scores": scores,
        "threshold": threshold,
        "abstain": len(labels) == 0,
    }


# -------------------------
# Demo / CLI
# -------------------------


def compare_baselines(text: str, threshold: float = 0.35) -> dict[str, Any]:
    result: dict[str, Any] = {
        "text": text,
        "keyword": keyword_baseline(text),
        "pictogram_menu": pictogram_menu_baseline(text),
    }

    try:
        model = train_tfidf_lr()
        result["tfidf_lr"] = tfidf_lr_predict(model, text, threshold=threshold)
    except Exception as exc:
        result["tfidf_lr"] = {
            "method": "tfidf_lr",
            "error": str(exc),
        }

    return result


def run_demo() -> None:
    sample_texts = [
        "My crop was destroyed by heavy rain",
        "I have a job card but no work was given",
        "My pension is delayed",
        "Crop loss and no wage work",
        "Hello",
        "मुझे मजदूरी चाहिए",
    ]

    for text in sample_texts:
        result = compare_baselines(text)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print("\n" + "-" * 80 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="HaqSetu triage baselines."
    )

    parser.add_argument(
        "--text",
        help="Text to classify.",
    )

    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run sample texts through the baselines.",
    )

    parser.add_argument(
        "--threshold",
        type=float,
        default=0.35,
        help="Confidence threshold for TF-IDF baseline.",
    )

    args = parser.parse_args()

    if args.demo:
        run_demo()
        return

    if not args.text:
        parser.error("Provide --text or --demo.")

    result = compare_baselines(args.text, threshold=args.threshold)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()