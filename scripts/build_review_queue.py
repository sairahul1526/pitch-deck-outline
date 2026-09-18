#!/usr/bin/env python3
# ruff: noqa: E501
"""Build a private, local visual queue for human OCR review.

The generated directory is intentionally ignored by Git. It contains rendered
source pages and machine drafts, but never creates human gold annotations.
Serve the output directory locally (for example with ``python -m http.server``)
so a reviewer can compare each page with its unverified machine draft.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
import subprocess
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pypdf import PdfReader

BUCKET_SPECS: tuple[tuple[str, Callable[[dict[str, Any]], bool], int], ...] = (
    ("born_digital", lambda row: row["native_characters"] >= 200, 20),
    ("scanned", lambda row: row["native_characters"] == 0, 15),
    ("chart_table", lambda row: 40 <= row["native_characters"] < 200, 10),
    ("difficult", lambda row: 0 < row["native_characters"] < 40, 5),
)


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of a source document."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _valid_pdfs(root: Path) -> list[tuple[str, Path]]:
    """Collect valid PDFs from the two approved public source snapshots."""

    sources = (
        ("awesome-pitch-decks", root / "raw" / "awesome-pitch-decks" / "pdfs"),
        (
            "pitch-deckz",
            root / "raw" / "huggingface" / "skyforclouds__pitch-deckz" / "files",
        ),
    )
    pdfs: list[tuple[str, Path]] = []
    for source_id, directory in sources:
        for path in sorted(directory.glob("*.pdf")):
            if path.name.startswith("._"):
                continue
            try:
                if path.open("rb").read(5) == b"%PDF-":
                    pdfs.append((source_id, path))
            except OSError:
                continue
    return pdfs


def collect_candidates(data_root: Path) -> list[dict[str, Any]]:
    """Extract page-level native drafts from locally downloaded PDFs."""

    candidates: list[dict[str, Any]] = []
    for source_id, path in _valid_pdfs(data_root):
        document_hash = sha256_file(path)
        try:
            reader = PdfReader(str(path))
            for page_number, page in enumerate(reader.pages, start=1):
                draft_text = (page.extract_text() or "").strip()
                candidates.append(
                    {
                        "source_id": source_id,
                        "relative_path": str(path.relative_to(data_root)),
                        "source_file": path.name,
                        "document_sha256": document_hash,
                        "page_number": page_number,
                        "native_characters": len(draft_text),
                        "native_draft_text": draft_text,
                    }
                )
        except Exception as error:  # pragma: no cover - malformed PDFs vary by source.
            print(f"skip {path.name}: {type(error).__name__}")
    return candidates


def select_review_records(
    candidates: list[dict[str, Any]], target_count: int = 50
) -> list[dict[str, Any]]:
    """Select a deterministic, bucket-balanced page sample without gold labels."""

    selected: list[dict[str, Any]] = []
    selected_keys: set[tuple[str, int]] = set()
    for bucket, predicate, target in BUCKET_SPECS:
        eligible = sorted(
            (row for row in candidates if predicate(row)),
            key=lambda row: hashlib.sha256(
                f"{row['document_sha256']}:{row['page_number']}".encode()
            ).hexdigest(),
        )
        for candidate in eligible:
            key = (candidate["document_sha256"], candidate["page_number"])
            if key in selected_keys:
                continue
            row = dict(candidate)
            row.update(
                {
                    "case_id": (
                        f"{row['source_id']}:{row['document_sha256'][:12]}:"
                        f"p{row['page_number']:03d}"
                    ),
                    "provisional_bucket": bucket,
                    "review_status": "machine_draft_unverified",
                    "gold_text": "",
                    "gold_numbers": [],
                    "gold_headings": [],
                    "gold_bullets": [],
                    "gold_tables": [],
                    "machine_draft_text": row["native_draft_text"],
                    "machine_draft_engine": "pypdf-native",
                    "machine_draft_status": "drafted" if row["native_draft_text"] else "empty",
                }
            )
            selected.append(row)
            selected_keys.add(key)
            if sum(item["provisional_bucket"] == bucket for item in selected) >= target:
                break
    selected.sort(key=lambda row: (row["source_id"], row["source_file"], row["page_number"]))
    return selected[:target_count]


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value)


def render_page(source: Path, page_number: int, output_path: Path) -> None:
    """Render one PDF page with the system ``pdftoppm`` binary."""

    if shutil.which("pdftoppm") is None:
        raise RuntimeError("pdftoppm is required to render the local review queue")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    prefix = output_path.with_suffix("")
    subprocess.run(
        [
            "pdftoppm",
            "-f",
            str(page_number),
            "-l",
            str(page_number),
            "-singlefile",
            "-jpeg",
            "-r",
            "100",
            str(source),
            str(prefix),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    generated = prefix.with_suffix(".jpg")
    if generated != output_path:
        generated.replace(output_path)


def write_queue(data_root: Path, output_root: Path, records: list[dict[str, Any]]) -> Path:
    """Render records and write private JSONL, manifest, and HTML artifacts."""

    output_root.mkdir(parents=True, exist_ok=True)
    rendered_root = output_root / "rendered"
    rendered_root.mkdir(parents=True, exist_ok=True)
    cards: list[str] = []
    render_status: Counter[str] = Counter()
    for index, row in enumerate(records, start=1):
        image_name = f"{index:03d}_{_safe_name(row['case_id'])}.jpg"
        image_path = rendered_root / image_name
        source_path = data_root / row["relative_path"]
        try:
            render_page(source_path, row["page_number"], image_path)
            render_status["rendered"] += 1
            image_markup = (
                f'<img src="rendered/{html.escape(image_name)}" '
                'alt="Source page" loading="lazy">'
            )
        except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
            render_status["render_failed"] += 1
            image_markup = (
                f"<p class='error'>Render failed: "
                f"{html.escape(type(error).__name__)}</p>"
            )

        draft = row.get("machine_draft_text") or "[empty machine draft]"
        cards.append(
            f"""<details class="case" id="case-{index:03d}">
