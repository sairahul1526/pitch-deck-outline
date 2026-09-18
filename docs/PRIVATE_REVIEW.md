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

Serve the generated directory without publishing it:

```bash
python3 -m http.server 8000 \
  --bind 127.0.0.1 \
  --directory data/interim/gold-review
```

Open `http://127.0.0.1:8000/review_queue.html`. Expand a case, compare the
rendered source page with the unverified machine draft, and then edit the local
`gold-review-records-with-machine-drafts.jsonl` copy. Keep `gold_text`, the
annotation lists, `reviewer_id`, and `reviewed_at` blank until a human has
actually checked the page. Change `review_status` to `reviewed` only after that
review. Never commit the generated directory or copy its text into GitHub.

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
