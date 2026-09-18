#!/usr/bin/env python3
"""Export only human-reviewed rows into a private BenchmarkCase JSONL file."""

from __future__ import annotations

import argparse
from pathlib import Path

from pitchdeck.ocr.review import (
    ReviewError,
    export_reviewed_cases,
    load_jsonl,
    validate_review_records,
    verify_manifest_file,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=Path, required=True, help="private review JSONL")
    parser.add_argument("--manifest", type=Path, required=True, help="private review manifest")
    parser.add_argument("--output", type=Path, required=True, help="private output JSONL")
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="export reviewed rows even when other rows are still pending",
    )
    args = parser.parse_args()

    try:
        manifest_hash = verify_manifest_file(args.manifest)
        records = load_jsonl(args.records)
        summary = validate_review_records(records)
        count, output_hash = export_reviewed_cases(
            records, args.output, allow_partial=args.allow_partial
        )
    except ReviewError as exc:
        print(f"could not export reviewed cases: {exc}")
        return 2

    print(f"exported reviewed cases: {count}")
    print(f"source manifest sha256: {manifest_hash}")
    print(f"reviewed rows: {summary.reviewed}/{summary.total}")
    print(f"output sha256: {output_hash}")
    print(f"output: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
