"""Contract tests that do not require a model, network, or GPU."""

import pytest

from pitchdeck.contracts import ContractError, StartupBrief


def test_brief_is_the_only_required_field() -> None:
    request = StartupBrief(brief="We help independent clinics reduce missed appointments.")

    assert request.as_prompt_context() == (
        "Brief:\nWe help independent clinics reduce missed appointments."
    )


def test_optional_context_is_preserved_without_forcing_output_shape() -> None:
    request = StartupBrief(
        brief="A startup brief.",
        industry="Healthcare",
        extra={"Founder note": "Keep the tone direct."},
    )

    rendered = request.as_prompt_context()
    assert "Industry:\nHealthcare" in rendered
    assert "Founder note:\nKeep the tone direct." in rendered


@pytest.mark.parametrize("value", ["", "   ", None])
def test_empty_brief_is_rejected(value: str | None) -> None:
    with pytest.raises(ContractError):
        StartupBrief(brief=value)  # type: ignore[arg-type]


def test_extra_fields_must_contain_strings() -> None:
    with pytest.raises(ContractError):
        StartupBrief(brief="A brief.", extra={"market_size": 10})  # type: ignore[dict-item]
