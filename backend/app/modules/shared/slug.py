"""Slug normalization shared by organizations and projects.

A slug is a stable, URL-safe identifier within a tenant scope. Two entry points
exist on purpose:

- :func:`normalize_slug` validates a client-supplied slug strictly and rejects
  anything that is not already canonical, so the stored value is predictable.
- :func:`slugify` derives a slug from a human name when the client supplied
  none, lowercasing and collapsing runs of non-alphanumerics.
"""

import re

from app.platform.errors import DomainValidationError

# Canonical form: lowercase alphanumeric groups joined by single hyphens.
_CANONICAL_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_MAX_SLUG_LENGTH = 100


class SlugFormatError(DomainValidationError):
    """A slug is empty, too long, or not in canonical form."""

    code = "invalid_slug"


def normalize_slug(raw: str) -> str:
    """Validate and return a client-supplied slug in canonical form.

    Rejects rather than rewrites: a non-canonical slug is a client error, so the
    stored identifier is never silently different from what was requested.
    """
    candidate = raw.strip().lower()
    if len(candidate) > _MAX_SLUG_LENGTH or not _CANONICAL_SLUG.fullmatch(candidate):
        raise SlugFormatError(f"slug is not in canonical form: {raw!r}")
    return candidate


def slugify(name: str) -> str:
    """Derive a canonical slug from a display name.

    Used only when the client supplies no slug. Raises when the name has no
    usable alphanumeric content rather than returning an empty identifier.
    """
    candidate = _NON_ALNUM.sub("-", name.strip().lower()).strip("-")
    if not candidate:
        raise SlugFormatError(f"cannot derive a slug from name: {name!r}")
    return candidate[:_MAX_SLUG_LENGTH].strip("-")
