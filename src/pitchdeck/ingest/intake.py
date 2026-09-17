"""Rights-aware inventory contracts for privately held source artifacts.

The intake manifest describes files after they have been collected. It contains
paths, hashes, and review state, never the PDF bytes or private permission
correspondence. A record cannot become usable for training unless its source
is approved by :mod:`pitchdeck.ingest.registry`.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .registry import SourceRegistry

INTAKE_STATUSES = frozenset({"candidate", "approved", "quarantined"})
SAMPLING_BUCKETS = frozenset({"born_digital", "scanned", "chart_table", "difficult"})
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class IntakeError(ValueError):
    """Raised when a source inventory violates an intake invariant."""


def _require_text(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise IntakeError(f"{name} must be a non-empty string")
    return value.strip()


def _validate_relative_path(value: str) -> str:
    value = _require_text("relative_path", value)
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise IntakeError("relative_path must stay inside the private data directory")
    return value


@dataclass(frozen=True, slots=True)
class IntakeRecord:
    """One privately stored artifact and its review state."""

    document_id: str
    source_id: str
    source_locator: str
    relative_path: str
    sampling_bucket: str
    status: str = "candidate"
    artifact_type: str = "pdf"
    sha256: str | None = None
    byte_size: int | None = None
    page_count: int | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        _require_text("document_id", self.document_id)
        _require_text("source_id", self.source_id)
        _require_text("source_locator", self.source_locator)
        _validate_relative_path(self.relative_path)
        if self.sampling_bucket not in SAMPLING_BUCKETS:
            raise IntakeError(
                f"sampling_bucket must be one of {sorted(SAMPLING_BUCKETS)}"
            )
        if self.status not in INTAKE_STATUSES:
            raise IntakeError(f"status must be one of {sorted(INTAKE_STATUSES)}")
        if self.artifact_type != "pdf":
            raise IntakeError("the OCR intake currently accepts PDF artifacts only")
        if self.sha256 is not None and not _SHA256.fullmatch(self.sha256):
            raise IntakeError("sha256 must be a lowercase SHA-256 digest")
        if self.byte_size is not None and self.byte_size < 1:
            raise IntakeError("byte_size must be positive when supplied")
        if self.page_count is not None and self.page_count < 1:
            raise IntakeError("page_count must be positive when supplied")
        if self.status == "approved" and self.sha256 is None:
            raise IntakeError("approved artifacts must include a SHA-256 digest")

    def canonical_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation with stable field values."""

        return asdict(self)


@dataclass(frozen=True, slots=True)
class IntakeManifest:
    """Deterministic inventory bound to one source-registry revision."""

    source_manifest_sha256: str
    records: tuple[IntakeRecord, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    schema_version = 1

    def __post_init__(self) -> None:
        if not _SHA256.fullmatch(self.source_manifest_sha256):
            raise IntakeError("source_manifest_sha256 must be a lowercase SHA-256 digest")
        identifiers = [record.document_id for record in self.records]
        if len(identifiers) != len(set(identifiers)):
            raise IntakeError("document_id values must be unique")
        paths = [record.relative_path for record in self.records]
        if len(paths) != len(set(paths)):
            raise IntakeError("relative_path values must be unique")

    @classmethod
    def from_json(cls, path: str | Path) -> IntakeManifest:
        """Load and validate a JSON inventory without touching source files."""

        input_path = Path(path)
        try:
            payload = json.loads(input_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise IntakeError(f"could not read intake manifest: {input_path}") from exc
        if not isinstance(payload, dict) or payload.get("schema_version") != cls.schema_version:
            raise IntakeError("unsupported or missing intake schema_version")
        raw_records = payload.get("records")
        if not isinstance(raw_records, list):
            raise IntakeError("intake records must be a list")
        allowed_fields = set(IntakeRecord.__dataclass_fields__)
        records: list[IntakeRecord] = []
        for index, raw_record in enumerate(raw_records):
            if not isinstance(raw_record, dict):
                raise IntakeError(f"record {index} must be an object")
            unknown_fields = set(raw_record) - allowed_fields
            if unknown_fields:
                raise IntakeError(
                    f"record {index} contains unknown fields: {sorted(unknown_fields)}"
                )
            try:
                records.append(IntakeRecord(**raw_record))
            except TypeError as exc:
                raise IntakeError(f"record {index} is missing or has invalid fields") from exc
        manifest = cls(
            source_manifest_sha256=payload.get("source_manifest_sha256", ""),
            records=tuple(records),
            metadata=payload.get("metadata", {}),
        )
        declared_hash = payload.get("manifest_sha256")
        if declared_hash is not None and declared_hash != manifest.manifest_sha256():
            raise IntakeError("manifest_sha256 does not match canonical intake contents")
        return manifest

    def validate_against(self, sources: SourceRegistry) -> None:
        """Ensure the manifest is bound to the exact registry and rights gate."""

        if self.source_manifest_sha256 != sources.manifest_sha256():
            raise IntakeError("intake manifest is bound to a different source registry")
        source_by_id = {record.source_id: record for record in sources.records}
        for record in self.records:
            source = source_by_id.get(record.source_id)
            if source is None:
                raise IntakeError(f"unknown source_id: {record.source_id}")
            if record.status == "approved" and not (
                source.status == "approved" and source.allowed_for_training
            ):
                raise IntakeError(
                    f"artifact {record.document_id} is approved but its source is not approved"
                )

    def approved_records(self) -> tuple[IntakeRecord, ...]:
        """Return only artifacts eligible for the next processing stage."""

        return tuple(record for record in self.records if record.status == "approved")

    def manifest_payload(self) -> dict[str, Any]:
        """Return the canonical fields used for the manifest hash."""

        return {
            "schema_version": self.schema_version,
            "source_manifest_sha256": self.source_manifest_sha256,
            "records": [
                record.canonical_dict()
                for record in sorted(self.records, key=lambda item: item.document_id)
            ],
            "metadata": self.metadata,
        }

    def manifest_sha256(self) -> str:
        """Hash canonical JSON so equivalent inventories share one identifier."""

        encoded = json.dumps(
            self.manifest_payload(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def save_manifest(self, path: str | Path) -> str:
        """Write a readable inventory and return its canonical hash."""

        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        manifest = self.manifest_payload()
        digest = self.manifest_sha256()
        manifest["manifest_sha256"] = digest
        output_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return digest


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    """Hash a local artifact without loading the complete PDF into memory."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as source_file:
        for chunk in iter(lambda: source_file.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def records_for_source(
    records: Iterable[IntakeRecord], source_id: str
) -> tuple[IntakeRecord, ...]:
    """Select records for one source while preserving deterministic ordering."""

    matching = (record for record in records if record.source_id == source_id)
    return tuple(sorted(matching, key=lambda item: item.document_id))
