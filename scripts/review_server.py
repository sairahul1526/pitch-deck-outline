#!/usr/bin/env python3
"""Serve the private OCR review queue with a local human-review editor.

The server deliberately binds to loopback by default.  It exposes the generated
review packet only to a browser on the same machine and writes reviewer edits
atomically back to the ignored JSONL file.  It never creates gold text from a
machine draft.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from pitchdeck.ocr.review import ReviewError, load_jsonl, validate_review_records

EDITABLE_FIELDS = frozenset(
    {
        "provisional_bucket",
        "review_status",
        "gold_text",
        "gold_numbers",
        "gold_headings",
        "gold_bullets",
        "gold_tables",
        "reviewer_id",
        "reviewed_at",
    }
)
RECORDS_FILENAME = "gold-review-records-with-machine-drafts.jsonl"
INDEX_PATH = re.compile(r"^/api/records/(\d+)$")


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def _atomic_write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    """Replace a JSONL file atomically, keeping the private file in its directory."""

    content = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in records)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def update_record(path: str | Path, index: int, changes: dict[str, Any]) -> dict[str, Any]:
    """Validate and persist one human edit without permitting immutable changes."""

    if not isinstance(changes, dict):
        raise ReviewError("update must be an object")
    unknown = sorted(set(changes) - EDITABLE_FIELDS)
    if unknown:
        raise ReviewError(f"immutable or unknown fields: {', '.join(unknown)}")

    records_path = Path(path)
    records = load_jsonl(records_path)
    if index < 0 or index >= len(records):
        raise ReviewError("record index is out of range")
    updated = dict(records[index])
    updated.update(changes)
    candidate = list(records)
    candidate[index] = updated
    validate_review_records(candidate)
    _atomic_write_jsonl(records_path, candidate)
    return updated


class ReviewHandler(SimpleHTTPRequestHandler):
    """HTTP handler for the local editor and its tiny JSON API."""

    server_version = "PitchDeckReview/1.0"

    @property
    def review_server(self) -> ReviewServer:
        return self.server  # type: ignore[return-value]

    def _send_json(self, status: HTTPStatus, payload: Any) -> None:
        body = _json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, status: HTTPStatus, message: str) -> None:
        self._send_json(status, {"ok": False, "error": message})

    def _records_for_browser(self) -> list[dict[str, Any]]:
        records = load_jsonl(self.review_server.records_path)
        rendered = sorted(self.review_server.rendered_path.glob("*.jpg"))
        output: list[dict[str, Any]] = []
        for index, record in enumerate(records):
            item = dict(record)
            if index < len(rendered):
                item["rendered_image"] = f"/rendered/{rendered[index].name}"
            output.append(item)
        return output

    def do_GET(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path == "/api/records":
            try:
                records = self._records_for_browser()
            except ReviewError as error:
                self._send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, str(error))
                return
            self._send_json(HTTPStatus.OK, {"records": records})
            return
        if path == "/api/status":
            try:
                summary = validate_review_records(load_jsonl(self.review_server.records_path))
            except ReviewError as error:
                self._send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, str(error))
                return
            self._send_json(
                HTTPStatus.OK,
                {
                    "total": summary.total,
                    "reviewed": summary.reviewed,
                    "pending": summary.pending,
                    "rejected": summary.rejected,
                    "status_counts": summary.status_counts,
                    "bucket_counts": summary.bucket_counts,
                },
            )
            return
        if path == "/review_editor.html":
            self._serve_editor()
            return
        super().do_GET()

    def _serve_editor(self) -> None:
        try:
            body = self.review_server.editor_path.read_bytes()
        except OSError:
            self._send_error_json(HTTPStatus.NOT_FOUND, "review editor template is missing")
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        match = INDEX_PATH.fullmatch(urlsplit(self.path).path)
        if match is None:
            self._send_error_json(HTTPStatus.NOT_FOUND, "unknown API endpoint")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 1_000_000:
                raise ReviewError("request body is missing or too large")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ReviewError("update must be an object")
            updated = update_record(
                self.review_server.records_path, int(match.group(1)), payload
            )
        except (ValueError, json.JSONDecodeError, ReviewError) as error:
            self._send_error_json(HTTPStatus.BAD_REQUEST, str(error))
            return
        # Return only non-sensitive status information; the browser reloads the row.
        self._send_json(
            HTTPStatus.OK,
            {"ok": True, "index": int(match.group(1)), "review_status": updated["review_status"]},
        )

    def log_message(self, format: str, *args: Any) -> None:
        # Keep source text and reviewer payloads out of terminal logs.
        super().log_message(format, *args)


class ReviewServer(ThreadingHTTPServer):
    """HTTP server carrying paths that are private to the local process."""

    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], root: Path, editor_path: Path) -> None:
        self.root = root.resolve()
        self.records_path = self.root / RECORDS_FILENAME
        self.rendered_path = self.root / "rendered"
        self.editor_path = editor_path.resolve()
        super().__init__(address, ReviewHandler)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("data/interim/gold-review"),
        help="private review directory",
    )
    parser.add_argument("--host", default="127.0.0.1", help="bind address (default: loopback only)")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    root = args.root.resolve()
    records_path = root / RECORDS_FILENAME
    editor_path = Path(__file__).resolve().parent.parent / "web" / "review_editor.html"
    if not records_path.is_file():
        raise SystemExit(f"private review records not found: {records_path}")
    if not editor_path.is_file():
        raise SystemExit(f"review editor template not found: {editor_path}")
    server = ReviewServer((args.host, args.port), root, editor_path)
    print(f"private review editor: http://{args.host}:{args.port}/review_editor.html")
    print(f"private review root: {root}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("stopping private review editor")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
