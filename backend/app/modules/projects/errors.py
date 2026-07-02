"""Project domain errors."""

from app.platform.errors import ConflictError, NotFoundError


class ProjectNotFound(NotFoundError):
    """No project with this id is visible to the caller's tenant."""

    code = "project_not_found"


class ProjectSlugConflict(ConflictError):
    """Another project in the same organization already uses this slug."""

    code = "project_slug_conflict"


class ProjectNotAcceptingAssets(ConflictError):
    """The project's lifecycle state forbids registering new assets."""

    code = "project_not_accepting_assets"
