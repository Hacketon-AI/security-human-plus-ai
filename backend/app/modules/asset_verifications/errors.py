"""Asset verification domain errors."""

from app.platform.errors import ConflictError, DomainValidationError, NotFoundError


class VerificationChallengeNotFound(NotFoundError):
    """No matching challenge is visible to the caller's tenant."""

    code = "verification_challenge_not_found"


class UnsupportedVerificationAssetType(DomainValidationError):
    """The asset type does not support DNS TXT ownership verification."""

    code = "unsupported_verification_asset_type"


class AssetNotPendingVerification(ConflictError):
    """The asset is not in ``pending_verification`` and cannot be verified."""

    code = "asset_not_pending_verification"


class InactiveVerificationTarget(ConflictError):
    """The owning project or organization is not active."""

    code = "inactive_verification_target"


class VerificationChallengeNotActive(ConflictError):
    """The challenge is in a terminal state that cannot be verified or cancelled."""

    code = "verification_challenge_not_active"


class ActiveChallengeConflict(ConflictError):
    """A pending challenge already exists for the asset (uniqueness race)."""

    code = "active_verification_challenge_exists"
