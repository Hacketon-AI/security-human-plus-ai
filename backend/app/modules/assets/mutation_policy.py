"""Policy for which asset fields may change via the general PATCH endpoint.

This is the single place that decides allowed mutations per asset state; the
route, ORM model, and request schema do not encode these rules. The PATCH
endpoint only ever edits metadata (name, criticality); identity and scope fields
(target, asset_type, project_id, organization_id, environment, status) are not
mutable here and are reaffirmed below as defense in depth.

State rules:

- ``draft``: name and criticality may change.
- ``pending_verification``: name and criticality may change. These do not touch
  the verification challenge, which is keyed to the asset's target/type — and
  those are not editable here — so an in-flight challenge is never invalidated.
- ``verified``: name and criticality may change; identity/scope fields may not.
- ``suspended``: not modifiable via the general PATCH endpoint.
- ``retired``: immutable.
"""

from collections.abc import Iterable

from app.modules.assets.enums import AssetStatus
from app.modules.assets.errors import AssetMutationNotAllowed

# States in which editable metadata may be changed via PATCH.
_METADATA_MUTABLE_STATUSES = frozenset(
    {AssetStatus.draft, AssetStatus.pending_verification, AssetStatus.verified}
)

# Fields the PATCH endpoint is permitted to change.
_EDITABLE_FIELDS = frozenset({"name", "criticality"})


def ensure_metadata_update_allowed(
    status: AssetStatus, requested_fields: Iterable[str]
) -> None:
    """Raise :class:`AssetMutationNotAllowed` if the update is not permitted."""
    if status not in _METADATA_MUTABLE_STATUSES:
        raise AssetMutationNotAllowed(
            f"assets in status {status.value} cannot be modified via patch"
        )
    disallowed = sorted(set(requested_fields) - _EDITABLE_FIELDS)
    if disallowed:
        raise AssetMutationNotAllowed(
            "only name and criticality may be updated; rejected: "
            + ", ".join(disallowed)
        )
