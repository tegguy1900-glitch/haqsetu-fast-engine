from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from typing import Any, Sequence


# =========================================================
# Basic classification metrics
# =========================================================


def accuracy(y_true: Sequence[Any], y_pred: Sequence[Any]) -> float:
    if not y_true:
        return 0.0

    correct = sum(1 for t, p in zip(y_true, y_pred) if t == p)
    return correct / len(y_true)


def _per_class_counts(
    y_true: Sequence[Any],
    y_pred: Sequence[Any],
    labels: Sequence[Any],
) -> dict[Any, dict[str, int]]:
    counts: dict[Any, dict[str, int]] = {
        label: {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
        for label in labels
    }

    for t, p in zip(y_true, y_pred):
        for label in labels:
            true_is_label = t == label
            pred_is_label = p == label

            if true_is_label and pred_is_label:
                counts[label]["tp"] += 1
            elif pred_is_label and not true_is_label:
                counts[label]["fp"] += 1
            elif true_is_label and not pred_is_label:
                counts[label]["fn"] += 1
            else:
                counts[label]["tn"] += 1

    return counts


def precision_recall_f1(
    y_true: Sequence[Any],
    y_pred: Sequence[Any],
    labels: Sequence[Any],
    average: str = "macro",
) -> dict[str, Any]:
    counts = _per_class_counts(y_true, y_pred, labels)

    per_label: dict[str, dict[str, float]] = {}

    precisions = []
    recalls = []
    f1s = []
    supports = []

    for label in labels:
        tp = counts[label]["tp"]
        fp = counts[label]["fp"]
        fn = counts[label]["fn"]

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0

        f1 = (
            (2 * precision * recall / (precision + recall))
            if (precision + recall) > 0
            else 0.0
        )

        support = tp + fn

        per_label[str(label)] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": support,
        }

        precisions.append(precision)
        recalls.append(recall)
        f1s.append(f1)
        supports.append(support)

    if average == "macro":
        macro_precision = sum(precisions) / len(precisions) if precisions else 0.0
        macro_recall = sum(recalls) / len(recalls) if recalls else 0.0
        macro_f1 = sum(f1s) / len(f1s) if f1s else 0.0
    elif average == "weighted":
        total_support = sum(supports) or 1

        macro_precision = sum(p * s for p, s in zip(precisions, supports)) / total_support
        macro_recall = sum(r * s for r, s in zip(recalls, supports)) / total_support
        macro_f1 = sum(f * s for f, s in zip(f1s, supports)) / total_support
    else:
        raise ValueError("average must be 'macro' or 'weighted'")

    return {
        "average": average,
        "precision": macro_precision,
        "recall": macro_recall,
        "f1": macro_f1,
        "per_label": per_label,
    }


def confusion_matrix(
    y_true: Sequence[Any],
    y_pred: Sequence[Any],
    labels: Sequence[Any],
) -> dict[str, Any]:
    label_index = {label: i for i, label in enumerate(labels)}

    matrix = [[0 for _ in labels] for _ in labels]

    for t, p in zip(y_true, y_pred):
        if t in label_index and p in label_index:
            matrix[label_index[t]][label_index[p]] += 1

    return {
        "labels": list(labels),
        "matrix": matrix,
    }


# =========================================================
# Wilson score interval for small samples
# =========================================================


def wilson_interval(
    successes: int,
    total: int,
    z: float = 1.96,
) -> dict[str, float]:
    """
    Wilson score interval for a binomial proportion.

    This is much better than the normal approximation when the
    sample size is small, which is exactly your situation.
    """
    if total <= 0:
        return {"lower": 0.0, "upper": 0.0, "center": 0.0}

    p_hat = successes / total
    z2 = z * z

    denominator = 1 + z2 / total
    centre = (p_hat + z2 / (2 * total)) / denominator
    margin = (z / denominator) * math.sqrt(
        (p_hat * (1 - p_hat) / total) + (z2 / (4 * total * total))
    )

    lower = max(0.0, centre - margin)
    upper = min(1.0, centre + margin)

    return {
        "lower": lower,
        "upper": upper,
        "center": centre,
        "successes": successes,
        "total": total,
    }


