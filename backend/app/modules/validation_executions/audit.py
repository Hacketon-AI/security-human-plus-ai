"""Audit events for validation-execution lifecycle decisions.

``.claude/rules/data-handling.md`` requires audit events that record who, what,
when, and the decision — never the secret payload. This emits structured,
sanitized records through the standard logging boundary. It is deliberately
small: one event shape and one emitter, not an audit framework.
"""

import logging
from typing import Any
from uuid import UUID

_logger = logging.getLogger("securescope.audit.validation_executions")


def record_execution_event(
    *,
    action: str,
    organization_id: UUID,
    execution_id: UUID,
    actor: str | None,
    decision: str,
    detail: str | None = None,
) -> None:
    """Emit one sanitized audit event.

    Only identifiers, the action, and the decision are recorded. No execution
    specification, scope payload, kill-switch token, or result body is logged —
    those may carry sensitive data and live only in the database row.
    """
    event: dict[str, Any] = {
        "action": action,
        "organization_id": str(organization_id),
        "execution_id": str(execution_id),
        "actor": actor or "unknown",
        "decision": decision,
    }
    if detail is not None:
        event["detail"] = detail
    _logger.info("validation_execution_audit", extra={"audit": event})
