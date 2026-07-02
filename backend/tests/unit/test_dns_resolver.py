"""Unit tests for the dnspython TXT resolver adapter.

The dnspython call is monkeypatched so the parsing, bounding, and
definitive-vs-transient outcome logic are exercised without real DNS.
"""

from collections.abc import Iterator

import dns.asyncresolver
import dns.exception
import dns.resolver
import pytest
from app.modules.asset_verifications.dns_resolver import (
    DnspythonTxtResolver,
    DnsResolutionUnavailable,
)


class _FakeRdata:
    def __init__(self, *segments: bytes) -> None:
        self.strings = segments


class _FakeAnswer:
    def __init__(self, rdatas: list[_FakeRdata]) -> None:
        self._rdatas = rdatas

    def __iter__(self) -> Iterator[_FakeRdata]:
        return iter(self._rdatas)


def _patch_resolve(monkeypatch: pytest.MonkeyPatch, behaviour: object) -> None:
    async def _fake(qname: str, rdtype: str, lifetime: float | None = None) -> object:
        if isinstance(behaviour, Exception):
            raise behaviour
        return behaviour

    monkeypatch.setattr(dns.asyncresolver, "resolve", _fake)


async def test_joins_segmented_txt_strings(monkeypatch: pytest.MonkeyPatch) -> None:
    answer = _FakeAnswer([_FakeRdata(b"securescope-", b"verification=abc")])
    _patch_resolve(monkeypatch, answer)

    values = await DnspythonTxtResolver().resolve_txt("_x.example.com", 5.0)

    assert list(values) == ["securescope-verification=abc"]


async def test_nxdomain_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_resolve(monkeypatch, dns.resolver.NXDOMAIN())
    assert list(await DnspythonTxtResolver().resolve_txt("_x.example.com", 5.0)) == []


async def test_no_answer_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_resolve(monkeypatch, dns.resolver.NoAnswer())
    assert list(await DnspythonTxtResolver().resolve_txt("_x.example.com", 5.0)) == []


async def test_timeout_is_transient(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_resolve(monkeypatch, dns.exception.Timeout())
    with pytest.raises(DnsResolutionUnavailable):
        await DnspythonTxtResolver().resolve_txt("_x.example.com", 5.0)


async def test_oversized_value_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    answer = _FakeAnswer([_FakeRdata(b"x" * 4096), _FakeRdata(b"ok")])
    _patch_resolve(monkeypatch, answer)

    values = await DnspythonTxtResolver().resolve_txt("_x.example.com", 5.0)

    assert list(values) == ["ok"]
