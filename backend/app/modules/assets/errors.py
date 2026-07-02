"""Asset domain errors."""

from app.platform.errors import ConflictError, DomainValidationError, NotFoundError


class AssetNotFound(NotFoundError):
    """No asset with this id is visible to the caller's tenant."""

    code = "asset_not_found"


class InvalidAssetTarget(DomainValidationError):
    """The supplied target is invalid for the asset type."""

    code = "invalid_asset_target"


class InvalidAssetStateTransition(ConflictError):
    """The requested transition is not allowed from the asset's current state."""

    code = "invalid_asset_state_transition"


class AssetMutationNotAllowed(ConflictError):
    """The requested field update is not permitted for the asset's state."""

    code = "asset_mutation_not_allowed"
