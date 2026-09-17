# Operations plan (draft)

The CPU VPS is intended for orchestration, manifests, API ingress, queues, and
observability. GPU workers are separate and disposable for OCR/training or
serverless for bursty inference.

Required production signals:

- Request count and status codes.
- Queue depth and rejection count.
- p50/p95/p99 latency.
- Input/output token counts.
- GPU warm/cold starts and utilization.
- Model/adapter load health.
- Timeout, retry, and provider error rates.
- Unsupported-statistic and safety-check failures.
- Cost estimate per request and per release.

Every release must support a canary route and one-command rollback to the last
validated adapter.
