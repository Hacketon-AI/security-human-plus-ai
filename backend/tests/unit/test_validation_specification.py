"""Unit tests for the execution-specification builder's sensitive_path flag.

The builder is pure, so it is exercised with lightweight stand-ins carrying only
the attributes it reads. Only the ``sensitive_path`` derivation is asserted here.
"""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.modules.assets.enums import AssetCriticality
from app.modules.validation_executions.specification import (
    build_execution_specification,
)
from app.modules.validation_executions.templates import (
    HTTP_SECURITY_HEADER_VALIDATION,
    get_template,
)


def _build(criticality: AssetCriticality) -> dict[str, object]:
    template = get_template(HTTP_SECURITY_HEADER_VALIDATION)
    asset = SimpleNamespace(
        id=uuid4(), target="https://app.example.com/login", criticality=criticality
    )
    authorization = SimpleNamespace(id=uuid4())
    engagement = SimpleNamespace(id=uuid4())
    window_start = datetime(2026, 6, 24, 9, 0, tzinfo=UTC)
    window_end = datetime(2026, 6, 24, 17, 0, tzinfo=UTC)
    return build_execution_specification(
        execution_id=uuid4(),
        template=template,
        asset=asset,  # type: ignore[arg-type]
        authorization=authorization,  # type: ignore[arg-type]
        engagement=engagement,  # type: ignore[arg-type]
        scope_snapshot={"target": asset.target},
        safety_snapshot={"rate_limit_per_minute": 30},
        testing_window_start=window_start,
        testing_window_end=window_end,
        kill_switch_token="opaque-token",
    )


@pytest.mark.parametrize(
    "criticality", [AssetCriticality.high, AssetCriticality.critical]
)
def test_high_criticality_marks_sensitive_path(
    criticality: AssetCriticality,
) -> None:
    assert _build(criticality)["sensitive_path"] is True


@pytest.mark.parametrize("criticality", [AssetCriticality.low, AssetCriticality.medium])
def test_low_criticality_is_not_sensitive(criticality: AssetCriticality) -> None:
    assert _build(criticality)["sensitive_path"] is False


def test_sensitive_path_is_spec_only_and_carries_no_secret() -> None:
    spec = _build(AssetCriticality.high)
    assert "sensitive_path" in spec
    # The flag is a plain bool, not a credential or path payload.
    assert isinstance(spec["sensitive_path"], bool)
