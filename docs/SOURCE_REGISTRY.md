# Source registry

The source registry is a rights and provenance gate. It is separate from
download code so a future collector cannot silently fetch an unapproved source.

## Required fields

Each source record contains:

- Stable lowercase `source_id`.
- Human-readable name and source kind.
- HTTPS source URL and owner.
- Declared license.
- Private permission-evidence reference.
- Date the rights decision was reviewed.
- Status: `pending`, `approved`, or `blocked`.
- Explicit permission scopes.
- Whether the source may be used for training, public model weights, and public
  redistribution.
- Optional immutable revision and notes.

An `approved` record must explicitly authorize training. Public-model and
public-redistribution flags require their matching permission scopes. The
validator fails closed when those relationships are inconsistent.

## Example record

```json
{
  "source_id": "example-pitch-decks",
  "name": "Example Pitch Deck Collection",
  "source_kind": "pdf_collection",
  "source_url": "https://example.com/pitch-decks",
  "owner": "Example owner",
  "license": "permission-granted",
  "permission_reference": "private-evidence://permissions/example-pitch-decks",
  "rights_reviewed_at": "2026-09-17",
  "status": "approved",
  "allowed_for_training": true,
  "allowed_for_public_model": true,
  "allowed_for_public_redistribution": false,
  "permission_scopes": ["training", "derivative_weights", "public_model"],
  "expected_revision": "sha256:...",
  "notes": "Raw PDFs remain private; derived model may be public."
}
```

Do not put permission emails, credentials, or private source payloads in this
repository. Store them in a private evidence location and keep only the stable
reference and, where appropriate, an evidence hash.

`configs/sources.example.json` contains the four currently discussed source
families. Copy it to a private working configuration, replace each permission
placeholder with the private evidence reference, and change `status` plus the
permission flags only after the evidence has been checked.

## Manifest behavior

`SourceRegistry.save_manifest()` sorts records by `source_id`, serializes them
with canonical JSON, and writes a `manifest_sha256`. This hash must be copied
into later ingestion, OCR, cleaning, split, and training manifests.
