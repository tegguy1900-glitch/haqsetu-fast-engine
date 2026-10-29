from __future__ import annotations

import argparse
import json
import re
import unicodedata
from datetime import date, datetime
from difflib import SequenceMatcher
from typing import Any


# Common leading titles that should usually not affect name matching.
TITLE_TOKENS = {
    "sh",
    "shri",
    "sri",
    "smt",
    "smta",
    "mrs",
    "mr",
    "ms",
    "miss",
    "kumari",
    "ku",
    "km",
    "late",
    "lata",
    "babu",
    "bhai",
    "devi",
    "devi",
}


DATE_FORMATS = [
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d %b %Y",
    "%d %B %Y",
    "%b %d, %Y",
    "%B %d, %Y",
    "%d %b, %Y",
    "%d %B, %Y",
]


# -------------------------
# Text normalization
# -------------------------


def _clean_text(text: Any) -> str:
    """
    Lowercase, remove punctuation, normalize whitespace.
    """
    if text is None:
        return ""

    text = str(text)
    text = unicodedata.normalize("NFKD", text)
    text = text.lower()

    # Treat dots as spaces so initials become separate tokens.
    text = text.replace(".", " ")

    # Keep letters, numbers, Unicode letters, and whitespace.
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)

    # Collapse multiple spaces.
    text = re.sub(r"\s+", " ", text).strip()

    return text


def normalize_name_tokens(name: Any) -> list[str]:
    """
    Convert a name into clean tokens.

    Example:
        "Late Shri Ramesh Kumar" -> ["ramesh", "kumar"]
    """
    text = _clean_text(name)

    if not text:
        return []

    tokens = text.split()

    # Remove leading titles.
    while tokens and tokens[0] in TITLE_TOKENS:
        tokens.pop(0)

    return tokens


# -------------------------
# Transliteration helpers
# -------------------------


_CANONICAL_REPLACEMENTS = [
    ("ae", "a"),
    ("ee", "i"),
    ("oo", "u"),
    ("ie", "i"),
    ("ei", "i"),
    ("ou", "o"),
    ("y", "i"),
    ("w", "v"),
]


def _canonical_token(token: str) -> str:
    """
    Create a rough phonetic/transliteration canonical form.

    Examples:
        suneeta -> sunit
        sunita  -> sunit
        kumar   -> kumar
        kumara  -> kumar
    """
    token = token.lower()

    for old, new in _CANONICAL_REPLACEMENTS:
        token = token.replace(old, new)

    # Reduce repeated letters, such as "nn" or "tt".
    token = re.sub(r"(.)\1", r"\1", token)

    # Many Indian names optionally end with "a".
    # Example: Kumar / Kumara
    if len(token) > 3 and token.endswith("a"):
        token = token[:-1]

    return token


def _canonical_name(name: Any) -> str:
    tokens = normalize_name_tokens(name)
    return " ".join(_canonical_token(token) for token in tokens)


# -------------------------
# Name scoring
# -------------------------


def _token_similarity(token_a: str, token_b: str) -> float:
    """
    Compare two name tokens.

    Returns a value from 0.0 to 1.0.
    """
    if not token_a or not token_b:
        return 0.0

    if token_a == token_b:
        return 1.0

    canon_a = _canonical_token(token_a)
    canon_b = _canonical_token(token_b)

    if canon_a == canon_b:
        return 0.95

    # Initial matching:
    # "S. Devi" vs "Sunita Devi"
    if len(token_a) == 1 and token_b.startswith(token_a):
        return 0.8

    if len(token_b) == 1 and token_a.startswith(token_b):
        return 0.8

    # Fuzzy similarity on canonical forms.
    ratio = SequenceMatcher(None, canon_a, canon_b).ratio()

    return ratio * 0.9


