"""Private OCR review contract tests."""

import hashlib
import json

import pytest

from pitchdeck.ocr.review import (
    ReviewError,
    export_reviewed_cases,
    validate_review_records,
    verify_manifest_payload,
)


def pending_record(**overrides):
    record = {
        "case_id": "sample:p001",
        "source_id": "approved-source",
        "relative_path": "raw/deck.pdf",
        "source_file": "deck.pdf",
        "document_sha256": "a" * 64,
        "page_number": 1,
        "provisional_bucket": "scanned",
        "review_status": "machine_draft_unverified",
        "gold_text": "",
        "gold_numbers": [],
        "gold_headings": [],
        "gold_bullets": [],
        "gold_tables": [],
    }
    record.update(overrides)
    return record


def test_machine_draft_rows_are_valid_but_not_complete() -> None:
    summary = validate_review_records([pending_record()])

    assert summary.reviewed == 0
    assert summary.pending == 1
    assert not summary.complete


def test_reviewed_rows_require_auditable_metadata() -> None:
    with pytest.raises(ReviewError, match="reviewer_id"):
        validate_review_records([pending_record(review_status="reviewed", gold_text="exact text")])


def test_reviewed_rows_export_without_logging_gold_text(tmp_path) -> None:
    row = pending_record(
        review_status="reviewed",
        gold_text="Exact English text",
        reviewer_id="reviewer-1",
        reviewed_at="2026-09-18T10:00:00Z",
    )
    output = tmp_path / "benchmark-cases.jsonl"

    count, digest = export_reviewed_cases([row], output)
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert count == 1
    assert digest == hashlib.sha256(output.read_bytes()).hexdigest()
    assert payload["gold_text"] == "Exact English text"
    assert payload["metadata"]["reviewer_id"] == "reviewer-1"


def test_manifest_hash_is_verified() -> None:
    payload = {"schema_version": 1, "records": [{"case_id": "sample:p001"}]}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    payload["manifest_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    assert verify_manifest_payload(payload) == payload["manifest_sha256"]

    payload["records"][0]["case_id"] = "changed"
    with pytest.raises(ReviewError, match="does not match"):
        verify_manifest_payload(payload)
