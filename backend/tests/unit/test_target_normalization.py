"""Unit tests for per-asset-type target normalization."""

import pytest
from app.modules.assets.enums import AssetType
from app.modules.assets.errors import InvalidAssetTarget
from app.modules.assets.target import normalize_target


@pytest.mark.parametrize(
    "asset_type",
    [AssetType.web_application, AssetType.api, AssetType.repository],
)
def test_https_url_is_lowercased_and_fragment_dropped(asset_type: AssetType) -> None:
    result = normalize_target(asset_type, "HTTPS://API.Example.COM/v1#frag")
    assert result == "https://api.example.com/v1"


@pytest.mark.parametrize(
    "asset_type",
    [AssetType.web_application, AssetType.api, AssetType.repository],
)
def test_plain_http_is_rejected(asset_type: AssetType) -> None:
    with pytest.raises(InvalidAssetTarget):
        normalize_target(asset_type, "http://example.com")


def test_embedded_credentials_are_rejected() -> None:
    with pytest.raises(InvalidAssetTarget):
        normalize_target(AssetType.web_application, "https://user:pass@example.com")


def test_ipv6_address_is_normalized() -> None:
    # Compressed/expanded forms collapse to one canonical representation.
    assert normalize_target(AssetType.ip_address, "2001:0DB8::0001") == "2001:db8::1"


def test_invalid_ip_is_rejected() -> None:
    with pytest.raises(InvalidAssetTarget):
        normalize_target(AssetType.ip_address, "999.1.1.1")


def test_ipv4_with_ambiguous_leading_zero_octet_is_rejected() -> None:
    # Leading-zero octets are an SSRF/parsing-ambiguity vector; reject them.
    with pytest.raises(InvalidAssetTarget):
        normalize_target(AssetType.ip_address, "192.168.000.1")


def test_cidr_is_normalized() -> None:
    assert normalize_target(AssetType.cidr_range, "10.0.0.0/24") == "10.0.0.0/24"


def test_cidr_with_host_bits_set_is_rejected() -> None:
    with pytest.raises(InvalidAssetTarget):
        normalize_target(AssetType.cidr_range, "10.0.0.5/24")


def test_mobile_identifier_is_accepted() -> None:
    assert (
        normalize_target(AssetType.mobile_application, "com.acme.bank")
        == "com.acme.bank"
    )


def test_mobile_identifier_with_space_is_rejected() -> None:
    with pytest.raises(InvalidAssetTarget):
        normalize_target(AssetType.mobile_application, "com acme bank")


def test_service_endpoint_with_port_is_accepted() -> None:
    assert normalize_target(AssetType.service, "Gateway.internal:8443") == (
        "gateway.internal:8443"
    )


def test_service_endpoint_port_out_of_range_is_rejected() -> None:
    with pytest.raises(InvalidAssetTarget):
        normalize_target(AssetType.service, "gateway.internal:70000")


def test_empty_target_is_rejected() -> None:
    with pytest.raises(InvalidAssetTarget):
        normalize_target(AssetType.web_application, "   ")
