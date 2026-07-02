"""Unit tests for slug normalization and derivation."""

import pytest
from app.modules.shared.slug import SlugFormatError, normalize_slug, slugify


def test_normalize_slug_accepts_canonical() -> None:
    assert normalize_slug("acme-bank") == "acme-bank"


def test_normalize_slug_lowercases_and_trims() -> None:
    assert normalize_slug("  Acme-Bank  ") == "acme-bank"


@pytest.mark.parametrize(
    "raw",
    ["acme bank", "acme_bank", "-acme", "acme-", "acme--bank", "acmé", ""],
)
def test_normalize_slug_rejects_non_canonical(raw: str) -> None:
    with pytest.raises(SlugFormatError):
        normalize_slug(raw)


def test_normalize_slug_rejects_overlong() -> None:
    with pytest.raises(SlugFormatError):
        normalize_slug("a" * 101)


def test_slugify_derives_from_name() -> None:
    assert slugify("Acme Bank, Ltd.") == "acme-bank-ltd"


def test_slugify_collapses_separators() -> None:
    assert slugify("  Core   Banking  ") == "core-banking"


def test_slugify_rejects_name_without_alphanumerics() -> None:
    with pytest.raises(SlugFormatError):
        slugify("   ---   ")
