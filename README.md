# Pitch Deck Outline

An open-source, text-first system that turns a startup brief into useful
investor-presentation copy.

The project is intentionally **not** tied to a fixed slide count or a fixed
response schema. A user supplies a required `brief` and may provide any number
of optional context fields. The model returns a normal text response that can
be rendered into a website, PDF, or presentation by a downstream application.

## Project status

This repository is at the scaffold-and-contract stage. It does not download
source documents, call external providers, train models, or deploy a service
yet. Those actions will be added behind explicit, reproducible steps.

## Design principles

- The startup `brief` is required; all other input fields are optional.
- Output is unconstrained plain text. Formatting guidance is a prompt concern,
  not a public API schema.
- Source data is preserved and never edited in place.
- Every source and transformation has provenance, hashes, and a manifest.
- Permission evidence is recorded privately; secrets and private correspondence
  never enter public artifacts.
- Raw documents are separated from cleaned text, supervised examples, and
  evaluation data.
- Training is compared with prompt-only and retrieval baselines before any
  claim that it improves the product.
- Public model behavior must not invent unsupported statistics, traction, or
  customer claims.
- Every release is versioned, evaluated, observable, and rollbackable.

## Planned pipeline

```text
approved sources
  -> raw snapshots + hashes
  -> PDF extraction/OCR benchmark
  -> cleaned slide/document records
  -> reviewed plain-text training examples
  -> prompt/RAG baselines
  -> LoRA/QLoRA experiments
  -> held-out and adversarial evaluation
  -> versioned adapter
  -> canary deployment and rollback
```

## Local development

The first implementation step is deliberately lightweight and CPU-safe:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest -q
```

GPU, OCR, hosted-provider, and serving dependencies will remain optional until
the OCR benchmark and data-rights manifest are approved.

## Repository map

- `src/pitchdeck/` — provider-neutral application modules.
- `src/pitchdeck/ocr/` — OCR extraction contracts, metrics, and benchmark runner.
- `src/pitchdeck/ingest/` — source rights and private artifact intake contracts.
- `notebooks/` — optional Colab smoke and benchmark notebooks.
- `configs/` — checked-in, human-readable configuration templates.
- `data/` — local data lifecycle directories; raw/private artifacts are ignored
  by Git.
- `manifests/` — immutable source, transformation, split, and run manifests.
- `docs/` — data, model, security, operations, and decision documentation.
- `scripts/` — bounded, resumable command-line workflows.
- `tests/` — unit and contract tests that run without a GPU.
- `runs/` — local experiment outputs; large artifacts are not committed.

## Open decisions

The following decisions are intentionally not guessed in the scaffold:

1. Project license (Apache-2.0 is the current recommendation for a public
   library/model project).
2. Exact base-model revision and model license.
3. OCR engine versions after the benchmark.
4. Training and serving providers.
5. Retention and opt-in policy for public user briefs.

See `docs/DECISIONS.md` for the decision log.

The current next step is the private benchmark review described in
`docs/DATA_INTAKE.md`. Source documents may be downloaded into ignored local
directories, but are never committed to this repository.
