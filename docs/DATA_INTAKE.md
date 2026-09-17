# Data intake and benchmark sampling

Step 4 prepares the private document inventory that will feed the OCR
benchmark. The repository stores only metadata and hashes; PDFs, gold
transcriptions, and permission emails stay outside Git.

## Intake states

- `candidate`: collected or proposed, but not yet cleared for processing.
- `approved`: source rights and artifact integrity have been checked; eligible
  for OCR and later review.
- `quarantined`: withheld because of a rights, quality, privacy, or integrity
  concern.

An `approved` artifact must reference an `approved` source, include a lowercase
SHA-256 digest, and use one of the OCR sampling buckets:
`born_digital`, `scanned`, `chart_table`, or `difficult`.

## Safe collection sequence

1. Replace permission placeholders in the private copy of
   `configs/sources.example.json` and save the source manifest.
2. Collect PDFs into the ignored `data/raw/` directory. Do not commit the
   files or private correspondence.
3. Record each file's stable document ID, source ID, private relative path,
   byte hash, and sampling bucket in an intake manifest.
4. Run `scripts/validate_intake_manifest.py` against the source manifest.
5. Review the 50-page sample by company, keeping gold transcription files in a
   private evaluation location.

The first sample target is 20 born-digital pages, 15 scanned/image-heavy pages,
10 chart/table pages, and 5 difficult pages. Keep all pages from one company
in the same evaluation split to prevent leakage.

## Reproducible source snapshot

The checked-in `scripts/download_awesome_decks.py` downloader resumes existing
PDFs, follows Google Drive virus-scan confirmation links, verifies PDF magic
bytes, and records per-file hashes in an ignored download manifest:

```bash
PYTHONPATH=src python scripts/download_awesome_decks.py --workers 4
```

The current local snapshot has 754 index rows, 752 unique Drive IDs, and 751
downloaded PDFs; one Hadean link is stale and returns a verified Drive “file
does not exist” page. The three Hugging Face source snapshots are also stored
under `data/raw/huggingface/` with their revision and file hashes.

## Validation command

```bash
PYTHONPATH=src python scripts/validate_intake_manifest.py \
  --sources /private/path/source-manifest.json \
  --intake /private/path/ocr-intake.json
```

The command does not download or open PDFs. It checks only metadata, hashes,
source binding, duplicate IDs/paths, and rights state.
