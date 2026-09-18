"""Validation and export helpers for the private OCR gold-review package.

The review package is deliberately separate from the public benchmark fixtures.
It may contain source paths, machine drafts, and human transcriptions, so these
helpers operate on caller-provided private files and never copy the files into
the repository.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REVIEW_STATUSES = frozenset(
    {"needs_review", "machine_draft_unverified", "reviewed", "rejected"}
)
REVIEW_BUCKETS = frozenset({"born_digital", "scanned", "chart_table", "difficult"})
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ANNOTATION_FIELDS = ("gold_numbers", "gold_headings", "gold_bullets", "gold_tables")


class ReviewError(ValueError):
    """Raised when a private review artifact violates the review contract."""


@dataclass(frozen=True, slots=True)
class ReviewSummary:
    """Small, non-sensitive summary suitable for terminal output."""

    total: int
    status_counts: dict[str, int]
    bucket_counts: dict[str, int]
    reviewed: int
    pending: int
    rejected: int

    @property
    def complete(self) -> bool:
        """Return whether every row is human-reviewed and none is rejected."""

        return self.total > 0 and self.reviewed == self.total and self.rejected == 0


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    """Load a JSONL review file while preserving each row as a mapping."""

    input_path = Path(path)
    try:
        lines = input_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ReviewError(f"could not read review records: {input_path}") from exc

    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ReviewError(f"invalid JSON on line {line_number}") from exc
        if not isinstance(value, dict):
            raise ReviewError(f"review record on line {line_number} must be an object")
        rows.append(value)
    return rows


def _require_text(row: Mapping[str, Any], field: str, index: int) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ReviewError(f"record {index}: {field} must be a non-empty string")
    return value.strip()


def _require_string_list(row: Mapping[str, Any], field: str, index: int) -> None:
    value = row.get(field, [])
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ReviewError(f"record {index}: {field} must be a list of non-empty strings")


def validate_review_records(
    records: Iterable[Mapping[str, Any]], *, expected_count: int | None = None
) -> ReviewSummary:
    """Validate row shape and return a privacy-safe status summary.

    A machine draft is never accepted as gold text. Rows marked ``reviewed``
    must include reviewer identity and timestamp fields so later benchmark
    runs can be audited without relying on notebook cell history.
    """

    rows = list(records)
    if expected_count is not None and len(rows) != expected_count:
        raise ReviewError(
            f"expected {expected_count} review records, found {len(rows)}"
        )

    case_ids: set[str] = set()
    status_counts: Counter[str] = Counter()
    bucket_counts: Counter[str] = Counter()
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, Mapping):
            raise ReviewError(f"record {index}: expected an object")
        case_id = _require_text(row, "case_id", index)
        if case_id in case_ids:
            raise ReviewError(f"record {index}: duplicate case_id: {case_id}")
        case_ids.add(case_id)

        source_id = _require_text(row, "source_id", index)
        _ = source_id  # Keep the required field explicit for readable errors.
        document_sha256 = _require_text(row, "document_sha256", index)
        if not _SHA256.fullmatch(document_sha256):
            raise ReviewError(f"record {index}: document_sha256 must be lowercase SHA-256")
        relative_path = _require_text(row, "relative_path", index)
        if Path(relative_path).is_absolute() or ".." in Path(relative_path).parts:
            raise ReviewError(f"record {index}: relative_path must stay private and relative")
        page_number = row.get("page_number")
        if not isinstance(page_number, int) or page_number < 1:
            raise ReviewError(f"record {index}: page_number must be a positive integer")

        bucket = row.get("provisional_bucket")
        if bucket not in REVIEW_BUCKETS:
            raise ReviewError(f"record {index}: invalid provisional_bucket: {bucket!r}")
        status = row.get("review_status")
        if status not in REVIEW_STATUSES:
            raise ReviewError(f"record {index}: invalid review_status: {status!r}")
        gold_text = row.get("gold_text", "")
        if not isinstance(gold_text, str):
            raise ReviewError(f"record {index}: gold_text must be a string")
        for field in _ANNOTATION_FIELDS:
            _require_string_list(row, field, index)

        if status == "reviewed":
            if not gold_text.strip():
                raise ReviewError(f"record {index}: reviewed rows require non-empty gold_text")
            _require_text(row, "reviewer_id", index)
            _require_text(row, "reviewed_at", index)
        elif gold_text.strip():
            raise ReviewError(
                f"record {index}: gold_text must remain blank until review_status is reviewed"
            )

        status_counts[status] += 1
        bucket_counts[bucket] += 1

    reviewed = status_counts["reviewed"]
    rejected = status_counts["rejected"]
    return ReviewSummary(
        total=len(rows),
        status_counts=dict(sorted(status_counts.items())),
        bucket_counts=dict(sorted(bucket_counts.items())),
        reviewed=reviewed,
        pending=len(rows) - reviewed - rejected,
        rejected=rejected,
    )


def verify_manifest_payload(payload: Mapping[str, Any]) -> str:
    """Verify a manifest's self-hash and return the declared digest."""

    declared = payload.get("manifest_sha256")
    if not isinstance(declared, str) or not _SHA256.fullmatch(declared):
        raise ReviewError("manifest_sha256 must be a lowercase SHA-256 digest")
    canonical_payload = dict(payload)
    canonical_payload.pop("manifest_sha256", None)
    canonical = json.dumps(
        canonical_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    actual = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    if actual != declared:
        raise ReviewError("manifest_sha256 does not match canonical manifest contents")
    return declared


def verify_manifest_file(path: str | Path) -> str:
    """Load and verify a private review manifest."""

    manifest_path = Path(path)
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReviewError(f"could not read review manifest: {manifest_path}") from exc
    if not isinstance(payload, dict):
        raise ReviewError("review manifest must be a JSON object")
    return verify_manifest_payload(payload)


def export_reviewed_cases(
    records: Iterable[Mapping[str, Any]], output_path: str | Path, *, allow_partial: bool = False
) -> tuple[int, str]:
    """Write reviewed rows in the provider-neutral BenchmarkCase JSONL shape.

    The destination must remain private whenever ``gold_text`` is populated.
    The function returns only a row count and output hash; it never logs the
    transcriptions themselves.
    """

    rows = list(records)
    summary = validate_review_records(rows)
    if not allow_partial and not summary.complete:
        raise ReviewError(
            "review is incomplete; finish every row or pass allow_partial=True explicitly"
        )

    exported: list[dict[str, Any]] = []
    for row in rows:
        if row["review_status"] != "reviewed":
            continue
        exported.append(
            {
                "case_id": row["case_id"],
                "source_id": row["source_id"],
                "page_number": row["page_number"],
                "document_ref": row["relative_path"],
                "gold_text": row["gold_text"],
                "language": row.get("language", "en"),
                "gold_numbers": row.get("gold_numbers", []),
                "gold_headings": row.get("gold_headings", []),
                "gold_bullets": row.get("gold_bullets", []),
                "gold_tables": row.get("gold_tables", []),
                "metadata": {
                    "document_sha256": row["document_sha256"],
                    "provisional_bucket": row["provisional_bucket"],
                    "reviewer_id": row["reviewer_id"],
                    "reviewed_at": row["reviewed_at"],
                },
            }
        )

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    content = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in exported
    )
    destination.write_text(content, encoding="utf-8")
    return len(exported), hashlib.sha256(content.encode("utf-8")).hexdigest()
