"""Unit tests for engagement state transition validation."""

import pytest
from app.modules.engagements.enums import EngagementStatus
from app.modules.engagements.errors import InvalidEngagementStateTransition
from app.modules.engagements.service import EngagementService

# All allowed transitions per the domain rules.
_ALLOWED = [
    (EngagementStatus.draft, EngagementStatus.scheduled),
    (EngagementStatus.draft, EngagementStatus.cancelled),
    (EngagementStatus.scheduled, EngagementStatus.active),
    (EngagementStatus.scheduled, EngagementStatus.cancelled),
    (EngagementStatus.active, EngagementStatus.paused),
    (EngagementStatus.active, EngagementStatus.completed),
    (EngagementStatus.paused, EngagementStatus.active),
    (EngagementStatus.paused, EngagementStatus.cancelled),
]


@pytest.mark.parametrize("current,target", _ALLOWED)
def test_allowed_transition_does_not_raise(
    current: EngagementStatus, target: EngagementStatus
) -> None:
    EngagementService._ensure_transition_allowed(current, target)


# A sample of invalid transitions covering each terminal state.
_INVALID = [
    (EngagementStatus.draft, EngagementStatus.active),
    (EngagementStatus.draft, EngagementStatus.paused),
    (EngagementStatus.draft, EngagementStatus.completed),
    (EngagementStatus.scheduled, EngagementStatus.paused),
    (EngagementStatus.scheduled, EngagementStatus.completed),
    (EngagementStatus.scheduled, EngagementStatus.draft),
    (EngagementStatus.active, EngagementStatus.scheduled),
    (EngagementStatus.active, EngagementStatus.draft),
    (EngagementStatus.active, EngagementStatus.cancelled),
    (EngagementStatus.paused, EngagementStatus.completed),
    (EngagementStatus.paused, EngagementStatus.scheduled),
    (EngagementStatus.completed, EngagementStatus.active),
    (EngagementStatus.completed, EngagementStatus.cancelled),
    (EngagementStatus.cancelled, EngagementStatus.active),
    (EngagementStatus.cancelled, EngagementStatus.draft),
]


@pytest.mark.parametrize("current,target", _INVALID)
def test_invalid_transition_raises(
    current: EngagementStatus, target: EngagementStatus
) -> None:
    with pytest.raises(InvalidEngagementStateTransition):
        EngagementService._ensure_transition_allowed(current, target)
