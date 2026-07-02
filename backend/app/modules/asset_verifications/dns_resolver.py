"""DNS TXT resolution at the verification I/O boundary.

A tiny interface so the service can be unit-tested with a deterministic resolver
while production performs real lookups via dnspython. This is ownership-proof
metadata resolution (a DNS query for a dedicated verification record), not a
scanner: it sends no traffic to the asset and runs in the control plane.

The contract distinguishes two definitive-vs-transient outcomes:

- an empty sequence means the name resolved with no usable TXT record
  (NXDOMAIN / no answer) — a definitive "not found";
- a raised :class:`DnsResolutionUnavailable` means a transient resolver failure
  (timeout, SERVFAIL) — the verification result is inconclusive.
"""

from collections.abc import Sequence
from typing import Protocol

import dns.asyncresolver
import dns.exception
import dns.resolver

# Bound the work done on a response so a hostile zone cannot force unbounded
# processing.
_MAX_RECORDS = 50
_MAX_VALUE_BYTES = 2048


class DnsResolutionUnavailable(Exception):
    """A transient DNS failure; the verification attempt is inconclusive."""


class DnsTxtResolver(Protocol):
    """Resolves TXT values for an exact record name within a timeout."""

    async def resolve_txt(
        self, record_name: str, timeout_seconds: float
    ) -> Sequence[str]: ...


class DnspythonTxtResolver:
    """Production resolver backed by dnspython's async resolver."""

    async def resolve_txt(
        self, record_name: str, timeout_seconds: float
    ) -> Sequence[str]:
        try:
            answer = await dns.asyncresolver.resolve(
                record_name, "TXT", lifetime=timeout_seconds
            )
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
            # Definitive: the verification record is not present.
            return []
        except (
            dns.resolver.NoNameservers,
            dns.resolver.LifetimeTimeout,
            dns.exception.Timeout,
        ) as exc:
            # Transient: do not let this masquerade as a definitive failure.
            raise DnsResolutionUnavailable("dns resolution unavailable") from exc
        except dns.exception.DNSException as exc:
            raise DnsResolutionUnavailable("dns resolution failed") from exc

        values: list[str] = []
        for rdata in list(answer)[:_MAX_RECORDS]:
            # Join segmented TXT character-strings per RFC 1035 (one logical
            # value), then bound and decode defensively.
            joined = b"".join(rdata.strings)
            if len(joined) > _MAX_VALUE_BYTES:
                continue
            try:
                values.append(joined.decode("utf-8"))
            except UnicodeDecodeError:
                continue
        return values


def get_dns_txt_resolver() -> DnsTxtResolver:
    """FastAPI dependency returning the production DNS TXT resolver."""
    return DnspythonTxtResolver()
