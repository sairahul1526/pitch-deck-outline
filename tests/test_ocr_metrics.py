"""Small deterministic metric tests; these are contract smoke checks."""

from pitchdeck.ocr.metrics import (
    character_error_rate,
    numeric_f1,
    structure_f1,
    token_f1,
    word_error_rate,
)


def test_identical_text_scores_perfectly() -> None:
    text = "Market size: $12.5M\n- Fast onboarding"

    assert character_error_rate(text, text) == 0.0
    assert word_error_rate(text, text) == 0.0
    assert token_f1(text, text) == 1.0


def test_numeric_and_structure_metrics_are_case_insensitive() -> None:
    candidate = "MARKET SIZE: $12.5M\n- Fast onboarding"

    assert numeric_f1(["$12.5M"], candidate) == 1.0
    assert structure_f1(["Market size: $12.5M"], candidate) == 1.0


def test_missing_numeric_annotation_is_not_scored() -> None:
    assert numeric_f1([], "No statistics provided") is None
