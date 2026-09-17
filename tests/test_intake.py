"""Rights-aware document inventory tests."""

import json
from dataclasses import replace

import pytest

from pitchdeck.ingest import (
    IntakeError,
    IntakeManifest,
    IntakeRecord,
    SourceRecord,
    SourceRegistry,
    sha256_file,
)


def approved_source() -> SourceRecord:
    return SourceRecord(
        source_id="approved-source",
        name="Approved source",
        source_kind="pdf_collection",
        source_url="https://example.com/decks",
        owner="Example owner",
        license="permission-granted",
        permission_reference="private-evidence://example/source-1",
        rights_reviewed_at="2026-09-17",
        status="approved",
        allowed_for_training=True,
        permission_scopes=frozenset({"training"}),
    )


def record(source_id: str = "approved-source", status: str = "approved") -> IntakeRecord:
    return IntakeRecord(
        document_id="deck-001",
        source_id=source_id,
        source_locator="https://example.com/deck.pdf",
        relative_path="data/raw/deck-001.pdf",
        sampling_bucket="born_digital",
        status=status,
        sha256="a" * 64 if status == "approved" else None,
    )


def test_approved_intake_must_bind_to_approved_source() -> None:
    sources = SourceRegistry([approved_source()])
    manifest = IntakeManifest(sources.manifest_sha256(), (record(),))

    manifest.validate_against(sources)
    assert manifest.approved_records() == (record(),)


def test_pending_source_cannot_clear_artifact() -> None:
    source = replace(approved_source(), status="pending", allowed_for_training=False)
    sources = SourceRegistry([source])
    manifest = IntakeManifest(sources.manifest_sha256(), (record(),))

    with pytest.raises(IntakeError, match="source is not approved"):
        manifest.validate_against(sources)


def test_manifest_hash_is_order_independent_and_round_trips(tmp_path) -> None:
    sources = SourceRegistry([approved_source()])
    first = IntakeManifest(sources.manifest_sha256(), (record(),))
    path = tmp_path / "intake.json"

    digest = first.save_manifest(path)
    loaded = IntakeManifest.from_json(path)

    assert loaded == first
    assert loaded.manifest_sha256() == digest
    assert json.loads(path.read_text(encoding="utf-8"))["manifest_sha256"] == digest


def test_duplicate_paths_are_rejected() -> None:
    first = record()
    second = replace(first, document_id="deck-002")

    with pytest.raises(IntakeError, match="relative_path values must be unique"):
        IntakeManifest("a" * 64, (first, second))


def test_sha256_file_hashes_in_chunks(tmp_path) -> None:
    path = tmp_path / "fixture.pdf"
    path.write_bytes(b"fixture")

    assert sha256_file(path) == "f16d05ec6b29248d2c61adb1e9263f78e4f7bace1b955014a2d17872cfe4064d"
