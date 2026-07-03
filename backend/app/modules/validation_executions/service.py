"""Validation-execution use cases.

The control plane's execution boundary: it validates eligibility, freezes
immutable snapshots, queues the execution, hands an immutable specification to
the dispatch seam, and records lifecycle transitions. It never runs scanner
logic — that belongs to an isolated worker.
"""

import hmac
import secrets
from collections.abc import Sequence
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError

from app.modules.assets.enums import AssetStatus
from app.modules.assets.repository import AssetRepository
from app.modules.authorizations.enums import AuthorizationStatus, RiskTier
from app.modules.authorizations.models import AuthorizationScope
from app.modules.authorizations.repository import AuthorizationRepository
from app.modules.engagements.enums import EngagementStatus
from app.modules.engagements.models import EngagementScope
from app.modules.engagements.repository import EngagementRepository
from app.modules.projects.repository import ProjectRepository
from app.modules.shared.persistence import unique_violation_constraint
from app.modules.tenancy.context import TenantContext
from app.modules.validation_executions import audit
from app.modules.validation_executions.credential_repository import (
    WorkerCredentialRepository,
)
from app.modules.validation_executions.dispatcher import (
    ValidationDispatcher,
    WorkerDispatchPayload,
)
from app.modules.validation_executions.enums import (
    ExecutionOutcome,
    ExecutionStatus,
)
from app.modules.validation_executions.errors import (
    ExecutionEligibilityBlocked,
    ExecutionImmutableError,
    IdempotencyConflict,
    InvalidExecutionScope,
    InvalidExecutionStateTransition,
    ValidationExecutionNotFound,
    WorkerCredentialIssuanceFailed,
    WorkerKillSwitchAuthenticationFailed,
)
from app.modules.validation_executions.models import (
    ValidationExecution,
    ValidationStepResult,
)
from app.modules.validation_executions.repository import (
    ValidationExecutionRepository,
)
from app.modules.validation_executions.schemas import (
    ValidationExecutionCreate,
    WorkerFinishedRequest,
    WorkerStepResult,
)
from app.modules.validation_executions.specification import (
    build_execution_specification,
    build_safety_snapshot,
    build_scope_snapshot,
)
from app.modules.validation_executions.templates import get_template
from app.modules.validation_executions.worker_auth import WorkerContext
from app.modules.validation_executions.worker_credential_contracts import (
    WorkerCredentialHandoff,
    WorkerCredentialIssueOutcome,
    WorkerCredentialIssuer,
    WorkerHookAction,
)
from app.platform.clock import Clock

_NOT_FOUND = "validation execution not found"
_IDEMPOTENCY_CONSTRAINT = "uq_validation_execution_idempotency_key"

# Default lifetime of a per-execution worker credential minted at dispatch.
# Kept well under the issuer's hard cap (``DEFAULT_CREDENTIAL_HARD_TTL`` = 24h)
# and further bounded by the engagement testing-window end at issue time — a
# leaked token cannot outlive the window it was scoped to. A typical scan
# finishes in minutes; an hour is a comfortable ceiling for a single run.
_WORKER_CREDENTIAL_TTL = timedelta(hours=1)

# The hook actions a dispatch-time credential authorizes: one worker drives the
# full lifecycle (start then finish), so it is granted both.
_WORKER_CREDENTIAL_ACTIONS: frozenset[WorkerHookAction] = frozenset(
    {WorkerHookAction.worker_started, WorkerHookAction.worker_finished}
)

# Fields that determine whether two requests sharing an idempotency key are
# "the same request". A repeat with identical material returns the existing
# execution; any difference is a conflict.
_IDEMPOTENCY_MATERIAL_FIELDS = (
    "project_id",
    "asset_id",
    "authorization_id",
    "engagement_id",
    "engagement_scope_id",
    "template_id",
)

# Bound the sanitized result/evidence stored from a worker report.
_MAX_RESULT_SUMMARY = 4000
_MAX_ERROR_MESSAGE = 2000
_MAX_EVIDENCE_KEYS = 50
_MAX_EVIDENCE_VALUE_CHARS = 2000