# =========================================================
# Risk-coverage for selective prediction / abstention
# =========================================================


def risk_coverage_curve(
    y_true: Sequence[Any],
    y_pred: Sequence[Any],
    confidences: Sequence[float],
    steps: int = 10,
) -> list[dict[str, float]]:
    """
    Build a risk-coverage curve.

    Sort examples by confidence. For each coverage level, keep only
    the top-confidence examples and compute accuracy on them.

    This shows whether abstaining on low-confidence examples improves
    accuracy on the examples you do answer.
    """
    if not y_true or not y_pred or not confidences:
        return []

    if not (len(y_true) == len(y_pred) == len(confidences)):
        raise ValueError("y_true, y_pred, confidences must have equal length")

    triples = sorted(
        zip(confidences, y_true, y_pred),
        key=lambda item: item[0],
        reverse=True,
    )

    n = len(triples)
    curve: list[dict[str, float]] = []

    for i in range(1, steps + 1):
        coverage = i / steps
        k = max(1, int(round(coverage * n)))

        covered = triples[:k]

        correct = sum(1 for _, t, p in covered if t == p)
        acc = correct / len(covered) if covered else 0.0

        curve.append(
            {
                "coverage": coverage,
                "accuracy": acc,
                "covered_count": len(covered),
                "correct_count": correct,
            }
        )

    return curve


def selective_summary(
    y_true: Sequence[Any],
    y_pred: Sequence[Any],
    confidences: Sequence[float],
    threshold: float,
) -> dict[str, Any]:
    """
    Summarize performance when the system only answers examples
    whose confidence is >= threshold.

    This is the practical abstention report.
    """
    if not y_true or not y_pred or not confidences:
        return {
            "threshold": threshold,
            "coverage": 0.0,
            "accuracy": 0.0,
            "answered": 0,
            "abstained": 0,
        }

    answered_true = []
    answered_pred = []
    abstained = 0

    for t, p, c in zip(y_true, y_pred, confidences):
        if c >= threshold:
            answered_true.append(t)
            answered_pred.append(p)
        else:
            abstained += 1

    total = len(y_true)
    answered = len(answered_true)

    coverage = answered / total if total else 0.0
    acc = accuracy(answered_true, answered_pred) if answered else 0.0

    interval = wilson_interval(
        successes=sum(1 for t, p in zip(answered_true, answered_pred) if t == p),
        total=answered,
    )

    return {
        "threshold": threshold,
        "coverage": coverage,
        "accuracy": acc,
        "answered": answered,
        "abstained": abstained,
        "total": total,
        "wilson_interval": interval,
    }


# =========================================================
# Multi-label helpers
# =========================================================


def multilabel_exact_match(
    y_true_sets: Sequence[set],
    y_pred_sets: Sequence[set],
) -> float:
    if not y_true_sets:
        return 0.0

    correct = sum(1 for t, p in zip(y_true_sets, y_pred_sets) if t == p)
    return correct / len(y_true_sets)


def multilabel_micro_f1(
    y_true_sets: Sequence[set],
    y_pred_sets: Sequence[set],
) -> dict[str, float]:
    tp = 0
    fp = 0
    fn = 0

    for t, p in zip(y_true_sets, y_pred_sets):
        tp += len(t & p)
        fp += len(p - t)
        fn += len(t - p)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0

    f1 = (
        (2 * precision * recall / (precision + recall))
        if (precision + recall) > 0
        else 0.0
    )

    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "tp": tp,
        "fp": fp,
        "fn": fn,
    }


# =========================================================
# Word error rate placeholder for speech
# =========================================================


