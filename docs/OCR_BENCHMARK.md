# OCR benchmark plan

This benchmark selects an extraction path for pitch-deck PDFs. It is not a
claim that one OCR engine is universally best.

## Sample design

Prepare 50 manually reviewed English slides:

- 20 born-digital PDFs with a text layer.
- 15 scanned or image-heavy slides.
- 10 chart/table-heavy slides.
- 5 difficult pages with rotation, dense layout, or OCR noise.

Split the sample by company and keep the gold transcription private. The
checked-in `contract_smoke` tests use tiny synthetic text and must never be
reported as a real OCR result.

## Candidate engines

1. Native PDF text extraction (speed baseline).
2. [Docling](https://github.com/docling-project/docling) for layout-aware
   reading order, headings, tables, and Markdown/JSON export.
3. [PaddleOCR-VL](https://github.com/PaddlePaddle/PaddleOCR) for scanned and
   complex pages, charts, and tables.
4. [olmOCR](https://github.com/allenai/olmocr) as a high-quality GPU reference.

The code and model licenses must be recorded independently. Do not publish
source PDFs or gold transcriptions unless their permission scope permits it.

## Metrics

- Character error rate (CER).
- Word error rate (WER).
- Token-overlap F1.
- Numeric-string F1, with zero tolerance for missing or corrupted numbers in
  approved critical slides.
- Heading, bullet, and table annotation F1.
- Per-page latency and error rate.
- Peak RAM/VRAM and estimated cost per page.

The report must retain case-level scores, engine versions, input/output hashes,
evidence scope, and the benchmark manifest hash.

## Private gold-review package

The Colab notebook can build a deterministic review package without publishing
source PDFs or annotations. It scans valid PDFs for page-level text signals,
selects 20 born-digital candidates, 15 scanned candidates, 10 chart/table
candidates, and 5 difficult candidates, then writes hashed case IDs and blank
gold fields to the user's private Drive. The buckets are routing hints only;
the reviewer must inspect each page, correct the bucket, transcribe the exact
English text, and mark the record as reviewed. The generated JSON and JSONL
files are working artifacts and must remain outside Git.

## Machine-assisted draft pass

After creating the review package, the notebook can run Docling once per
selected page with an exact \`page_range\`. It writes
\`gold-review-records-with-machine-drafts.jsonl\` and
\`runs/ocr/machine-draft-report.json\` to Drive. Each row records the engine
version, latency, status, and draft text while preserving blank gold fields.
Rows are marked \`machine_draft_unverified\`; a human must inspect the source
page, correct the transcription, confirm the provisional bucket, and then set
the row to \`reviewed\`. Empty or failed machine drafts are retained as explicit
hard cases rather than silently dropped.

## Selection rule

Choose the engine or tier with the best measured quality subject to acceptable
latency, memory, cost, and redistribution constraints. A hybrid route is valid:
native extraction for clean PDFs and a VLM fallback for difficult pages.
