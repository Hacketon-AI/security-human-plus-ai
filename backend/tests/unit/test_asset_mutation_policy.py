"""Unit tests for the asset mutation policy."""

import pytest
from app.modules.assets.enums import AssetStatus
from app.modules.assets.errors import AssetMutationNotAllowed
from app.modules.assets.mutation_policy import ensure_metadata_update_allowed


@pytest.mark.parametrize(
    "status",
    [AssetStatus.draft, AssetStatus.pending_verification, AssetStatus.verified],
)
def test_metadata_update_allowed_in_mutable_states(status: AssetStatus) -> None:
    # Does not raise.
    ensure_metadata_update_allowed(status, {"name", "criticality"})


def test_empty_change_set_allowed_in_mutable_state() -> None:
    ensure_metadata_update_allowed(AssetStatus.draft, set())


@pytest.mark.parametrize("status", [AssetStatus.suspended, AssetStatus.retired])
def test_metadata_update_rejected_in_protected_states(status: AssetStatus) -> None:
    with pytest.raises(AssetMutationNotAllowed):
        ensure_metadata_update_allowed(status, {"name"})


def test_protected_state_rejects_even_empty_change_set() -> None:
    # A PATCH against a retired asset is refused regardless of fields.
    with pytest.raises(AssetMutationNotAllowed):
        ensure_metadata_update_allowed(AssetStatus.retired, set())


def test_disallowed_field_is_rejected_in_mutable_state() -> None:
    with pytest.raises(AssetMutationNotAllowed):
        ensure_metadata_update_allowed(AssetStatus.draft, {"name", "target"})
