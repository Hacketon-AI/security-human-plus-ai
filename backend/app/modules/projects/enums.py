"""Project domain enumerations."""

from enum import StrEnum


class ProjectStatus(StrEnum):
    """Lifecycle of a project.

    Only an ``active`` project accepts new assets; ``suspended`` and
    ``archived`` do not. There is no hard delete.
    """

    active = "active"
    suspended = "suspended"
    archived = "archived"
