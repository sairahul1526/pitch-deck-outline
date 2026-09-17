"""Rights-gate tests for the source registry."""

import json
from dataclasses import replace

import pytest

from pitchdeck.ingest.registry import RegistryError, SourceRecord, SourceRegistry


def approved_record(source_id: str = "approved-source") -> SourceRecord:
    return SourceRecord(
        source_id=source_id,
        name="Approved source",
        source_kind="pdf_collection",
        source_url="https://example.com/decks",
        owner="Example owner",
        license="permission-granted",
        permission_reference="private-evidence://example/source-1",
        rights_reviewed_at="2026-09-17",
        status="approved",
        allowed_for_training=True,
        allowed_for_public_model=True,
        permission_scopes=frozenset({"training", "derivative_weights", "public_model"}),
    )


def test_approved_sources_are_explicitly_selectable() -> None:
    registry = SourceRegistry([approved_record()])

    assert registry.approved_for_training() == (approved_record(),)


def test_pending_sources_are_not_downloadable() -> None:
    pending = SourceRecord(
        source_id="pending-source",
        name="Pending source",
        source_kind="github_index",
        source_url="https://github.com/example/source",
        owner="Example owner",
        license="permission-pending",
        permission_reference="private-evidence://pending/source-1",
        rights_reviewed_at="2026-09-17",
    )

    assert SourceRegistry([pending]).approved_for_training() == ()


def test_public_model_requires_matching_training_and_permission_scopes() -> None:
    with pytest.raises(RegistryError, match="training permission scope"):
        replace(
            approved_record(),
            permission_scopes=frozenset({"public_model"}),
        )


def test_duplicate_source_ids_are_rejected() -> None:
    with pytest.raises(RegistryError, match="duplicate source_id"):
        SourceRegistry([approved_record(), approved_record()])


def test_manifest_hash_is_order_independent(tmp_path) -> None:
    first = SourceRegistry([approved_record("a-source"), approved_record("b-source")])
    second = SourceRegistry([approved_record("b-source"), approved_record("a-source")])

    assert first.manifest_sha256() == second.manifest_sha256()

    path = tmp_path / "source-manifest.json"
    digest = first.save_manifest(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["manifest_sha256"] == digest
    assert payload["schema_version"] == 1


def test_registry_round_trip_load(tmp_path) -> None:
    original = SourceRegistry([approved_record()])
    path = tmp_path / "source-manifest.json"
    original.save_manifest(path)

    loaded = SourceRegistry.from_json(path)

    assert loaded.records == original.records
    assert loaded.manifest_sha256() == original.manifest_sha256()


def test_unknown_record_fields_fail_closed(tmp_path) -> None:
    path = tmp_path / "sources.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "records": [{"source_id": "x", "unexpected": True}],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(RegistryError, match="unknown fields"):
        SourceRegistry.from_json(path)
