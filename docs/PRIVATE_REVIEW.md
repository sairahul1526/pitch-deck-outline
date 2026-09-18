# Private visual review queue

`scripts/build_review_queue.py` creates a local, browser-readable review packet
from the downloaded source PDFs. The generated directory is ignored by Git and
contains source-page renders, native machine drafts, and blank gold fields.

## Build the queue

From the repository root:

```bash
python3 scripts/build_review_queue.py \
  --data-root data \
  --output-root data/interim/gold-review
```

The default sample is 50 pages with deterministic coverage across born-digital,
scanned, chart/table, and difficult pages. The command prints only counts and
paths; it does not print source text.

## Review locally

Run the local editor without publishing the generated directory:

```bash
PYTHONPATH=src python3 scripts/review_server.py \
  --root data/interim/gold-review \
  --host 127.0.0.1 \
  --port 8000
```

Open `http://127.0.0.1:8000/review_editor.html`. The editor shows one source
page and its unverified machine draft at a time. Enter only what you can verify
from the image. Saving a pending row keeps `gold_text` blank; the server refuses
to mark a row `reviewed` unless gold text, reviewer ID, and review time are all
present. The generated directory is ignored by Git and stays private on the
machine. Never commit it or copy its text into GitHub.

The older `review_queue.html` remains available as a read-only visual index.

The queue is a visual aid, not an editor. Use the repository's validation and
export scripts after review:

```bash
python3 scripts/validate_gold_review.py \
  --records data/interim/gold-review/gold-review-records-with-machine-drafts.jsonl \
  --manifest data/interim/gold-review/gold-review-manifest.json

python3 scripts/export_reviewed_cases.py \
  --records data/interim/gold-review/gold-review-records-with-machine-drafts.jsonl \
  --manifest data/interim/gold-review/gold-review-manifest.json \
  --output data/interim/gold-review/reviewed-cases.jsonl
```

The export command intentionally refuses to export an incomplete review unless
`--allow-partial` is supplied.
