"""Helpers for interpreting database integrity errors at the domain boundary.

The database's unique constraints are the source of truth for uniqueness. When a
race slips past an application-level pre-check, the resulting
``IntegrityError`` is translated into the correct domain conflict — but only for
the specific constraint involved. Any other integrity error is left to surface
as a safe internal error, never reinterpreted as a conflict, and the raw
database message is never exposed to callers.
"""

from sqlalchemy.exc import IntegrityError


def unique_violation_constraint(error: IntegrityError) -> str | None:
    """Return the violated constraint name, if the driver reported one.

    asyncpg exposes ``constraint_name`` on its unique-violation errors, but
    SQLAlchemy wraps that error: ``error.orig`` is the DBAPI adapter and the
    original asyncpg exception sits on its ``__cause__`` chain. Walk the chain
    and return the first string ``constraint_name`` found, so callers can match
    it exactly. Returns ``None`` when no constraint name is available, leaving
    such errors to surface as safe internal errors.
    """
    cause: BaseException | None = error.orig
    while cause is not None:
        constraint = getattr(cause, "constraint_name", None)
        if isinstance(constraint, str):
            return constraint
        cause = cause.__cause__
    return None
