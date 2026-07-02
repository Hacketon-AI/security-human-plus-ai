"""Unit tests for authorization state transition validation."""

import pytest
from app.modules.authorizations.enums import AuthorizationStatus
from app.modules.authorizations.errors import InvalidAuthorizationStateTransition
from app.modules.authorizations.service import AuthorizationService

# All allowed transitions per the domain rules.
_ALLOWED = [
    (AuthorizationStatus.draft, AuthorizationStatus.submitted),
    (AuthorizationStatus.submitted, AuthorizationStatus.active),
    (AuthorizationStatus.submitted, AuthorizationStatus.rejected),
    (AuthorizationStatus.active, AuthorizationStatus.revoked),
    (AuthorizationStatus.active, AuthorizationStatus.expired),
]


@pytest.mark.parametrize("current,target", _ALLOWED)
def test_allowed_transition_does_not_raise(
    current: AuthorizationStatus, target: AuthorizationStatus
) -> None:
    AuthorizationService._ensure_transition_allowed(current, target)


# A sample of invalid transitions covering each terminal state.
_INVALID = [
    (AuthorizationStatus.draft, AuthorizationStatus.active),
    (AuthorizationStatus.draft, AuthorizationStatus.rejected),
    (AuthorizationStatus.draft, AuthorizationStatus.revoked),
    (AuthorizationStatus.draft, AuthorizationStatus.expired),
    (AuthorizationStatus.submitted, AuthorizationStatus.draft),
    (AuthorizationStatus.submitted, AuthorizationStatus.revoked),
    (AuthorizationStatus.active, AuthorizationStatus.submitted),
    (AuthorizationStatus.active, AuthorizationStatus.draft),
    (AuthorizationStatus.expired, AuthorizationStatus.active),
    (AuthorizationStatus.expired, AuthorizationStatus.draft),
    (AuthorizationStatus.revoked, AuthorizationStatus.active),
    (AuthorizationStatus.revoked, AuthorizationStatus.draft),
    (AuthorizationStatus.rejected, AuthorizationStatus.draft),
    (AuthorizationStatus.rejected, AuthorizationStatus.active),
    (AuthorizationStatus.rejected, AuthorizationStatus.submitted),
]


@pytest.mark.parametrize("current,target", _INVALID)
def test_invalid_transition_raises(
    current: AuthorizationStatus, target: AuthorizationStatus
) -> None:
    with pytest.raises(InvalidAuthorizationStateTransition):
        AuthorizationService._ensure_transition_allowed(current, target)
