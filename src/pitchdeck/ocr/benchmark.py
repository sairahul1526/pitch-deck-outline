"""Engine-neutral OCR benchmark runner and report serialization."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

from .contracts import BenchmarkCase
from .metrics import (
    character_error_rate,
    numeric_f1,
    structure_f1,
    token_f1,
    word_error_rate,
)


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    """One engine's output for one benchmark case."""

    case_id: str
    engine: str
    engine_version: str
    text: str = ""
    latency_ms: float | None = None
    input_sha256: str | None = None
    output_sha256: str | None = None
    status: str = "ok"
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in {"ok", "error"}:
            raise ValueError("status must be 'ok' or 'error'")
        if self.status == "error" and not self.error:
            raise ValueError("error results must include an error message")

    @classmethod
    def success(
        cls,
        case_id: str,
        engine: str,
        engine_version: str,
        text: str,
        latency_ms: float | None = None,
        input_sha256: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ExtractionResult:
        """Construct a result and calculate its output hash consistently."""

        output_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return cls(
            case_id=case_id,
            engine=engine,
            engine_version=engine_version,
            text=text,
            latency_ms=latency_ms,
            input_sha256=input_sha256,
            output_sha256=output_sha256,
            metadata=metadata or {},
        )


class ExtractionEngine(Protocol):
    """Adapter interface implemented by native, Docling, Paddle, or olmOCR."""

    name: str
    version: str

    def extract(self, case: BenchmarkCase) -> ExtractionResult:
        """Extract one case and return a hashed, timed result."""


@dataclass(frozen=True, slots=True)
class BenchmarkScore:
    """Metrics for one engine/case pair."""

    case_id: str
    engine: str
    engine_version: str
    status: str
    character_error_rate: float | None
    word_error_rate: float | None
    token_f1: float | None
    numeric_f1: float | None
    heading_f1: float | None
    bullet_f1: float | None
    table_f1: float | None
    latency_ms: float | None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    """Immutable report with an evidence scope and deterministic hash."""

    evidence_scope: str
    scores: tuple[BenchmarkScore, ...]
    metadata: dict[str, Any] = field(default_factory=dict)

    def payload(self) -> dict[str, Any]:
        return {
            "evidence_scope": self.evidence_scope,
            "scores": [asdict(score) for score in self.scores],
            "metadata": self.metadata,
        }

    def sha256(self) -> str:
        encoded = json.dumps(self.payload(), sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()

    def save_json(self, path: str | Path) -> str:
        """Write a readable report and return its canonical hash."""

        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = self.payload()
        digest = self.sha256()
        payload["report_sha256"] = digest
        output_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return digest


def _score(case: BenchmarkCase, result: ExtractionResult) -> BenchmarkScore:
    if result.status == "error":
        return BenchmarkScore(
            case_id=case.case_id,
            engine=result.engine,
            engine_version=result.engine_version,
            status="error",
            character_error_rate=None,
            word_error_rate=None,
            token_f1=None,
            numeric_f1=None,
            heading_f1=None,
            bullet_f1=None,
            table_f1=None,
            latency_ms=result.latency_ms,
            error=result.error,
        )
    return BenchmarkScore(
        case_id=case.case_id,
        engine=result.engine,
        engine_version=result.engine_version,
        status="ok",
        character_error_rate=character_error_rate(case.gold_text, result.text),
        word_error_rate=word_error_rate(case.gold_text, result.text),
        token_f1=token_f1(case.gold_text, result.text),
        numeric_f1=numeric_f1(case.gold_numbers, result.text),
        heading_f1=structure_f1(case.gold_headings, result.text),
        bullet_f1=structure_f1(case.gold_bullets, result.text),
        table_f1=structure_f1(case.gold_tables, result.text),
        latency_ms=result.latency_ms,
    )


def benchmark(
    cases: Iterable[BenchmarkCase],
    engines: Iterable[ExtractionEngine],
    *,
    evidence_scope: str = "contract_smoke",
    metadata: dict[str, Any] | None = None,
) -> BenchmarkReport:
    """Run every engine on every case and fail closed per engine/case.

    An engine exception becomes an explicit error score instead of disappearing
    from the report. Scores are sorted to make report hashes reproducible.
    """

    case_list = tuple(cases)
    engine_list = tuple(engines)
    scores: list[BenchmarkScore] = []
    for engine in engine_list:
        for case in case_list:
            try:
                result = engine.extract(case)
                if result.case_id != case.case_id:
                    raise ValueError("engine returned a result for the wrong case_id")
            except Exception as exc:  # noqa: BLE001 - report engine failures explicitly
                result = ExtractionResult(
                    case_id=case.case_id,
                    engine=engine.name,
                    engine_version=engine.version,
                    status="error",
                    error=f"{type(exc).__name__}: {exc}",
                )
            scores.append(_score(case, result))

    ordered = tuple(sorted(scores, key=lambda item: (item.engine, item.case_id)))
    return BenchmarkReport(evidence_scope=evidence_scope, scores=ordered, metadata=metadata or {})
