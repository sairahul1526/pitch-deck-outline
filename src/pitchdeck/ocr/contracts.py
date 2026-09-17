"""Data contracts for reproducible PDF/OCR evaluation.

The benchmark stores references and manually prepared gold annotations, not
source PDFs. Real document paths remain outside Git and are resolved by a
runner in the execution environment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    """One page or slide with a manually reviewed reference transcription."""

    case_id: str
    source_id: str
    page_number: int
    document_ref: str
    gold_text: str
    language: str = "en"
    gold_numbers: tuple[str, ...] = ()
    gold_headings: tuple[str, ...] = ()
    gold_bullets: tuple[str, ...] = ()
    gold_tables: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Reject ambiguous benchmark cases before an engine is called."""

        for name in ("case_id", "source_id", "document_ref", "gold_text"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if not isinstance(self.page_number, int) or self.page_number < 1:
            raise ValueError("page_number must be a positive integer")
        if self.language != "en":
            raise ValueError("the first OCR benchmark only supports English cases")

    def annotation(self, key: str) -> tuple[str, ...]:
        """Return a tuple annotation by name for generic metric code."""

        value = getattr(self, f"gold_{key}", None)
        if value is None:
            raise KeyError(f"unknown annotation: {key}")
        return value
