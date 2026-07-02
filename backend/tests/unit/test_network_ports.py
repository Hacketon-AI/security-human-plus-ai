"""Unit tests for the shared port-allow-list normalizer.

``normalize_allowed_ports`` is the single control-plane normalization point for
``allowed_ports``; the request schemas and the snapshot builder both rely on it,
so the strict-int / range / dedup contract is pinned here.
"""

import pytest
from app.modules.shared.network_ports import (
    InvalidPortError,
    normalize_allowed_ports,
)


def test_none_passes_through() -> None:
    assert normalize_allowed_ports(None) is None


def test_empty_list_is_empty_list() -> None:
    assert normalize_allowed_ports([]) == []


def test_valid_ports_are_sorted_and_deduplicated() -> None:
    assert normalize_allowed_ports([8443, 443, 8443, 80]) == [80, 443, 8443]


def test_boundary_ports_accepted() -> None:
    assert normalize_allowed_ports([1, 65535]) == [1, 65535]


@pytest.mark.parametrize(
    "value",
    [
        "443",  # bare string, not a list
        443,  # bare int, not a list
        (443,),  # tuple is not a list
        {443},  # set is not a list
        {"port": 443},  # mapping is not a list
        ["443"],  # numeric string element
        ["https"],  # non-numeric string element
        [443.0],  # float element
        [8443, None],  # None element
        [True],  # bool masquerading as port 1
        [False],  # bool masquerading as port 0
        [0],  # zero is reserved
        [-1],  # negative
        [65536],  # above the valid range
        [70000],  # well above the valid range
    ],
)
def test_invalid_representations_rejected(value: object) -> None:
    with pytest.raises(InvalidPortError):
        normalize_allowed_ports(value)
