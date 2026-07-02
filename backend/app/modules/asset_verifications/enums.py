"""Asset verification domain enumerations."""

from enum import StrEnum


class ChallengeMethod(StrEnum):
    """Supported ownership-proof methods. Only DNS TXT exists in this stage."""

    dns_txt = "dns_txt"


class ChallengeStatus(StrEnum):
    """Lifecycle of a verification challenge.

    ``pending`` is the only verifiable state. ``verified``/``expired``/
    ``failed``/``cancelled`` are terminal.
    """

    pending = "pending"
    verified = "verified"
    expired = "expired"
    failed = "failed"
    cancelled = "cancelled"
