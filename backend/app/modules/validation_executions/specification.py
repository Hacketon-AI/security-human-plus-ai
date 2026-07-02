"""Builders for the immutable execution specification and snapshots.

The control plane records *intent*. What an isolated worker would eventually
receive is an immutable execution specification carrying exactly the controls
required by ``.claude/rules/scan-authorization.md``: target, authorization,
explicit scope allow-list, testing window, rate limit, kill-switch reference,
and the intrusive flag (always passive here).

These builders are pure: given already-validated domain objects they return
plain JSON-serializable dicts. They never perform I/O and never embed secrets
or long-lived credentials (the worker credential is provisioned out-of-band by
the future orchestrator, never in this spec).
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from app.modules.assets.enums import AssetCriticality
from app.modules.assets.models import Asset
from app.modules.authorizations.models import Authorization, AuthorizationScope
from app.modules.engagements.models import Engagement, EngagementScope
from app.modules.shared.network_ports import InvalidPortError, normalize_allowed_ports
from app.modules.validation_executions.errors import InvalidExecutionScope
from app.modules.validation_executions.templates import ValidationTemplate

# Assets whose responses are sensitive enough that a missing Cache-Control
# hardening directive is itself a finding. Criticality is the asset's explicit
# sensitivity classification, so it is the signal the executor's optional
# Cache-Control check keys off — no extra request, target, or method is added.
_SENSITIVE_CRITICALITIES = frozenset({AssetCriticality.high, AssetCriticality.critical})


def build_scope_snapshot(
    asset: Asset,
    authorization_scope: AuthorizationScope | None,
    engagement_scope: EngagementScope,
) -> dict[str, Any]:
    """Capture the effective, immutable scope at queue time.

    Engagement-scope overrides take precedence over authorization-scope
    defaults; the snapshot freezes them so later edits to the source rows do
    not change what was authorized for this execution.

    ``allowed_ports`` is normalized to a structured ``list[int]`` (or ``None``)
    before it is frozen. Both scope columns are written as validated JSON, so
    this is defense-in-depth: a malformed stored representation blocks dispatch
    with :class:`InvalidExecutionScope` rather than reaching an isolated worker.
    """
    allowed_paths = engagement_scope.allowed_paths
    excluded_paths = engagement_scope.excluded_paths
    allowed_ports = engagement_scope.allowed_ports
    if authorization_scope is not None:
        if allowed_paths is None:
            allowed_paths = authorization_scope.allowed_paths
        if excluded_paths is None:
            excluded_paths = authorization_scope.excluded_paths
        if allowed_ports is None:
            allowed_ports = authorization_scope.allowed_ports

    try:
        normalized_ports = normalize_allowed_ports(allowed_ports)
    except InvalidPortError as exc:
        raise InvalidExecutionScope(f"scope allowed_ports is invalid: {exc}") from exc

    return {
        "asset_id": str(asset.id),
        "target": asset.target,
        "asset_type": asset.asset_type.value,
        "environment": asset.environment.value,
        "engagement_scope_id": str(engagement_scope.id),
        "authorization_scope_id": (
            str(authorization_scope.id) if authorization_scope is not None else None
        ),
        "allowed_paths": allowed_paths,
        "excluded_paths": excluded_paths,
        "allowed_ports": normalized_ports,
    }


def build_safety_snapshot(
    template: ValidationTemplate,
    engagement: Engagement,
    engagement_scope: EngagementScope,
    kill_switch_active: bool,
) -> dict[str, Any]:
    """Freeze the safety envelope at queue time.

    Rate-limit and concurrency come from the engagement scope override or the
    engagement defaults; the rest are the template's fixed bounds. The kill
    switch state is captured so the dispatch decision is auditable.
    """
    rate_limit = (
        engagement_scope.rate_limit_per_minute
        if engagement_scope.rate_limit_per_minute is not None
        else engagement.default_rate_limit_per_minute
    )
    concurrency = (
        engagement_scope.concurrency_limit
        if engagement_scope.concurrency_limit is not None
        else engagement.default_concurrency_limit
    )
    limits = template.safety_limits
    return {
        "rate_limit_per_minute": rate_limit,
        "concurrency_limit": concurrency,
        "timeout_seconds": limits.timeout_seconds,
        "redirect_limit": limits.redirect_limit,
        "max_requests": limits.max_requests,
        "max_response_bytes": limits.max_response_bytes,
        "kill_switch_active": kill_switch_active,
        "intrusive": False,
    }


def build_execution_specification(
    execution_id: UUID,
    template: ValidationTemplate,
    asset: Asset,
    authorization: Authorization,
    engagement: Engagement,
    scope_snapshot: dict[str, Any],
    safety_snapshot: dict[str, Any],
    testing_window_start: datetime,
    testing_window_end: datetime,
    kill_switch_token: str,
) -> dict[str, Any]:
    """Assemble the immutable spec a worker would consume.

    Carries every control required before dispatch. Contains no secret payload:
    ``kill_switch_token`` is an opaque poll key, not a credential, and there is
    no long-lived secret in the spec.

    ``sensitive_path`` is an explicit spec-only flag (no DB column): the
    worker-side executor uses it to decide whether a missing/weak Cache-Control
    header is a finding. It is derived from the asset's criticality, not a new
    scanning input, so it never broadens what is requested.
    """
    return {
        "execution_id": str(execution_id),
        "template_id": template.template_id,
        "risk_tier": template.risk_tier.value,
        "allowed_methods": list(template.allowed_methods),
        "intrusive": False,
        "sensitive_path": asset.criticality in _SENSITIVE_CRITICALITIES,
        "asset_id": str(asset.id),
        "target": asset.target,
        "authorization_id": str(authorization.id),
        "engagement_id": str(engagement.id),
        "scope": scope_snapshot,
        "safety": safety_snapshot,
        "testing_window": {
            "start": testing_window_start.isoformat(),
            "end": testing_window_end.isoformat(),
        },
        "rate_limit_per_minute": safety_snapshot["rate_limit_per_minute"],
        "kill_switch_token": kill_switch_token,
    }
