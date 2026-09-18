"""Tests for the private local review editor's write boundary."""

import json

import pytest

from pitchdeck.ocr.review import ReviewError
from scripts.review_server import update_record


def pending_record() -> dict[str, object]:
    return {
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
        "machine_draft_text": "unverified",
    }


def write_records(tmp_path, row: dict[str, object]) -> object:
    path = tmp_path / "gold-review-records-with-machine-drafts.jsonl"
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    return path


def test_update_rejects_reviewed_row_without_gold_text(tmp_path) -> None:
    path = write_records(tmp_path, pending_record())

    with pytest.raises(ReviewError, match="non-empty gold_text"):
        update_record(path, 0, {"review_status": "reviewed"})


def test_update_rejects_immutable_fields(tmp_path) -> None:
    path = write_records(tmp_path, pending_record())

    with pytest.raises(ReviewError, match="immutable"):
        update_record(path, 0, {"case_id": "changed"})


def test_update_writes_valid_review_atomically(tmp_path) -> None:
    path = write_records(tmp_path, pending_record())

    updated = update_record(
        path,
        0,
        {
            "review_status": "reviewed",
            "gold_text": "Human transcription",
            "reviewer_id": "reviewer-1",
            "reviewed_at": "2026-09-18T10:00:00Z",
        },
    )

    assert updated["review_status"] == "reviewed"
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["gold_text"] == "Human transcription"
    assert stored["case_id"] == "sample:p001"
