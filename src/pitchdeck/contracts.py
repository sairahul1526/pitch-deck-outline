"""Stable input contracts for the pitch-deck outline project.

The public product intentionally accepts an open-ended set of optional context
fields. Only ``brief`` is required. This module validates the boundary without
forcing a fixed output schema: model responses remain plain text.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


class ContractError(ValueError):
    """Raised when a user-facing request violates the input contract."""


@dataclass(frozen=True, slots=True)
class StartupBrief:
    """A startup brief plus optional, user-defined context.

    ``extra`` allows integrations to pass fields that this version of the
    project does not know about yet. The values are kept as strings so the
    prompt layer can preserve the user's wording without inventing semantics.
    """

    brief: str
    industry: str | None = None
    target_customer: str | None = None
    problem: str | None = None
    solution: str | None = None
    traction: str | None = None
    market: str | None = None
    business_model: str | None = None
    competition: str | None = None
    go_to_market: str | None = None
    team: str | None = None
    fundraising_ask: str | None = None
    extra: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate only the invariant that the product requires: a brief."""

        if not isinstance(self.brief, str) or not self.brief.strip():
            raise ContractError("brief must be a non-empty string")

        for key, value in self.extra.items():
            if not isinstance(key, str) or not key.strip():
                raise ContractError("extra field names must be non-empty strings")
            if not isinstance(value, str):
                raise ContractError(f"extra field {key!r} must contain a string value")

    def as_prompt_context(self) -> str:
        """Render supplied context without imposing an output format.

        Empty optional fields are omitted. The brief is always first so a
        downstream prompt can clearly distinguish the required user intent
        from optional context.
        """

        sections = [f"Brief:\n{self.brief.strip()}"]
        optional = (
            ("Industry", self.industry),
            ("Target customer", self.target_customer),
            ("Problem", self.problem),
            ("Solution", self.solution),
            ("Traction", self.traction),
            ("Market", self.market),
            ("Business model", self.business_model),
            ("Competition", self.competition),
            ("Go-to-market", self.go_to_market),
            ("Team", self.team),
            ("Fundraising ask", self.fundraising_ask),
        )
        sections.extend(
            f"{label}:\n{value.strip()}"
            for label, value in optional
            if value and value.strip()
        )
        sections.extend(
            f"{key.strip()}:\n{value.strip()}"
            for key, value in self.extra.items()
            if value.strip()
        )
        return "\n\n".join(sections)
