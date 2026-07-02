"""Pydantic response models for the asset verification API.

The create, verify, and cancel endpoints take no request body: the token,
record name, and expiry are all server-derived, so a client can neither choose
the DNS record nor supply an expected token.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.modules.asset_verifications.enums import ChallengeMethod, ChallengeStatus
from app.modules.assets.enums import AssetStatus


class VerificationChallengeCreatedResponse(BaseModel):
    """Returned once, at create time. Carries the full record value to publish."""

    model_config = ConfigDict(extra="forbid")

    challenge_id: UUID
    method: ChallengeMethod
    record_name: str
    record_type: str
    record_value: str
    expires_at: datetime
    maximum_attempts: int


class VerificationChallengeResponse(BaseModel):
    """Current-challenge view. Never includes the raw token or full TXT value."""

    model_config = ConfigDict(extra="forbid")

    challenge_id: UUID
    method: ChallengeMethod
    status: ChallengeStatus
    record_name: str
    record_type: str
    token_last_four: str
    attempts: int
    maximum_attempts: int
    expires_at: datetime
    verified_at: datetime | None
    last_attempted_at: datetime | None


class VerificationResultResponse(BaseModel):
    """Outcome of a verify attempt, with a sanitized human-readable message."""

    model_config = ConfigDict(extra="forbid")

    challenge_id: UUID
    challenge_status: ChallengeStatus
    asset_status: AssetStatus
    attempts: int
    verified_at: datetime | None
    message: str


class VerificationChallengeCancelledResponse(BaseModel):
    """Result of cancelling a challenge."""

    model_config = ConfigDict(extra="forbid")

    challenge_id: UUID
    challenge_status: ChallengeStatus