_RISK_TIER_ORDER = {
    RiskTier.tier_0_passive: 0,
    RiskTier.tier_1_safe: 1,
    RiskTier.tier_2_controlled: 2,
    RiskTier.tier_3_critical: 3,
}


def _risk_tier_lte(a: RiskTier, b: RiskTier) -> bool:
    """Return True when risk tier ``a`` does not exceed ``b``."""
    return _RISK_TIER_ORDER.get(a, -1) <= _RISK_TIER_ORDER.get(b, -1)


class ValidationExecutionService:
    """Creates, queues, reads, cancels, and transitions validation executions."""

    def __init__(
        self,
        executions: ValidationExecutionRepository,
        engagements: EngagementRepository,
        authorizations: AuthorizationRepository,
        assets: AssetRepository,
        projects: ProjectRepository,
        dispatcher: ValidationDispatcher,
        clock: Clock,
        credential_issuer: WorkerCredentialIssuer,
        credentials: WorkerCredentialRepository,
    ) -> None:
        self._executions = executions
        self._engagements = engagements
        self._authorizations = authorizations
        self._assets = assets
        self._projects = projects
        self._dispatcher = dispatcher
        self._clock = clock
        self._credential_issuer = credential_issuer
        self._credentials = credentials

    # ------------------------------------------------------------------
    # Create + queue
    # ------------------------------------------------------------------

    async def create_and_queue(
        self, tenant: TenantContext, payload: ValidationExecutionCreate
    ) -> ValidationExecution:
        # Idempotency: a prior execution with the same key short-circuits.
        if payload.idempotency_key is not None:
            existing = await self._executions.get_by_idempotency_key(
                tenant.organization_id, payload.idempotency_key
            )
            if existing is not None:
                self._ensure_idempotent_match(existing, payload)
                return existing

        template = get_template(payload.template_id)

        # Resolve and validate every dependency under the tenant scope.
        engagement = await self._engagements.get_in_org(
            payload.engagement_id, tenant.organization_id
        )
        if engagement is None or engagement.project_id != payload.project_id:
            raise ExecutionEligibilityBlocked("engagement is not eligible")
        authorization = await self._authorizations.get_in_org(
            payload.authorization_id, tenant.organization_id
        )
        if authorization is None or authorization.project_id != payload.project_id:
            raise ExecutionEligibilityBlocked("authorization is not eligible")
        asset = await self._assets.get_in_org(payload.asset_id, tenant.organization_id)
        if asset is None or asset.project_id != payload.project_id:
            raise InvalidExecutionScope("asset is not eligible")

        engagement_scope = self._find_engagement_scope(
            engagement.scopes, payload.engagement_scope_id, payload.asset_id
        )

        now = self._clock.now()
        self._validate_asset(asset)
        self._validate_authorization(authorization, asset.id, template.risk_tier, now)
        authorization_scope = self._resolve_authorization_scope(
            authorization.scopes, asset.id, engagement_scope
        )
        self._validate_engagement(engagement, asset.id, template.risk_tier, now)

        # Freeze immutable snapshots at queue time.
        scope_snapshot = build_scope_snapshot(
            asset, authorization_scope, engagement_scope
        )
        safety_snapshot = build_safety_snapshot(
            template, engagement, engagement_scope, engagement.kill_switch_active
        )

        execution = ValidationExecution(
            id=uuid4(),
            organization_id=tenant.organization_id,
            project_id=payload.project_id,
            asset_id=asset.id,
            authorization_id=authorization.id,
            authorization_scope_id=(
                authorization_scope.id if authorization_scope is not None else None
            ),
            engagement_id=engagement.id,
            engagement_scope_id=engagement_scope.id,
            template_id=template.template_id,
            status=ExecutionStatus.queued,
            outcome=ExecutionOutcome.not_run,
            requested_by=(
                payload.requested_by.strip() if payload.requested_by else None
            ),
            idempotency_key=payload.idempotency_key,
            risk_tier=template.risk_tier,
            execution_specification={},
            scope_snapshot=scope_snapshot,
            safety_snapshot=safety_snapshot,
            queued_at=now,
        )
        # The kill-switch token is an opaque poll key, not a credential.
        kill_switch_token = secrets.token_urlsafe(32)
        execution.execution_specification = build_execution_specification(
            execution_id=execution.id,
            template=template,
            asset=asset,
            authorization=authorization,
            engagement=engagement,
            scope_snapshot=scope_snapshot,
            safety_snapshot=safety_snapshot,
            testing_window_start=engagement.starts_at,
            testing_window_end=engagement.ends_at,
            kill_switch_token=kill_switch_token,
        )

        try:
            await self._executions.add(execution)
        except IntegrityError as exc:
            # Backstop for the partial unique index if two requests with the
            # same key race past the pre-check.
            if unique_violation_constraint(exc) == _IDEMPOTENCY_CONSTRAINT:
                raise IdempotencyConflict(
                    "idempotency key already used for another request"
                ) from exc
            raise

        audit.record_execution_event(
            action="queue",
            organization_id=tenant.organization_id,
            execution_id=execution.id,
            actor=execution.requested_by,
            decision="queued",
        )
        # Mint the per-execution worker credential now — after the row and
        # snapshots exist, before dispatch publishes. Issuance persists into the
        # same transaction, so a later dispatch failure rolls the credential row
        # back with the execution (no orphaned grant). The raw token lives only
        # inside the returned handoff, which is handed to the dispatch seam as
        # side-channel data and never enters the broker payload/envelope, a log,
        # an audit event, or the API response.
        handoff = await self._issue_worker_credential(execution, engagement)
        # Dispatch only a newly created execution, inside this transaction. The
        # idempotent early-return above never reaches here, so a repeat request
        # returns the existing row without dispatching again.
        await self.dispatch_queued(execution, handoff)
        return execution

    async def _issue_worker_credential(
        self, execution: ValidationExecution, engagement: Any
    ) -> WorkerCredentialHandoff:
        """Issue the per-execution worker credential; fail closed on rejection.

        Grants both worker hook actions (``worker_started`` /
        ``worker_finished``) and expires at the sooner of the default TTL and
        the engagement testing-window end — never beyond the issuer's hard cap.
        On any non-``issued`` outcome the execution is *not* dispatched: a
        :class:`WorkerCredentialIssuanceFailed` is raised so the create
        transaction rolls back. The rejection's safe category is recorded in
        the audit trail; the raw token is never logged, audited, or surfaced.
        """
        now = self._clock.now()
        # Bound the credential to the testing window and the default TTL. The
        # engagement window end is exclusive and already validated to be in the
        # future during eligibility, so this is always a real future instant.
        expires_at = min(now + _WORKER_CREDENTIAL_TTL, engagement.ends_at)

        result = await self._credential_issuer.issue(
            execution_id=str(execution.id),
            organization_id=str(execution.organization_id),
            allowed_actions=_WORKER_CREDENTIAL_ACTIONS,
            expires_at=expires_at,
        )
        if (
            result.outcome is not WorkerCredentialIssueOutcome.issued
            or result.issued is None
        ):
            # ``result.failure`` is a short, non-sensitive category (e.g.
            # "execution_not_issuable") — safe for the audit trail, never the
            # raw token. The API surfaces only a generic typed error.
            audit.record_execution_event(
                action="worker_credential_issue",
                organization_id=execution.organization_id,
                execution_id=execution.id,
                actor=None,
                decision="rejected",
                detail=result.failure,
            )
            raise WorkerCredentialIssuanceFailed("worker credential issuance failed")

        issued = result.issued
        audit.record_execution_event(
            action="worker_credential_issue",
            organization_id=execution.organization_id,
            execution_id=execution.id,
            actor=None,
            decision="issued",
            # credential_id is an opaque server identifier — safe to audit.
            detail=issued.grant.credential_id,
        )
        return WorkerCredentialHandoff(
            execution_id=str(execution.id),
            credential_id=issued.grant.credential_id,
            raw_token=issued.raw_token,
            expires_at=issued.grant.expires_at,
        )

    async def _revoke_worker_credentials(
        self, execution_id: UUID, organization_id: UUID, *, reason: str
    ) -> None:
        """Revoke every active worker credential for a terminated execution.

        Called inside the same transaction as the terminal transition so the
        credential row(s) close atomically with the execution: a redelivered
        broker message cannot resurrect a credential for a run that is already
        ``succeeded`` / ``failed`` / ``cancelled`` / ``blocked`` (see
        docs/validation-worker-credentials-design.md → Expiry and revocation).

        Idempotent: a credential already carrying ``revoked_at`` is skipped, so
        a duplicate terminal hook does not move the timestamp forward and emits
        no second audit event (nothing was closed). The revocation writes only
        the wall-clock timestamp — no token, digest, or payload is read or
        logged.
        """
        revoked = await self._credentials.revoke_for_execution(
            execution_id,
            organization_id,
            revoked_at=self._clock.now(),
        )
        # Record the revocation as an audit fact only when it closed a live
        # credential; a no-op on an already-revoked/expired set is unremarkable
        # and would only add noise to the trail on duplicate terminal hooks.
        if revoked:
            audit.record_execution_event(
                action="worker_credential_revoke",
                organization_id=organization_id,
                execution_id=execution_id,
                actor=None,
                decision="revoked",
                detail=reason,
            )

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_for_tenant(
        self, execution_id: UUID, tenant: TenantContext
    ) -> ValidationExecution:
        execution = await self._executions.get_in_org(
            execution_id, tenant.organization_id
        )
        if execution is None:
            raise ValidationExecutionNotFound(_NOT_FOUND)
        return execution

    async def list_for_project(
        self, project_id: UUID, tenant: TenantContext
    ) -> Sequence[ValidationExecution]:
        return await self._executions.list_for_project(
            project_id, tenant.organization_id
        )

    # ------------------------------------------------------------------
    # Cancel
    # ------------------------------------------------------------------

    async def cancel(
        self, execution_id: UUID, tenant: TenantContext
    ) -> ValidationExecution:
        execution = await self._executions.get_in_org_for_update(
            execution_id, tenant.organization_id
        )
        if execution is None:
            raise ValidationExecutionNotFound(_NOT_FOUND)

        if execution.status in _TERMINAL_STATUSES:
            raise ExecutionImmutableError(
                f"execution in status {execution.status.value} cannot be cancelled"
            )
        if execution.status not in _CANCELLABLE_STATUSES:
            raise InvalidExecutionStateTransition(
                f"execution in status {execution.status.value} cannot be cancelled"
            )

        now = self._clock.now()
        current = execution.status
        success = await self._executions.conditional_transition(
            execution_id,
            tenant.organization_id,
            expected_status=current,
            new_status=ExecutionStatus.cancelled,
            cancelled_at=now,
        )
        if not success:
            raise InvalidExecutionStateTransition(
                "execution was modified concurrently; cannot cancel"
            )
        await self._executions.persist(execution)
        # Cancellation is terminal: close the per-execution worker credential so
        # a still-running or redelivered worker cannot keep driving hooks for a
        # run the operator stopped.
        await self._revoke_worker_credentials(
            execution.id, tenant.organization_id, reason="cancelled"
        )
        audit.record_execution_event(
            action="cancel",
            organization_id=tenant.organization_id,
            execution_id=execution.id,
            actor=None,
            decision="cancelled",
        )
        return execution

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    async def dispatch_queued(
        self, execution: ValidationExecution, handoff: WorkerCredentialHandoff
    ) -> None:
        """Hand the frozen worker payload to the dispatch seam.

        Called once for a newly queued execution, within the create transaction.
        Builds an immutable :class:`WorkerDispatchPayload` from the persisted
        snapshots and forwards only that — never the ORM row, tenant identity, or
        a raw dict. The per-execution credential ``handoff`` is passed as an
        explicit *internal* side-channel argument: a dispatcher that provisions
        the worker out of band may read the raw token from it, but the broker
        publisher ignores it and publishes only the credential-free envelope.
        The dispatcher forwards to an isolated worker and never runs scanner
        logic in this process. If a fail-closed dispatcher raises, the request
        transaction rolls back: nothing is queued (and no credential row
        survives) without a worker pipeline to run it — the safe default.
        """
        payload = WorkerDispatchPayload(
            execution_id=str(execution.id),
            template_id=execution.template_id,
            execution_specification=execution.execution_specification,
            scope_snapshot=execution.scope_snapshot,
            safety_snapshot=execution.safety_snapshot,
        )
        await self._dispatcher.dispatch(payload, handoff=handoff)

    # ------------------------------------------------------------------
    # Worker transition hooks
    # ------------------------------------------------------------------

    async def worker_started(
        self, execution_id: UUID, worker: WorkerContext
    ) -> ValidationExecution:
        """Mark an execution as ``executing`` and report a transition outcome.

        Idempotent against broker redelivery: a second ``worker-started`` for an
        execution already in ``executing`` returns the current row unchanged —
        ``started_at`` is preserved and no audit event is duplicated. Terminal
        rows (``succeeded`` / ``failed`` / ``cancelled`` / ``blocked``) reject
        with :class:`InvalidExecutionStateTransition` so a late redelivery
        cannot revive a closed execution. The row is locked
        (``SELECT … FOR UPDATE``) so concurrent duplicate hooks serialize.
        """
        # Machine-authenticated hook: the worker is identified by its credential
        # and the row by its unforgeable execution id, so the fetch is by id
        # alone and the organization is derived from the locked row — never from
        # the caller. Cross-tenant mutation is impossible because the id selects
        # exactly one tenant's row.
        execution = await self._executions.get_for_update(execution_id)
        if execution is None:
            raise ValidationExecutionNotFound(_NOT_FOUND)
        organization_id = execution.organization_id

        # Idempotent path: a redelivered worker-started for an already-executing
        # row is a no-op success — no audit, no started_at reset, no duplicate
        # mutation. This is the safety net for broker at-least-once delivery
        # (see docs/validation-dispatch-broker-design.md → idempotency).
        if execution.status is ExecutionStatus.executing:
            return execution

        # A worker may start from queued or dispatching.
        if execution.status not in (
            ExecutionStatus.queued,
            ExecutionStatus.dispatching,
        ):
            raise InvalidExecutionStateTransition(
                f"execution in status {execution.status.value} cannot start"
            )

        now = self._clock.now()
        success = await self._executions.conditional_transition(
            execution_id,
            organization_id,
            expected_status=execution.status,
            new_status=ExecutionStatus.executing,
            started_at=now,
        )
        if not success:
            raise InvalidExecutionStateTransition(
                "execution was modified concurrently; cannot start"
            )
        await self._executions.persist(execution)
        audit.record_execution_event(
            action="worker_started",
            organization_id=organization_id,
            execution_id=execution.id,
            actor=worker.worker_reference,
            decision="executing",
        )
        return execution

    async def worker_finished(
        self,
        execution_id: UUID,
        worker: WorkerContext,
        payload: WorkerFinishedRequest,
    ) -> ValidationExecution:
        """Apply a worker-reported result and report a transition outcome.

        Idempotent against broker redelivery: a duplicate ``worker-finished``
        whose sanitized result *matches* the already-stored terminal result
        (status, outcome, summary, error code, and the step-result set) returns
        the existing row — no duplicate step rows are inserted and
        ``finished_at`` is preserved. A duplicate carrying a *different*
        semantic result rejects with :class:`InvalidExecutionStateTransition`
        so a stale or conflicting redelivery never overwrites a recorded
        verdict (and ``cancelled`` / ``blocked`` reject for the same reason —
        a terminal cancellation must not be revived). The row is locked
        (``SELECT … FOR UPDATE``) so concurrent duplicate hooks serialize
        through the same idempotent path.
        """
        # Machine-authenticated hook: fetch by id and derive the organization
        # from the locked row (see ``worker_started``).
        execution = await self._executions.get_for_update(execution_id)
        if execution is None:
            raise ValidationExecutionNotFound(_NOT_FOUND)
        organization_id = execution.organization_id

        result_summary = _sanitize_text(payload.result_summary, _MAX_RESULT_SUMMARY)
        error_code = _sanitize_text(payload.error_code, 100)
        error_message = _sanitize_text(payload.error_message, _MAX_ERROR_MESSAGE)
        new_status = (
            ExecutionStatus.succeeded if payload.succeeded else ExecutionStatus.failed
        )

        # Idempotent path: a redelivered worker-finished hits an already-terminal
        # row. If the sanitized result matches what is stored, return the row
        # unchanged; otherwise reject so a stale or conflicting redelivery never
        # overwrites a verdict. ``cancelled`` and ``blocked`` reject regardless
        # — a terminal cancellation must not be revived (see security boundary).
        if execution.status in _RESULT_TERMINAL_STATUSES:
            if _result_matches(
                execution,
                expected_status=new_status,
                outcome=payload.outcome,
                result_summary=result_summary,
                error_code=error_code,
                error_message=error_message,
                steps=payload.steps,
            ):
                return execution
            raise InvalidExecutionStateTransition(
                f"execution in status {execution.status.value} cannot finish"
            )
        if execution.status is not ExecutionStatus.executing:
            raise InvalidExecutionStateTransition(
                f"execution in status {execution.status.value} cannot finish"
            )

        now = self._clock.now()
        success = await self._executions.conditional_transition(
            execution_id,
            organization_id,
            expected_status=ExecutionStatus.executing,
            new_status=new_status,
            outcome=payload.outcome,
            result_summary=result_summary,
            error_code=error_code,
            error_message=error_message,
            finished_at=now,
        )
        if not success:
            raise InvalidExecutionStateTransition(
                "execution was modified concurrently; cannot finish"
            )

        # Persist sanitized step results.
        for step in payload.steps:
            execution.step_results.append(
                ValidationStepResult(
                    organization_id=organization_id,
                    execution_id=execution.id,
                    step_name=step.step_name.strip()[:200],
                    status=step.status,
                    evidence=_sanitize_evidence(step),
                    finished_at=now,
                )
            )
        await self._executions.persist(execution)
        # The run has reached a terminal result: revoke the worker credential so
        # a broker redelivery of this finish (or a lingering worker) cannot
        # re-authenticate against a closed execution. The worker's own call has
        # already been verified above, so closing the credential here does not
        # break the in-flight request.
        await self._revoke_worker_credentials(
            execution.id, organization_id, reason=new_status.value
        )
        audit.record_execution_event(
            action="worker_finished",
            organization_id=organization_id,
            execution_id=execution.id,
            actor=worker.worker_reference,
            decision=new_status.value,
            detail=payload.outcome.value,
        )
        return execution

    # ------------------------------------------------------------------
    # Kill-switch poll
    # ------------------------------------------------------------------

    async def worker_kill_switch_status(
        self, execution_id: UUID, presented_token: str | None
    ) -> bool:
        """Report whether a polling worker must abort this execution.

        Machine path authenticated on the opaque ``kill_switch_token`` the
        control plane froze into the execution specification (see
        ``scan-authorization.md``) — not the per-execution worker credential, so
        a poll never depends on the credential's lifecycle. The presented token
        is compared to the stored one in constant time; a missing header and a
        mismatch are indistinguishable, both raising
        :class:`WorkerKillSwitchAuthenticationFailed` (401). The token value is
        never logged or echoed.

        Aborts (returns ``True``) when the engagement kill switch is active or
        the execution has already reached a terminal state — either means an
        in-flight scan should stop promptly. The read takes no row lock so
        frequent polls never serialize behind a running transition.
        """
        execution = await self._executions.get_by_id(execution_id)
        if execution is None:
            # Indistinguishable from a bad token: never disclose existence.
            raise WorkerKillSwitchAuthenticationFailed("kill-switch authentication failed")

        stored_token = execution.execution_specification.get("kill_switch_token")
        if not _kill_switch_token_matches(stored_token, presented_token):
            raise WorkerKillSwitchAuthenticationFailed("kill-switch authentication failed")

        if execution.status in _TERMINAL_STATUSES:
            return True

        engagement = await self._engagements.get_in_org(
            execution.engagement_id, execution.organization_id
        )
        # A missing engagement (deleted mid-run) is treated as a stop signal:
        # the worker should not keep scanning against a vanished authorization.
        if engagement is None:
            return True
        return bool(engagement.kill_switch_active)

    # ------------------------------------------------------------------
    # Eligibility helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _ensure_idempotent_match(
        existing: ValidationExecution, payload: ValidationExecutionCreate
    ) -> None:
        material = {
            "project_id": existing.project_id,
            "asset_id": existing.asset_id,
            "authorization_id": existing.authorization_id,
            "engagement_id": existing.engagement_id,
            "engagement_scope_id": existing.engagement_scope_id,
            "template_id": existing.template_id,
        }
        requested = {
            "project_id": payload.project_id,
            "asset_id": payload.asset_id,
            "authorization_id": payload.authorization_id,
            "engagement_id": payload.engagement_id,
            "engagement_scope_id": payload.engagement_scope_id,
            "template_id": payload.template_id,
        }
        for field in _IDEMPOTENCY_MATERIAL_FIELDS:
            if material[field] != requested[field]:
                raise IdempotencyConflict(
                    "idempotency key already used for another request"
                )

    @staticmethod
    def _find_engagement_scope(
        scopes: Sequence[EngagementScope],
        engagement_scope_id: UUID,
        asset_id: UUID,
    ) -> EngagementScope:
        for scope in scopes:
            if scope.id == engagement_scope_id:
                if scope.asset_id != asset_id:
                    raise InvalidExecutionScope(
                        "engagement scope does not cover the requested asset"
                    )
                return scope
        raise InvalidExecutionScope(
            "engagement scope does not belong to the engagement"
        )

    @staticmethod
    def _resolve_authorization_scope(
        scopes: Sequence[AuthorizationScope],
        asset_id: UUID,
        engagement_scope: EngagementScope,
    ) -> AuthorizationScope | None:
        # Prefer the scope the engagement scope references; otherwise match by
        # asset. The asset-in-authorization check already ran in
        # _validate_authorization.
        if engagement_scope.authorization_scope_id is not None:
            for scope in scopes:
                if scope.id == engagement_scope.authorization_scope_id:
                    return scope
        for scope in scopes:
            if scope.asset_id == asset_id:
                return scope
        return None

    @staticmethod
    def _validate_asset(asset: Any) -> None:
        if asset.status is not AssetStatus.verified:
            raise InvalidExecutionScope(
                f"asset {asset.id} is not verified "
                f"(current status: {asset.status.value})"
            )

    def _validate_authorization(
        self, authorization: Any, asset_id: UUID, risk_tier: RiskTier, now: Any
    ) -> None:
        if authorization.status is not AuthorizationStatus.active:
            raise ExecutionEligibilityBlocked("linked authorization is not active")
        if now < authorization.valid_from or now >= authorization.valid_until:
            raise ExecutionEligibilityBlocked(
                "linked authorization is not within its valid time window"
            )
        if asset_id not in {s.asset_id for s in authorization.scopes}:
            raise InvalidExecutionScope("asset is not within the authorization scope")
        if not _risk_tier_lte(risk_tier, authorization.maximum_risk_tier):
            raise ExecutionEligibilityBlocked(
                f"template risk tier {risk_tier.value} exceeds authorization "
                f"maximum {authorization.maximum_risk_tier.value}"
            )

    def _validate_engagement(
        self, engagement: Any, asset_id: UUID, risk_tier: RiskTier, now: Any
    ) -> None:
        if engagement.status is not EngagementStatus.active:
            raise ExecutionEligibilityBlocked(
                f"engagement status {engagement.status.value} is not active"
            )
        if engagement.kill_switch_active:
            raise ExecutionEligibilityBlocked("engagement kill switch is active")
        if now < engagement.starts_at or now >= engagement.ends_at:
            raise ExecutionEligibilityBlocked(
                "engagement is not within its time window"
            )
        if asset_id not in {s.asset_id for s in engagement.scopes}:
            raise InvalidExecutionScope("asset is not within the engagement scope")
        if not _risk_tier_lte(risk_tier, engagement.max_risk_tier):
            raise ExecutionEligibilityBlocked(
                f"template risk tier {risk_tier.value} exceeds engagement "
                f"maximum {engagement.max_risk_tier.value}"
            )


