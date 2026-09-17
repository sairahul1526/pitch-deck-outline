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

## Selection rule

Choose the engine or tier with the best measured quality subject to acceptable
latency, memory, cost, and redistribution constraints. A hybrid route is valid:
native extraction for clean PDFs and a VLM fallback for difficult pages.