def _best_token_score(tokens_a: list[str], tokens_b: list[str]) -> float:
    """
    Match tokens from one name to tokens from another name.

    Extra unmatched tokens reduce the score.
    """
    if not tokens_a or not tokens_b:
        return 0.0

    used_b: set[int] = set()
    scores: list[float] = []

    for token_a in tokens_a:
        best_score = 0.0
        best_index = None

        for j, token_b in enumerate(tokens_b):
            if j in used_b:
                continue

            score = _token_similarity(token_a, token_b)

            if score > best_score:
                best_score = score
                best_index = j

        if best_index is not None and best_score >= 0.5:
            used_b.add(best_index)

        scores.append(best_score)

    denominator = max(len(tokens_a), len(tokens_b))

    if denominator == 0:
        return 0.0

    return sum(scores) / denominator


def name_match_score(name_a: Any, name_b: Any) -> dict[str, Any]:
    """
    Compare two names and return a score.

    Score meaning:
        100: exact normalized match
        85+: strong match
        60+: possible match
        below: weak/mismatch
    """
    tokens_a = normalize_name_tokens(name_a)
    tokens_b = normalize_name_tokens(name_b)

    if not tokens_a or not tokens_b:
        return {
            "score": 0,
            "status": "insufficient",
            "normalized_a": None,
            "normalized_b": None,
            "canonical_a": None,
            "canonical_b": None,
        }

    normalized_a = " ".join(tokens_a)
    normalized_b = " ".join(tokens_b)

    canonical_a = _canonical_name(name_a)
    canonical_b = _canonical_name(name_b)

    if normalized_a == normalized_b:
        score = 100
    else:
        candidates = []

        if canonical_a == canonical_b:
            candidates.append(0.95)

        token_score = _best_token_score(tokens_a, tokens_b)
        candidates.append(token_score)

        sorted_a = " ".join(sorted(tokens_a))
        sorted_b = " ".join(sorted(tokens_b))
        sorted_ratio = SequenceMatcher(None, sorted_a, sorted_b).ratio()
        candidates.append(sorted_ratio * 0.9)

        canonical_ratio = SequenceMatcher(None, canonical_a, canonical_b).ratio()
        candidates.append(canonical_ratio * 0.85)

        score = int(round(max(candidates) * 100))

    if score >= 85:
        status = "match"
    elif score >= 60:
        status = "possible"
    elif score >= 35:
        status = "weak"
    else:
        status = "mismatch"

    return {
        "score": score,
        "status": status,
        "normalized_a": normalized_a,
        "normalized_b": normalized_b,
        "canonical_a": canonical_a,
        "canonical_b": canonical_b,
    }


# -------------------------
# DOB parsing and scoring
# -------------------------


def _parse_dob(value: Any) -> tuple[date | None, str]:
    """
    Parse a date of birth value.

    Returns:
        date or None
        precision: "full", "year", or "none"
    """
    if isinstance(value, datetime):
        return value.date(), "full"

    if isinstance(value, date):
        return value, "full"

    if value is None:
        return None, "none"

    text = str(value).strip()

    if not text:
        return None, "none"

    # Year-only value, e.g. "1961"
    if re.fullmatch(r"\d{4}", text):
        year = int(text)
        current_year = date.today().year

        if 1900 <= year <= current_year:
            return date(year, 1, 1), "year"

    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date(), "full"
        except ValueError:
            pass

    return None, "none"