# Terminal and cancellable status sets.
_TERMINAL_STATUSES: frozenset[ExecutionStatus] = frozenset(
    {
        ExecutionStatus.succeeded,
        ExecutionStatus.failed,
        ExecutionStatus.cancelled,
        ExecutionStatus.blocked,
    }
)

# Terminal statuses that are valid landing places for a worker-finished result.
# ``cancelled`` and ``blocked`` are deliberately excluded: a redelivered
# worker-finished must never revive a terminally-cancelled execution.
_RESULT_TERMINAL_STATUSES: frozenset[ExecutionStatus] = frozenset(
    {ExecutionStatus.succeeded, ExecutionStatus.failed}
)

# Cancellation is permitted up to and including the executing state; actual
# worker cancellation is deferred (the row records the requested terminal state).
_CANCELLABLE_STATUSES: frozenset[ExecutionStatus] = frozenset(
    {
        ExecutionStatus.queued,
        ExecutionStatus.dispatching,
        ExecutionStatus.executing,
    }
)


def _result_matches(
    execution: ValidationExecution,
    *,
    expected_status: ExecutionStatus,
    outcome: ExecutionOutcome,
    result_summary: str | None,
    error_code: str | None,
    error_message: str | None,
    steps: Sequence[WorkerStepResult],
) -> bool:
    """Return True when ``execution`` already records the same semantic result.

    Compares sanitized fields only — never raw payload bytes, evidence-with-
    secrets, or unsanitized strings — so the comparison cannot be skewed by
    payload-encoding noise. Step-result equality is the multiset of
    ``(step_name, status, sanitized_evidence)`` tuples: the worker reporting
    the same steps in a different order is still the same semantic result,
    while a different step set or a changed evidence value is not. This
    function is the entire idempotency fingerprint — no derived hash column
    is stored or required (see docs/validation-dispatch-broker-design.md).
    """
    if execution.status is not expected_status:
        return False
    if execution.outcome is not outcome:
        return False
    if execution.result_summary != result_summary:
        return False
    if execution.error_code != error_code:
        return False
    if execution.error_message != error_message:
        return False
    return _step_results_match(execution.step_results, steps)


