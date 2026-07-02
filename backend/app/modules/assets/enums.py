"""Asset domain enumerations."""

from enum import StrEnum


class AssetType(StrEnum):
    """The kind of target an asset represents. Drives target normalization."""

    web_application = "web_application"
    api = "api"
    mobile_application = "mobile_application"
    ip_address = "ip_address"
    cidr_range = "cidr_range"
    repository = "repository"
    service = "service"


class AssetEnvironment(StrEnum):
    """Deployment environment of the asset. Production carries extra controls."""

    development = "development"
    staging = "staging"
    preproduction = "preproduction"
    production = "production"


class AssetCriticality(StrEnum):
    """Business criticality of the asset."""

    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class AssetStatus(StrEnum):
    """Asset lifecycle.

    An asset is registered as ``draft`` and may request verification, moving to
    ``pending_verification``. The transition to ``verified`` is owned by a
    separate verification use case (not in this stage) and is never set
    directly by a client. There is no hard delete; ``suspended`` and
    ``retired`` are lifecycle states.
    """

    draft = "draft"
    pending_verification = "pending_verification"
    verified = "verified"
    suspended = "suspended"
    retired = "retired"


class VerificationMethod(StrEnum):
    """How ownership of an asset is to be proven.

    The challenge and proof flow are built in a later stage; here the requested
    method is only recorded.
    """

    dns_txt_record = "dns_txt_record"
    http_file = "http_file"
    manual_attestation = "manual_attestation"
