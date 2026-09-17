# Decision log

This file records decisions that affect data rights, reproducibility, safety,
cost, or public behavior. Each entry should include evidence and a date.

## Confirmed

- The project is separate from the Amazon title-generation repository.
- English is the first supported language.
- Only `brief` is required at the input boundary.
- Optional context fields may be omitted or extended.
- The public response is unconstrained plain text.
- There is no user-selected or hard-coded output slide count.
- Approved sources may be used after permission evidence is recorded privately.

## Recommended, pending approval

- Use Apache-2.0 for the project unless the owner chooses another license.
- Start with a CPU-safe local pipeline and an on-demand L4 GPU for OCR/training.
- Use serverless GPU inference for bursty public traffic and dedicated capacity
  only after measured traffic justifies it.
- Treat unsupported numeric claims as a launch-blocking quality failure.

## Blocked until evidence exists

- Exact base model revision and license.
- OCR engine versions and winning benchmark configuration.
- Training dataset size after cleaning and review.
- Public user-brief retention and training opt-in policy.
- Sustained traffic profile and p95 latency target.
