"""Strict normalization for the network-port allow-lists on scope definitions.

A scope's ``allowed_ports`` is part of the explicit allow-list that is frozen
into the immutable worker execution snapshot (see
``.claude/rules/scan-authorization.md`` — scope is an allow-list, never free
text). The control plane must therefore guarantee a structured ``list[int]`` and
reject anything ambiguous, so a stray string or float can never widen, narrow,
or misrepresent the permitted ports once the spec leaves the orchestrator.

``normalize_allowed_ports`` is the single normalization point; both the request
schemas (via :data:`AllowedPortList`) and the snapshot builder use it so the
rule is enforced identically at the API edge and at queue time.
"""

from typing import Annotated, Final

from pydantic import BeforeValidator

# TCP/UDP port range. Port 0 is reserved and never a valid scan target.
MIN_PORT: Final = 1
MAX_PORT: Final = 65535


class InvalidPortError(ValueError):
    """A port allow-list entry is not a valid integer port in ``1..65535``.

    Subclasses :class:`ValueError` so Pydantic surfaces it as a 422 validation
    error at the request edge; the snapshot builder translates it into a domain
    error so a malformed stored value blocks dispatch instead of reaching a
    worker.
    """


def normalize_allowed_ports(value: object) -> list[int] | None:
    """Validate a port allow-list and return it sorted and de-duplicated.

    ``None`` passes through unchanged (no port restriction recorded). A list is
    accepted only when every entry is a genuine integer port in
    ``MIN_PORT..MAX_PORT``. Booleans are rejected explicitly (``bool`` is an
    ``int`` subclass, so ``True``/``False`` would otherwise pose as ports 1/0),
    and strings and floats are rejected rather than coerced — coercion is how an
    ambiguous value silently becomes the wrong port. The result is sorted and
    de-duplicated so the frozen snapshot is canonical.
    """
    if value is None:
        return None
    if not isinstance(value, list):
        raise InvalidPortError("allowed_ports must be a list of integer ports")
    ports: set[int] = set()
    for entry in value:
        if isinstance(entry, bool) or not isinstance(entry, int):
            raise InvalidPortError("allowed_ports entries must be integers")
        if entry < MIN_PORT or entry > MAX_PORT:
            raise InvalidPortError(
                f"allowed_ports entries must be in {MIN_PORT}..{MAX_PORT}"
            )
        ports.add(entry)
    return sorted(ports)


# Reusable schema field type: a structured port allow-list normalized at the
# request edge. ``BeforeValidator`` runs ``normalize_allowed_ports`` ahead of
# Pydantic's own list coercion, so invalid entries are rejected before any lax
# int coercion can mask them.
AllowedPortList = Annotated[list[int] | None, BeforeValidator(normalize_allowed_ports)]