def word_error_rate(reference: str, hypothesis: str) -> dict[str, Any]:
    """
    Simple WER using edit distance over words.

    This is included now so the speech step can reuse it.
    """
    ref_words = reference.split()
    hyp_words = hypothesis.split()

    n = len(ref_words)
    m = len(hyp_words)

    dp = [[0] * (m + 1) for _ in range(n + 1)]

    for i in range(n + 1):
        dp[i][0] = i

    for j in range(m + 1):
        dp[0][j] = j

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if ref_words[i - 1] == hyp_words[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(
                    dp[i - 1][j],
                    dp[i][j - 1],
                    dp[i - 1][j - 1],
                )

    edit_distance = dp[n][m]
    wer = edit_distance / n if n > 0 else 0.0

    return {
        "wer": wer,
        "edit_distance": edit_distance,
        "reference_words": n,
        "hypothesis_words": m,
    }


# =========================================================
# Full report helper
# =========================================================


def classification_report(
    y_true: Sequence[Any],
    y_pred: Sequence[Any],
    labels: Sequence[Any],
    confidences: Sequence[float] | None = None,
    abstain_threshold: float = 0.55,
) -> dict[str, Any]:
    """
    Produce a single honest report suitable for a poster.
    """
    if not y_true:
        return {
            "error": "No examples provided.",
        }

    correct = sum(1 for t, p in zip(y_true, y_pred) if t == p)
    total = len(y_true)

    acc = accuracy(y_true, y_pred)

    interval = wilson_interval(successes=correct, total=total)

    macro = precision_recall_f1(y_true, y_pred, labels, average="macro")
    weighted = precision_recall_f1(y_true, y_pred, labels, average="weighted")
    cm = confusion_matrix(y_true, y_pred, labels)

    report: dict[str, Any] = {
        "total_examples": total,
        "correct": correct,
        "accuracy": acc,
        "accuracy_wilson_95": interval,
        "macro": macro,
        "weighted": weighted,
        "confusion_matrix": cm,
    }

    if confidences is not None:
        selective = selective_summary(
            y_true=y_true,
            y_pred=y_pred,
            confidences=confidences,
            threshold=abstain_threshold,
        )

        curve = risk_coverage_curve(
            y_true=y_true,
            y_pred=y_pred,
            confidences=confidences,
            steps=10,
        )

        report["selective_prediction"] = selective
        report["risk_coverage_curve"] = curve

    return report


# =========================================================
# CLI / demo
# =========================================================


def run_demo() -> None:
    # Small fake example, intentionally tiny.
    labels = ["crop_loss", "wage_work", "grievance"]

    y_true = [
        "crop_loss",
        "crop_loss",
        "wage_work",
        "wage_work",
        "grievance",
        "crop_loss",
        "wage_work",
        "grievance",
        "crop_loss",
        "grievance",
    ]

    y_pred = [
        "crop_loss",
        "crop_loss",
        "wage_work",
        "grievance",
        "grievance",
        "crop_loss",
        "wage_work",
        "grievance",
        "wage_work",
        "grievance",
    ]

    confidences = [
        0.95,
        0.88,
        0.80,
        0.45,
        0.90,
        0.70,
        0.65,
        0.85,
        0.30,
        0.75,
    ]

    report = classification_report(
        y_true=y_true,
        y_pred=y_pred,
        labels=labels,
        confidences=confidences,
        abstain_threshold=0.60,
    )

    print(json.dumps(report, ensure_ascii=False, indent=2))

    # Multi-label example.
    y_true_sets = [
        {"crop_loss"},
        {"crop_loss", "wage_work"},
        {"grievance"},
    ]

    y_pred_sets = [
        {"crop_loss"},
        {"crop_loss"},
        {"grievance", "wage_work"},
    ]

    multilabel = {
        "exact_match": multilabel_exact_match(y_true_sets, y_pred_sets),
        "micro_f1": multilabel_micro_f1(y_true_sets, y_pred_sets),
    }

    print("\nMulti-label example:")
    print(json.dumps(multilabel, ensure_ascii=False, indent=2))

    # WER example for later speech work.
    wer_example = word_error_rate(
        reference="my crop was damaged by rain",
        hypothesis="my crop was damaged by heavy rain",
    )

    print("\nWER example:")
    print(json.dumps(wer_example, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="HaqSetu evaluation metrics with honest intervals."
    )

    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run a small demo report.",
    )

    args = parser.parse_args()

    if args.demo:
        run_demo()
    else:
        parser.error("Use --demo for now. File-based eval comes with the dataset.")


if __name__ == "__main__":
    main()