def dob_match_score(dob_a: Any, dob_b: Any) -> dict[str, Any]:
    """
    Compare two dates of birth.

    Supports:
        1961-03-05
        05/03/1961
        5 March 1961
        1961
    """
    date_a, precision_a = _parse_dob(dob_a)
    date_b, precision_b = _parse_dob(dob_b)

    if date_a is None or date_b is None:
        return {
            "score": 0,
            "status": "insufficient",
            "parsed_a": date_a.isoformat() if date_a else None,
            "parsed_b": date_b.isoformat() if date_b else None,
            "precision_a": precision_a,
            "precision_b": precision_b,
        }

    if precision_a == "full" and precision_b == "full":
        if date_a == date_b:
            score = 100
            status = "match"
        elif date_a.year == date_b.year and date_a.month == date_b.month:
            score = 75
            status = "possible"
        elif date_a.year == date_b.year:
            score = 35
            status = "needs_verification"
        else:
            score = 0
            status = "mismatch"

    elif precision_a == "year" and precision_b == "year":
        if date_a.year == date_b.year:
            score = 70
            status = "possible"
        else:
            score = 0
            status = "mismatch"

    else:
        # One side is year-only, the other is full.
        if date_a.year == date_b.year:
            score = 60
            status = "possible"
        else:
            score = 0
            status = "mismatch"

    return {
        "score": score,
        "status": status,
        "parsed_a": date_a.isoformat(),
        "parsed_b": date_b.isoformat(),
        "precision_a": precision_a,
        "precision_b": precision_b,
    }


# -------------------------
# Combined identity matching
# -------------------------


def identity_match_score(
    record_a: dict[str, Any],
    record_b: dict[str, Any],
) -> dict[str, Any]:
    """
    Compare two identity records.

    Expected fields:
        name
        dob

    This returns a combined score, but it should only assist
    human verification. It must not automatically deny anyone.
    """
    name_result = name_match_score(record_a.get("name"), record_b.get("name"))
    dob_result = dob_match_score(record_a.get("dob"), record_b.get("dob"))

    name_score = name_result["score"]
    dob_score = dob_result["score"]

    name_insufficient = name_result["status"] == "insufficient"
    dob_insufficient = dob_result["status"] == "insufficient"

    if name_insufficient and dob_insufficient:
        overall = 0
        status = "insufficient"

    elif name_insufficient:
        # DOB alone is not enough for full identity confirmation.
        overall = int(round(dob_score * 0.8))

        if overall >= 60:
            status = "possible"
        elif overall >= 35:
            status = "needs_verification"
        else:
            status = "mismatch"

    elif dob_insufficient:
        # Name alone is not enough for full identity confirmation.
        overall = int(round(name_score * 0.85))

        if overall >= 85:
            status = "possible"
        elif overall >= 60:
            status = "possible"
        elif overall >= 35:
            status = "needs_verification"
        else:
            status = "mismatch"

    else:
        overall = int(round((0.65 * name_score) + (0.35 * dob_score)))

        if overall >= 85:
            status = "match"
        elif overall >= 60:
            status = "possible"
        elif overall >= 35:
            status = "needs_verification"
        else:
            status = "mismatch"

    return {
        "overall_score": overall,
        "status": status,
        "name": name_result,
        "dob": dob_result,
    }


# -------------------------
# CLI
# -------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="HaqSetu transliteration-aware name and DOB matcher."
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    names_parser = subparsers.add_parser("names", help="Compare two names.")
    names_parser.add_argument("--a", required=True)
    names_parser.add_argument("--b", required=True)

    dob_parser = subparsers.add_parser("dob", help="Compare two dates of birth.")
    dob_parser.add_argument("--a", required=True)
    dob_parser.add_argument("--b", required=True)

    identity_parser = subparsers.add_parser(
        "identity",
        help="Compare name and DOB together.",
    )
    identity_parser.add_argument("--a-name", default=None)
    identity_parser.add_argument("--a-dob", default=None)
    identity_parser.add_argument("--b-name", default=None)
    identity_parser.add_argument("--b-dob", default=None)

    args = parser.parse_args()

    if args.command == "names":
        result = name_match_score(args.a, args.b)

    elif args.command == "dob":
        result = dob_match_score(args.a, args.b)

    elif args.command == "identity":
        result = identity_match_score(
            {
                "name": args.a_name,
                "dob": args.a_dob,
            },
            {
                "name": args.b_name,
                "dob": args.b_dob,
            },
        )

    else:
        parser.error("Unknown command.")
        return

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()