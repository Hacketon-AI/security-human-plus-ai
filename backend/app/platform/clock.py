"""A minimal clock boundary for application-generated timestamps.

Use this for timestamps the application decides (e.g. when verification was
requested), so those moments are injectable and testable. It is deliberately
tiny — one protocol and the production implementation — not a time framework.
Database-managed timestamps (``created_at``/``updated_at``) keep using the
database clock and are unaffected.
"""

from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    """Source of the current instant as a timezone-aware datetime."""

    def now(self) -> datetime: ...


class SystemClock:
    """Production clock: the current time in UTC, timezone aware."""

    def now(self) -> datetime:
        return datetime.now(tz=UTC)


def get_clock() -> Clock:
    """FastAPI dependency returning the application clock."""
    return SystemClock()
