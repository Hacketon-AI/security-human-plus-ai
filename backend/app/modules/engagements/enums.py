"""Engagement domain enumerations."""

from enum import StrEnum


class EngagementStatus(StrEnum):
    """Lifecycle of an operational engagement.

    ``draft`` is editable. ``scheduled`` has a confirmed testing window.
    ``active`` means testing is in progress. ``paused`` suspends
    execution. ``completed`` and ``cancelled`` are terminal.
    """

    draft = "draft"
    scheduled = "scheduled"
    active = "active"
    paused = "paused"
    completed = "completed"
    cancelled = "cancelled"
