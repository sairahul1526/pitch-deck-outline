"""Provider-neutral OCR benchmark contracts and metrics."""

from .benchmark import (
    BenchmarkReport,
    BenchmarkScore,
    ExtractionEngine,
    ExtractionResult,
    benchmark,
)
from .contracts import BenchmarkCase
from .metrics import (
    character_error_rate,
    numeric_f1,
    structure_f1,
    token_f1,
    word_error_rate,
)

__all__ = [
    "BenchmarkCase",
    "BenchmarkReport",
    "BenchmarkScore",
    "ExtractionEngine",
    "ExtractionResult",
    "benchmark",
    "character_error_rate",
    "numeric_f1",
    "structure_f1",
    "token_f1",
    "word_error_rate",
]
