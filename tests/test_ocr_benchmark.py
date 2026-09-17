"""Benchmark runner tests with a synthetic engine."""

import json

from pitchdeck.ocr import BenchmarkCase, ExtractionResult, benchmark


class EchoEngine:
    name = "echo"
    version = "0.1"

    def extract(self, case: BenchmarkCase) -> ExtractionResult:
        return ExtractionResult.success(
            case_id=case.case_id,
            engine=self.name,
            engine_version=self.version,
            text=case.gold_text,
            latency_ms=1.5,
        )


class BrokenEngine:
    name = "broken"
    version = "0.1"

    def extract(self, case: BenchmarkCase) -> ExtractionResult:
        raise RuntimeError("provider unavailable")


def sample_case() -> BenchmarkCase:
    return BenchmarkCase(
        case_id="smoke-001",
        source_id="contract-smoke",
        page_number=1,
        document_ref="fixture://contract-smoke",
        gold_text="Market size: $12.5M\n- Fast onboarding",
        gold_numbers=("$12.5M",),
        gold_headings=("Market size: $12.5M",),
        gold_bullets=("Fast onboarding",),
    )


def test_benchmark_is_sorted_and_records_engine_failures(tmp_path) -> None:
    report = benchmark([sample_case()], [BrokenEngine(), EchoEngine()])

    assert [score.engine for score in report.scores] == ["broken", "echo"]
    assert report.scores[0].status == "error"
    assert report.scores[1].token_f1 == 1.0
    assert report.evidence_scope == "contract_smoke"

    path = tmp_path / "ocr-report.json"
    digest = report.save_json(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["report_sha256"] == digest
