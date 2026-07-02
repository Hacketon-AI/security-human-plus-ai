"""Organization domain errors."""

from app.platform.errors import ConflictError, NotFoundError


class OrganizationNotFound(NotFoundError):
    """No organization with this id is visible to the caller."""

    code = "organization_not_found"


class OrganizationSlugConflict(ConflictError):
    """Another organization already uses this slug."""

    code = "organization_slug_conflict"


class OrganizationNotAcceptingProjects(ConflictError):
    """The organization's lifecycle state forbids creating new projects."""

    code = "organization_not_accepting_projects"
