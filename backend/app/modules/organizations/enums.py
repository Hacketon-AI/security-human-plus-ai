"""Organization domain enumerations."""

from enum import StrEnum


class OrganizationStatus(StrEnum):
    """Lifecycle of a tenant root.

    ``archived`` and ``suspended`` are terminal-for-intake: an organization in
    either state cannot accept new projects. There is no hard delete.
    """

    active = "active"
    suspended = "suspended"
    archived = "archived"
