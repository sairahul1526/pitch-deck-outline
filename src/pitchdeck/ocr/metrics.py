"""Deterministic, dependency-free OCR quality metrics."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

_NUMBER = re.compile(
    r"(?<![A-Za-z])(?:[$€£₹]?\s*\d[\d,]*(?:\.\d+)?(?:\s*[KMBT])?%?)(?![A-Za-z])",
    flags=re.IGNORECASE,
)
_TOKEN = re.compile(r"\w+(?:['’-]\w+)*", flags=re.UNICODE)


def normalize_text(text: str) -> str:
    """Normalize text only for scoring; never mutate the source artifact."""

    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def _sequence_distance(left: list[str], right: list[str]) -> int:
    """Return Levenshtein distance using two rows of O(min(n, m)) memory."""

    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for left_index, left_item in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_item in enumerate(right, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[right_index] + 1,
                    previous[right_index - 1] + (left_item != right_item),
                )
            )
        previous = current
    return previous[-1]


def _error_rate(reference: list[str], candidate: list[str]) -> float:
    if not reference:
        return 0.0 if not candidate else 1.0
    return _sequence_distance(reference, candidate) / len(reference)


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(normalize_text(text))


def character_error_rate(reference: str, candidate: str) -> float:
    """Calculate normalized character error rate in the range [0, infinity)."""

    return _error_rate(list(normalize_text(reference)), list(normalize_text(candidate)))


def word_error_rate(reference: str, candidate: str) -> float:
    """Calculate whitespace/token word error rate."""

    return _error_rate(_tokens(reference), _tokens(candidate))


def token_f1(reference: str, candidate: str) -> float:
    """Calculate token-overlap F1 while respecting duplicate words."""

    from collections import Counter

    expected = Counter(_tokens(reference))
    actual = Counter(_tokens(candidate))
    overlap = sum((expected & actual).values())
    if not expected and not actual:
        return 1.0
    if not overlap:
        return 0.0
    precision = overlap / sum(actual.values())
    recall = overlap / sum(expected.values())
    return 2 * precision * recall / (precision + recall)


def _normal_set(values: Iterable[str]) -> set[str]:
    return {normalize_text(value) for value in values if normalize_text(value)}


def structure_f1(expected: Iterable[str], actual_text: str) -> float | None:
    """Score annotated headings/bullets/tables by exact normalized phrase match."""

    expected_set = _normal_set(expected)
    if not expected_set:
        return None
    actual = normalize_text(actual_text)
    found = {value for value in expected_set if value in actual}
    return len(found) / len(expected_set)


def numeric_f1(expected: Iterable[str], actual_text: str) -> float | None:
    """Score preservation of numeric strings, which is critical for pitch decks."""

    expected_set = _normal_set(expected)
    if not expected_set:
        return None
    actual_set = _normal_set(_NUMBER.findall(actual_text))
    overlap = len(expected_set & actual_set)
    if not overlap:
        return 0.0
    precision = overlap / max(1, len(actual_set))
    recall = overlap / len(expected_set)
    return 2 * precision * recall / (precision + recall)
