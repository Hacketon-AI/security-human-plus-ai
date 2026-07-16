"""Execution Evidence Provider Boundary.

Isolates AI Proof-of-Risk from the core execution engine. Prevents accidental
imports of worker runtimes, celery, or transport logic.
"""

from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID


@dataclass
class ExecutionEvidenceBundle:
    """A safe, extracted bundle of evidence from an execution run."""

    execution_id: UUID
    organization_id: UUID
    project_id: UUID
    asset_id: UUID
    asset_target_safe: bool
    asset_verified: bool
    authorization_snapshot_summary: str
    engagement_snapshot_summary: str
    scope_snapshot_summary: str
    safety_snapshot_summary: str
    validation_result_summary: str
    sanitized_step_results: list[dict[str, Any]] | None = None
    raw_step_results_to_be_redacted: list[dict[str, Any]] | None = None
    original_target_hash: str | None = None
    original_target_hostname: str | None = None
    tenant_access_confirmed: bool = False


class ExecutionEvidenceProvider(Protocol):
    """Protocol for fetching evidence safely."""

    def get_execution_evidence(
        self, execution_id: UUID, context: dict[str, Any] | None = None
    ) -> ExecutionEvidenceBundle: ...


class FakeExecutionEvidenceProvider:
    """A fake provider for tests and safe sandbox execution."""

    def __init__(self) -> None:
        pass

    def get_execution_evidence(
        self, execution_id: UUID, context: dict[str, Any] | None = None
    ) -> ExecutionEvidenceBundle:
        from uuid import uuid4

        organization_id = uuid4()
        if context is not None and "organization_id" in context:
            organization_id = UUID(str(context["organization_id"]))

        # Hardcoded fake data remains tenant-bound to the verified route context.
        return ExecutionEvidenceBundle(
            execution_id=execution_id,
            organization_id=organization_id,
            project_id=uuid4(),
            asset_id=uuid4(),
            asset_target_safe=True,
            asset_verified=True,
            authorization_snapshot_summary="Authorized",
            engagement_snapshot_summary="Active",
            scope_snapshot_summary="In Scope",
            safety_snapshot_summary="Safe",
            validation_result_summary="Completed with findings",
            raw_step_results_to_be_redacted=[
                {
                    "step_id": "step-1",
                    "status": "passed",
                    "finding_refs": ["missing_csp"],
                    "evidence": {
                        "headers": {
                            "Content-Type": "text/html",
                            "Authorization": "Bearer secret_token",
                        }
                    },
                }
            ],
            original_target_hostname="example.com",
            tenant_access_confirmed=True,
        )