<summary><strong>{index:03d}. {html.escape(row['source_file'])}</strong> — page {row['page_number']} — bucket {html.escape(row['provisional_bucket'])} — {html.escape(row['machine_draft_status'])}</summary>
<div class="grid"><section><h3>Source page</h3>{image_markup}</section>
<section><h3>Machine draft (unverified)</h3><pre>{html.escape(draft)}</pre>
<p class="warning">Do not treat this draft as gold. Review the source page and edit the private JSONL record.</p></section></div>
<p><code>{html.escape(row['case_id'])}</code></p></details>"""
        )

    records_path = output_root / "gold-review-records-with-machine-drafts.jsonl"
    records_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in records),
        encoding="utf-8",
    )
    manifest = {
        "schema_version": 1,
        "evidence_scope": "local_private_visual_review_queue",
        "records_path": str(records_path.relative_to(data_root)),
        "pages": len(records),
        "render_status_counts": dict(sorted(render_status.items())),
        "gold_text_policy": "blank_until_human_review",
        "review_status_policy": "machine_draft_unverified",
    }
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    manifest["manifest_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    (output_root / "gold-review-manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    queue_html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Private pitch-deck OCR review queue</title><style>
body{{font-family:system-ui,-apple-system,sans-serif;max-width:1200px;margin:2rem auto;padding:0 1rem;color:#222}}
.case{{border:1px solid #bbb;border-radius:8px;margin:1rem 0;padding:.75rem;background:#fafafa}}
summary{{cursor:pointer;font-size:1.05rem}} .grid{{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:1rem;margin-top:1rem}}
section{{background:#fff;border:1px solid #ddd;border-radius:6px;padding:.75rem}} img{{max-width:100%;height:auto;display:block}}
pre{{white-space:pre-wrap;max-height:24rem;overflow:auto;background:#f4f4f4;padding:.75rem;border-radius:4px}}
.warning{{color:#8a3b00;background:#fff4e5;padding:.6rem;border-radius:4px}} .error{{color:#9b1c1c}} code{{font-size:.8rem;color:#555}}
@media(max-width:800px){{.grid{{grid-template-columns:1fr}}}}</style></head><body>
<h1>Private pitch-deck OCR review queue</h1><p><strong>Scope:</strong> {len(records)} pages; machine drafts are unverified.</p>
<p><strong>Important:</strong> this local queue is a visual aid only. Gold text and reviewer fields remain blank until a human review. Edit <code>{html.escape(records_path.name)}</code> in this private directory; do not commit it or copy private text to GitHub.</p>
{''.join(cards)}</body></html>"""
    queue_path = output_root / "review_queue.html"
    queue_path.write_text(queue_html, encoding="utf-8")
    return queue_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--output-root", type=Path, default=Path("data/interim/gold-review"))
    parser.add_argument("--target-count", type=int, default=50)
    args = parser.parse_args()

    candidates = collect_candidates(args.data_root)
    records = select_review_records(candidates, target_count=args.target_count)
    if len(records) != args.target_count:
        raise SystemExit(f"only selected {len(records)} of {args.target_count} requested pages")
    queue_path = write_queue(args.data_root, args.output_root, records)
    counts = Counter(row["provisional_bucket"] for row in records)
    print(f"candidate pages scanned: {len(candidates)}")
    print(f"selected pages: {len(records)}")
    print(f"bucket counts: {dict(sorted(counts.items()))}")
    print(f"review queue: {queue_path}")
    print("gold text written: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
