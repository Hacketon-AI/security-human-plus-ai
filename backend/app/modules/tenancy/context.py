"""The authenticated tenant context carried through request handling.

Every tenant-scoped use case takes a :class:`TenantContext`. It is the single
source of the caller's ``organization_id``; that value is never read from a
request body, so a client cannot assert ownership of another tenant's data.
"""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class TenantContext:
    """Immutable tenant identity resolved by the authentication adapter."""

    organization_id: UUID