def _step_results_match(
    stored: Sequence[ValidationStepResult],
    incoming: Sequence[WorkerStepResult],
) -> bool:
    """Compare two step-result sets as multisets of sanitized triples.

    Storage truncates ``step_name`` to 200 chars and sanitizes evidence at
    persist time; this applies the same truncation/sanitization to the
    incoming payload before comparing, so the two sides are normalised
    identically. Order is ignored.
    """
    if len(stored) != len(incoming):
        return False
    stored_signatures = sorted(
        (row.step_name, row.status, _evidence_signature(row.evidence)) for row in stored
    )
    incoming_signatures = sorted(
        (
            step.step_name.strip()[:200],
            step.status,
            _evidence_signature(_sanitize_evidence(step)),
        )
        for step in incoming
    )
    return stored_signatures == incoming_signatures


def _evidence_signature(evidence: dict[str, Any] | None) -> tuple[tuple[str, str], ...]:
    """Return a stable, hashable signature of a sanitized evidence mapping.

    The sanitizer already coerces every value to a bounded string, so the
    signature is a sorted tuple of (key, value) pairs. ``None`` evidence
    signs as the empty tuple.
    """
    if not evidence:
        return ()
    return tuple(sorted((str(k), str(v)) for k, v in evidence.items()))


def _sanitize_text(value: str | None, limit: int) -> str | None:
    """Trim and bound a free-text field reported by a worker."""
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    return cleaned[:limit]


def _sanitize_evidence(step: WorkerStepResult) -> dict[str, Any] | None:
    """Bound and stringify worker-reported evidence.

    Evidence from a worker is treated as untrusted: the key count is capped,
    values are coerced to bounded strings, and nothing is interpreted. This
    keeps unbounded or structured payloads out of the stored record.
    """
    if step.evidence is None:
        return None
    sanitized: dict[str, Any] = {}
    for index, (key, value) in enumerate(step.evidence.items()):
        if index >= _MAX_EVIDENCE_KEYS:
            break
        safe_key = str(key)[:200]
        sanitized[safe_key] = str(value)[:_MAX_EVIDENCE_VALUE_CHARS]
    return sanitized
