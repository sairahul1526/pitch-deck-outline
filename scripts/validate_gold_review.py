#!/usr/bin/env python3
"""Validate a private OCR review package without printing its text contents."""

from __future__ import annotations

import argparse
from pathlib import Path

from pitchdeck.ocr.review import (
    ReviewError,
    load_jsonl,
    validate_review_records,
    verify_manifest_file,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=Path, required=True, help="private review JSONL")
    parser.add_argument("--manifest", type=Path, required=True, help="private review manifest")
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="fail unless every record has human-reviewed gold text",
    )
    args = parser.parse_args()

    try:
        manifest_hash = verify_manifest_file(args.manifest)
        records = load_jsonl(args.records)
        summary = validate_review_records(records)
        if args.require_complete and not summary.complete:
            raise ReviewError("review is incomplete")
    except ReviewError as exc:
        print(f"invalid private gold review: {exc}")
        return 2

    print(f"valid private gold review: {summary.total} records")
    print(f"manifest sha256: {manifest_hash}")
    print(f"status counts: {summary.status_counts}")
    print(f"bucket counts: {summary.bucket_counts}")
    print(f"human-reviewed: {summary.reviewed}/{summary.total}")
    print(f"ready for benchmark export: {'yes' if summary.complete else 'no'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
