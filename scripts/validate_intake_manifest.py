#!/usr/bin/env python3
"""Validate a private intake inventory against the source rights manifest."""

from __future__ import annotations

import argparse
from pathlib import Path

from pitchdeck.ingest import IntakeManifest, SourceRegistry


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, required=True, help="source registry JSON")
    parser.add_argument("--intake", type=Path, required=True, help="intake manifest JSON")
    args = parser.parse_args()

    sources = SourceRegistry.from_json(args.sources)
    intake = IntakeManifest.from_json(args.intake)
    intake.validate_against(sources)
    print(
        f"valid intake manifest: {len(intake.records)} records, "
        f"{len(intake.approved_records())} approved"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
