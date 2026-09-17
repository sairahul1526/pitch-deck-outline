#!/usr/bin/env python3
"""Download the approved Awesome Pitch Decks index artifacts.

The CSV is treated as an index, not as executable input. Each Google Drive
file ID is validated, downloaded through the public Drive endpoint, checked for
the PDF magic bytes, and recorded with a local SHA-256 digest. Raw PDFs remain
under ``data/raw/`` and are ignored by Git.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import hashlib
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

_DRIVE_ID = re.compile(r"^[A-Za-z0-9_-]{10,}$")
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True, slots=True)
class DownloadRecord:
    """One index row and the resulting local artifact state."""

    display_name: str
    company_name: str
    year: str
    round: str
    drive_id: str
    local_path: str
    status: str
    byte_size: int | None = None
    sha256: str | None = None
    error: str | None = None


def _drive_id(value: str) -> str:
    parsed = urlparse(value)
    match = re.search(r"/d/([^/]+)", parsed.path)
    candidate = match.group(1) if match else parse_qs(parsed.query).get("id", [""])[0]
    if not _DRIVE_ID.fullmatch(candidate):
        raise ValueError(f"could not validate Google Drive file ID: {value}")
    return candidate


def _safe_filename(display_name: str, drive_id: str) -> str:
    stem = _SAFE_NAME.sub("-", display_name).strip("-.") or "deck"
    return f"{stem}--{drive_id[:8]}.pdf"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _has_pdf_header(path: Path) -> bool:
    with path.open("rb") as handle:
        return handle.read(5) == b"%PDF-"


def _download_with_curl(url: str, temporary: Path) -> tuple[bool, str]:
    command = [
        "curl",
        "--fail",
        "--location",
        "--retry",
        "3",
        "--connect-timeout",
        "20",
        "--max-time",
        "180",
        "--silent",
        "--show-error",
        "--output",
        str(temporary),
        url,
    ]
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if completed.returncode == 0:
        return True, ""
    return False, completed.stderr.strip() or f"curl exited {completed.returncode}"


def _virus_scan_confirmation_url(temporary: Path, drive_id: str) -> str | None:
    """Extract Drive's explicit 'Download anyway' token from its warning page."""

    try:
        page = temporary.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    match = re.search(r'name="uuid"\s+value="([^"]+)"', page)
    if not match:
        return None
    query = urlencode(
        {"id": drive_id, "export": "download", "confirm": "t", "uuid": match.group(1)}
    )
    return f"https://drive.usercontent.google.com/download?{query}"


def _download(row: dict[str, str], output_dir: Path) -> DownloadRecord:
    display_name = row["display_name"].strip()
    drive_id = _drive_id(row["google_drive_link"])
    destination = output_dir / _safe_filename(display_name, drive_id)
    temporary = destination.with_suffix(destination.suffix + ".part")
    if destination.exists() and _has_pdf_header(destination):
        return DownloadRecord(
            display_name=display_name,
            company_name=row["company_name"],
            year=row["year"],
            round=row["round"],
            drive_id=drive_id,
            local_path=str(destination),
            status="existing",
            byte_size=destination.stat().st_size,
            sha256=_sha256(destination),
        )

    url = f"https://drive.usercontent.google.com/download?id={drive_id}&export=download"
    try:
        downloaded, message = _download_with_curl(url, temporary)
        if not downloaded:
            return DownloadRecord(
                display_name=display_name,
                company_name=row["company_name"],
                year=row["year"],
                round=row["round"],
                drive_id=drive_id,
                local_path=str(destination),
                status="error",
                error=message[:500],
            )
        if not _has_pdf_header(temporary):
            confirmation_url = _virus_scan_confirmation_url(temporary, drive_id)
            if confirmation_url is not None:
                downloaded, message = _download_with_curl(confirmation_url, temporary)
            if not downloaded or not _has_pdf_header(temporary):
                if downloaded:
                    message = "download did not begin with a PDF magic header"
                else:
                    message = message or "Google Drive confirmation download failed"
                return DownloadRecord(
                    display_name=display_name,
                    company_name=row["company_name"],
                    year=row["year"],
                    round=row["round"],
                    drive_id=drive_id,
                    local_path=str(destination),
                    status="error",
                    error=message,
                )
        temporary.replace(destination)
        return DownloadRecord(
            display_name=display_name,
            company_name=row["company_name"],
            year=row["year"],
            round=row["round"],
            drive_id=drive_id,
            local_path=str(destination),
            status="downloaded",
            byte_size=destination.stat().st_size,
            sha256=_sha256(destination),
        )
    except OSError as exc:
        return DownloadRecord(
            display_name=display_name,
            company_name=row["company_name"],
            year=row["year"],
            round=row["round"],
            drive_id=drive_id,
            local_path=str(destination),
            status="error",
            error=str(exc)[:500],
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--index",
        type=Path,
        default=Path("data/raw/awesome-pitch-decks/metadata/deck_index.csv"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/raw/awesome-pitch-decks/pdfs"),
    )
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    if args.workers < 1 or args.workers > 32:
        parser.error("--workers must be between 1 and 32")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    with args.index.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    required = {"company_name", "display_name", "year", "round", "google_drive_link"}
    if not rows or not required.issubset(rows[0]):
        parser.error(f"index must contain columns: {sorted(required)}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        records = list(pool.map(lambda row: _download(row, args.output_dir), rows))
    records.sort(key=lambda record: (record.display_name, record.drive_id))
    manifest = {
        "schema_version": 1,
        "source": "https://github.com/midovislam/awesome-pitch-decks",
        "index_path": str(args.index),
        "records": [asdict(record) for record in records],
    }
    manifest_path = args.output_dir.parent / "download-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    counts: dict[str, int] = {}
    for record in records:
        counts[record.status] = counts.get(record.status, 0) + 1
    print(f"processed {len(records)} index rows: {counts}")
    print(f"manifest: {manifest_path}")
    return 0 if counts.get("error", 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
