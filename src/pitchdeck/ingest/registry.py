"""Validated source registry and deterministic permission manifest.

The registry is deliberately separate from downloading. It records what may be
used and why; a later ingestion step will be allowed to fetch only records
whose status and permission scope pass validation.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

SOURCE_KINDS = frozenset(
    {
        "github_index",
        "pdf_collection",
        "huggingface_dataset",
        "transcript_dataset",
        "synthetic_dataset",
        "user_owned",
    }
)

PERMISSION_SCOPES = frozenset(
    {
        "training",
        "derivative_weights",
        "public_model",
        "public_redistribution",
    }
)

STATUSES = frozenset({"pending", "approved", "blocked"})
_SOURCE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


class RegistryError(ValueError):
    """Raised when a source registry violates a rights or schema invariant."""


def _require_text(field_name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RegistryError(f"{field_name} must be a non-empty string")
    return value.strip()


def _validate_url(value: str) -> str:
    value = _require_text("source_url", value)
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise RegistryError("source_url must be an absolute HTTPS URL")
    return value


def _validate_date(field_name: str, value: str) -> str:
    value = _require_text(field_name, value)
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise RegistryError(f"{field_name} must use YYYY-MM-DD format") from exc
    return value


@dataclass(frozen=True, slots=True)
class SourceRecord:
    """A single source and its permitted uses.

    ``permission_reference`` points to private evidence, such as a local
    correspondence identifier. It is intentionally not the email contents.
    """

    source_id: str
    name: str
    source_kind: str
    source_url: str
    owner: str
    license: str
    permission_reference: str
    rights_reviewed_at: str
    status: str = "pending"
    allowed_for_training: bool = False
    allowed_for_public_model: bool = False
    allowed_for_public_redistribution: bool = False
    permission_scopes: frozenset[str] = field(default_factory=frozenset)
    expected_revision: str | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        """Validate the record and fail closed on ambiguous permissions."""

        if not isinstance(self.source_id, str) or not _SOURCE_ID.fullmatch(self.source_id):
            raise RegistryError(
                "source_id must contain only lowercase letters, numbers, '.', '_' or '-'"
            )
        _require_text("name", self.name)
        if self.source_kind not in SOURCE_KINDS:
            raise RegistryError(f"source_kind must be one of {sorted(SOURCE_KINDS)}")
        _validate_url(self.source_url)
        _require_text("owner", self.owner)
        _require_text("license", self.license)
        _require_text("permission_reference", self.permission_reference)
        _validate_date("rights_reviewed_at", self.rights_reviewed_at)

        if self.status not in STATUSES:
            raise RegistryError(f"status must be one of {sorted(STATUSES)}")
        if not isinstance(self.permission_scopes, (set, frozenset)):
            raise RegistryError("permission_scopes must be a set of scope names")
        unknown_scopes = set(self.permission_scopes) - PERMISSION_SCOPES
        if unknown_scopes:
            raise RegistryError(f"unknown permission scopes: {sorted(unknown_scopes)}")

        if self.allowed_for_training and "training" not in self.permission_scopes:
            raise RegistryError("allowed_for_training requires the training permission scope")
        if self.allowed_for_public_model and "public_model" not in self.permission_scopes:
            raise RegistryError("allowed_for_public_model requires the public_model scope")
        if (
            self.allowed_for_public_redistribution
            and "public_redistribution" not in self.permission_scopes
        ):
            raise RegistryError(
                "allowed_for_public_redistribution requires the public_redistribution scope"
            )
        if self.allowed_for_public_model and not self.allowed_for_training:
            raise RegistryError(
                "a public model cannot use a source that is not approved for training"
            )
        if self.allowed_for_public_redistribution and not self.allowed_for_public_model:
            raise RegistryError(
                "public redistribution requires permission to use the source in the public model"
            )
        if self.status == "approved" and not self.allowed_for_training:
            raise RegistryError("approved sources must be approved for training")

    def canonical_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation with stable ordering."""

        record = asdict(self)
        record["permission_scopes"] = sorted(self.permission_scopes)
        return record


class SourceRegistry:
    """Collection of unique source records with a reproducible manifest hash."""

    schema_version = 1

    def __init__(self, records: Iterable[SourceRecord] = ()) -> None:
        self.records = tuple(records)
        self._validate_unique_ids()

    @classmethod
    def from_json(cls, path: str | Path) -> SourceRegistry:
        """Load and validate a registry JSON file.

        Unknown record fields are rejected so a typo cannot silently weaken a
        rights gate. A previously written ``manifest_sha256`` is checked
        against the canonical records when present.
        """

        input_path = Path(path)
        try:
            payload = json.loads(input_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RegistryError(f"could not read registry JSON: {input_path}") from exc
        if not isinstance(payload, dict):
            raise RegistryError("registry JSON must contain an object")
        if payload.get("schema_version") != cls.schema_version:
            raise RegistryError(
                "unsupported registry schema_version: "
                f"{payload.get('schema_version')!r}"
            )
        raw_records = payload.get("records")
        if not isinstance(raw_records, list):
            raise RegistryError("registry records must be a list")

        allowed_fields = set(SourceRecord.__dataclass_fields__)
        records: list[SourceRecord] = []
        for index, raw_record in enumerate(raw_records):
            if not isinstance(raw_record, dict):
                raise RegistryError(f"record {index} must be an object")
            unknown_fields = set(raw_record) - allowed_fields
            if unknown_fields:
                raise RegistryError(
                    f"record {index} contains unknown fields: {sorted(unknown_fields)}"
                )
            record_data = dict(raw_record)
            record_data["permission_scopes"] = frozenset(record_data.get("permission_scopes", ()))
            try:
                records.append(SourceRecord(**record_data))
            except TypeError as exc:
                raise RegistryError(f"record {index} is missing or has invalid fields") from exc

        registry = cls(records)
        declared_hash = payload.get("manifest_sha256")
        if declared_hash is not None and declared_hash != registry.manifest_sha256():
            raise RegistryError("manifest_sha256 does not match canonical registry contents")
        return registry

    def _validate_unique_ids(self) -> None:
        ids = [record.source_id for record in self.records]
        duplicates = sorted({source_id for source_id in ids if ids.count(source_id) > 1})
        if duplicates:
            raise RegistryError(f"duplicate source_id values: {duplicates}")

    def approved_for_training(self) -> tuple[SourceRecord, ...]:
        """Return only sources that are explicitly approved for training."""

        return tuple(
            record
            for record in self.records
            if record.status == "approved" and record.allowed_for_training
        )

    def manifest_payload(self) -> dict[str, Any]:
        """Return canonical data used for hashing and audit storage."""

        return {
            "schema_version": self.schema_version,
            "records": [
                record.canonical_dict()
                for record in sorted(self.records, key=lambda item: item.source_id)
            ],
        }

    def manifest_sha256(self) -> str:
        """Hash canonical JSON so equivalent registries produce the same hash."""

        payload = json.dumps(
            self.manifest_payload(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def save_manifest(self, path: str | Path) -> str:
        """Write a readable manifest and return its SHA-256 identifier."""

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
