import asyncio
from datetime import datetime, timedelta, UTC
from uuid import UUID
from sqlalchemy import select, delete

from app.config import get_settings
from app.platform.database import create_engine, create_session_factory
from app.modules.organizations.models import Organization
from app.modules.organizations.enums import OrganizationStatus
from app.modules.projects.models import Project
from app.modules.projects.enums import ProjectStatus
from app.modules.assets.models import Asset
from app.modules.assets.enums import AssetType, AssetEnvironment, AssetCriticality, AssetStatus, VerificationMethod
from app.modules.authorizations.models import Authorization, AuthorizationScope
from app.modules.authorizations.enums import AuthorizationStatus, RiskTier
from app.modules.engagements.models import Engagement, EngagementScope
from app.modules.engagements.enums import EngagementStatus
from app.modules.validation_executions.models import ValidationExecution, ValidationStepResult
from app.modules.validation_executions.enums import ExecutionStatus, ExecutionOutcome, StepStatus


async def run_seed():
    settings = get_settings()
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)

    async with session_factory() as session:
        # Clear existing data to ensure clean state
        print("Clearing existing data...")
        await session.execute(delete(ValidationStepResult))
        await session.execute(delete(ValidationExecution))
        await session.execute(delete(EngagementScope))
        await session.execute(delete(Engagement))
        await session.execute(delete(AuthorizationScope))
        await session.execute(delete(Authorization))
        await session.execute(delete(Asset))
        await session.execute(delete(Project))
        await session.execute(delete(Organization))
        await session.commit()

        print("Seeding organizations...")
        org1 = Organization(
            id=UUID("00000000-0000-0000-0000-000000000001"),
            name="Nasari Security Lab",
            slug="nsl",
            status=OrganizationStatus.active
        )
        org2 = Organization(
            id=UUID("00000000-0000-0000-0000-000000000002"),
            name="Core Banking Validation",
            slug="cbv",
            status=OrganizationStatus.active
        )
        org3 = Organization(
            id=UUID("00000000-0000-0000-0000-000000000003"),
            name="KDKMP Digital Platform",
            slug="kdkmp",
            status=OrganizationStatus.active
        )
        session.add_all([org1, org2, org3])
        await session.flush()

        print("Seeding projects...")
        p1 = Project(
            id=UUID("00000000-0000-0000-0000-000000000011"),
            organization_id=org1.id,
            name="Mobile API Security",
            slug="mob-api",
            description="Mobile API Security Assessment",
            status=ProjectStatus.active
        )
        p2 = Project(
            id=UUID("00000000-0000-0000-0000-000000000012"),
            organization_id=org2.id,
            name="Core Banking Gateway",
            slug="cb-gw",
            description="Core Banking Gateway Assessment",
            status=ProjectStatus.active
        )
        p3 = Project(
            id=UUID("00000000-0000-0000-0000-000000000013"),
            organization_id=org3.id,
            name="Admin Console Validation",
            slug="adm-con",
            description="Admin Console Validation Assessment",
            status=ProjectStatus.active
        )
        session.add_all([p1, p2, p3])
        await session.flush()

        print("Seeding assets...")
        now = datetime.now(UTC)
        a1 = Asset(
            id=UUID("00000000-0000-0000-0000-000000000021"),
            organization_id=org1.id,
            project_id=p1.id,
            name="Nasari Public API",
            asset_type=AssetType.api,
            environment=AssetEnvironment.production,
            target="api.nasari.local",
            criticality=AssetCriticality.high,
            status=AssetStatus.verified,
            ownership_verified_at=now - timedelta(days=30),
            verification_method=VerificationMethod.dns_txt_record
        )
        a2 = Asset(
            id=UUID("00000000-0000-0000-0000-000000000022"),
            organization_id=org1.id,
            project_id=p1.id,
            name="Staging Mobile API",
            asset_type=AssetType.api,
            environment=AssetEnvironment.staging,
            target="staging-mobile-api.securescope.test",
            criticality=AssetCriticality.medium,
            status=AssetStatus.verified,
            ownership_verified_at=now - timedelta(days=20),
            verification_method=VerificationMethod.dns_txt_record
        )
        a3 = Asset(
            id=UUID("00000000-0000-0000-0000-000000000023"),
            organization_id=org3.id,
            project_id=p3.id,
            name="Admin Console",
            asset_type=AssetType.web_application,
            environment=AssetEnvironment.production,
            target="admin-console.securescope.test",
            criticality=AssetCriticality.critical,
            status=AssetStatus.verified,
            ownership_verified_at=now - timedelta(days=10),
            verification_method=VerificationMethod.dns_txt_record
        )
        a4 = Asset(
            id=UUID("00000000-0000-0000-0000-000000000024"),
            organization_id=org2.id,
            project_id=p2.id,
            name="Core Banking Gateway",
            asset_type=AssetType.api,
            environment=AssetEnvironment.production,
            target="core-gw.bank-mirror.local",
            criticality=AssetCriticality.critical,
            status=AssetStatus.verified,
            ownership_verified_at=now - timedelta(days=5),
            verification_method=VerificationMethod.dns_txt_record
        )
        a5 = Asset(
            id=UUID("00000000-0000-0000-0000-000000000025"),
            organization_id=org1.id,
            project_id=p1.id,
            name="Edge Auth Service",
            asset_type=AssetType.api,
            environment=AssetEnvironment.staging,
            target="edge-auth.nasari-sandbox.test",
            criticality=AssetCriticality.high,
            status=AssetStatus.pending_verification,
            verification_method=VerificationMethod.dns_txt_record,
            verification_requested_at=now - timedelta(hours=12)
        )
        a6 = Asset(
            id=UUID("00000000-0000-0000-0000-000000000026"),
            organization_id=org3.id,
            project_id=p3.id,
            name="Reporting Endpoint",
            asset_type=AssetType.api,
            environment=AssetEnvironment.development,
            target="reports.kdkmp-sandbox.test",
            criticality=AssetCriticality.medium,
            status=AssetStatus.draft
        )
        session.add_all([a1, a2, a3, a4, a5, a6])
        await session.flush()

        print("Seeding authorizations...")
        auth1 = Authorization(
            id=UUID("00000000-0000-0000-0000-000000000031"),
            organization_id=org1.id,
            project_id=p1.id,
            reference_number="AUTH-NSL-001",
            title="Mobile API Security Scope",
            status=AuthorizationStatus.active,
            valid_from=now - timedelta(days=5),
            valid_until=now + timedelta(days=15),
            timezone="Asia/Jakarta",
            maximum_risk_tier=RiskTier.tier_2_controlled,
            emergency_contact_name="K. Andrade",
            emergency_contact_phone="+62-811-1111-2222",
            authorization_document_name="NSL-Auth-Pkg-2026-07.pdf",
            authorization_document_sha256="9f2a00000000000000000000000000000000000000000000000000000000b71c"
        )
        auth2 = Authorization(
            id=UUID("00000000-0000-0000-0000-000000000032"),
            organization_id=org2.id,
            project_id=p2.id,
            reference_number="AUTH-CBV-001",
            title="Core Banking Authorization letter",
            status=AuthorizationStatus.active,
            valid_from=now - timedelta(days=1),
            valid_until=now + timedelta(days=3),
            timezone="Asia/Jakarta",
            maximum_risk_tier=RiskTier.tier_1_safe,
            emergency_contact_name="R. Varga",
            emergency_contact_phone="+62-811-3333-4444",
            authorization_document_name="CBV-Auth-Pkg-2026-07.pdf",
            authorization_document_sha256="3c8100000000000000000000000000000000000000000000000000000000f29a"
        )
        auth3 = Authorization(
            id=UUID("00000000-0000-0000-0000-000000000033"),
            organization_id=org3.id,
            project_id=p3.id,
            reference_number="AUTH-KDKMP-001",
            title="KDKMP Audit Validation",
            status=AuthorizationStatus.active,
            valid_from=now - timedelta(days=10),
            valid_until=now + timedelta(days=20),
            timezone="Asia/Jakarta",
            maximum_risk_tier=RiskTier.tier_2_controlled,
            emergency_contact_name="T. Olsen",
            emergency_contact_phone="+62-811-5555-6666",
            authorization_document_name="KDKMP-Auth-Pkg-2026-07.pdf",
            authorization_document_sha256="5d1200000000000000000000000000000000000000000000000000000000aa90"
        )
        auth4 = Authorization(
            id=UUID("00000000-0000-0000-0000-000000000034"),
            organization_id=org1.id,
            project_id=p1.id,
            reference_number="AUTH-NSL-002",
            title="Staging Sandbox Verification",
            status=AuthorizationStatus.draft,
            valid_from=now + timedelta(days=5),
            valid_until=now + timedelta(days=15),
            timezone="Asia/Jakarta",
            maximum_risk_tier=RiskTier.tier_1_safe,
            emergency_contact_name="K. Andrade",
            emergency_contact_phone="+62-811-1111-2222",
            authorization_document_name="NSL-Auth-Pkg-2026-07-002.pdf",
            authorization_document_sha256="1f8c0000000000000000000000000000000000000000000000000000000077bd"
        )
        session.add_all([auth1, auth2, auth3, auth4])
        await session.flush()

        print("Seeding authorization scopes...")
        sc1 = AuthorizationScope(
            id=UUID("00000000-0000-0000-0000-000000000081"),
            organization_id=org1.id,
            authorization_id=auth1.id,
            asset_id=a1.id,
            allowed_ports=[443],
            allowed_paths="/api/v1/*,/api/v2/*,/healthz",
            excluded_paths="/api/v1/payments/*,/api/v1/admin/*",
            maximum_requests_per_minute=60,
            maximum_concurrency=5
        )
        sc2 = AuthorizationScope(
            id=UUID("00000000-0000-0000-0000-000000000082"),
            organization_id=org1.id,
            authorization_id=auth1.id,
            asset_id=a2.id,
            allowed_ports=[443],
            allowed_paths="/api/v1/*,/api/v2/*,/healthz",
            excluded_paths="/api/v1/payments/*,/api/v1/admin/*",
            maximum_requests_per_minute=60,
            maximum_concurrency=5
        )
        sc3 = AuthorizationScope(
            id=UUID("00000000-0000-0000-0000-000000000083"),
            organization_id=org2.id,
            authorization_id=auth2.id,
            asset_id=a4.id,
            allowed_ports=[443],
            allowed_paths="/gateway/v1/*,/gateway/v1/health",
            excluded_paths="/gateway/v1/transfer/*,/gateway/v1/auth/*",
            maximum_requests_per_minute=60,
            maximum_concurrency=5
        )
        sc4 = AuthorizationScope(
            id=UUID("00000000-0000-0000-0000-000000000084"),
            organization_id=org3.id,
            authorization_id=auth3.id,
            asset_id=a3.id,
            allowed_ports=[443],
            allowed_paths="/admin/*,/admin/healthz",
            excluded_paths="/admin/users/delete/*,/admin/billing/*",
            maximum_requests_per_minute=60,
            maximum_concurrency=5
        )
        session.add_all([sc1, sc2, sc3, sc4])
        await session.flush()

        print("Seeding engagements...")
        eng1 = Engagement(
            id=UUID("00000000-0000-0000-0000-000000000041"),
            organization_id=org1.id,
            project_id=p1.id,
            authorization_id=auth1.id,
            name="Mobile API Header Hardening Sweep",
            description="Testing TLS and headers on production & staging",
            status=EngagementStatus.active,
            starts_at=now - timedelta(hours=2),
            ends_at=now + timedelta(hours=6),
            timezone="Asia/Jakarta",
            max_risk_tier=RiskTier.tier_2_controlled,
            default_rate_limit_per_minute=60,
            default_concurrency_limit=5,
            emergency_contact_name="K. Andrade",
            emergency_contact_email="k.andrade@nasari.sec",
            emergency_contact_phone="+62-811-1111-2222",
            kill_switch_active=False
        )
        eng2 = Engagement(
            id=UUID("00000000-0000-0000-0000-000000000042"),
            organization_id=org2.id,
            project_id=p2.id,
            authorization_id=auth2.id,
            name="Core Gateway TLS Check",
            description="Verify core banking TLS parameters",
            status=EngagementStatus.active,
            starts_at=now - timedelta(hours=1),
            ends_at=now + timedelta(hours=3),
            timezone="Asia/Jakarta",
            max_risk_tier=RiskTier.tier_1_safe,
            default_rate_limit_per_minute=30,
            default_concurrency_limit=3,
            emergency_contact_name="R. Varga",
            emergency_contact_email="r.varga@cbv.sec",
            emergency_contact_phone="+62-811-3333-4444",
            kill_switch_active=False
        )
        eng3 = Engagement(
            id=UUID("00000000-0000-0000-0000-000000000043"),
            organization_id=org3.id,
            project_id=p3.id,
            authorization_id=auth3.id,
            name="Admin Portal Scope Assessment",
            description="Check exposed endpoints and configurations",
            status=EngagementStatus.scheduled,
            starts_at=now + timedelta(days=1),
            ends_at=now + timedelta(days=3),
            timezone="Asia/Jakarta",
            max_risk_tier=RiskTier.tier_2_controlled,
            default_rate_limit_per_minute=60,
            default_concurrency_limit=5,
            emergency_contact_name="T. Olsen",
            emergency_contact_email="t.olsen@kdkmp.sec",
            emergency_contact_phone="+62-811-5555-6666",
            kill_switch_active=False
        )
        session.add_all([eng1, eng2, eng3])
        await session.flush()

        print("Seeding engagement scopes...")
        es1 = EngagementScope(
            id=UUID("00000000-0000-0000-0000-000000000091"),
            organization_id=org1.id,
            engagement_id=eng1.id,
            asset_id=a1.id,
            authorization_scope_id=sc1.id,
            allowed_ports=[443],
            allowed_paths=["/api/v1/*", "/api/v2/*"],
            excluded_paths=[],
            rate_limit_per_minute=60,
            concurrency_limit=5
        )
        es2 = EngagementScope(
            id=UUID("00000000-0000-0000-0000-000000000092"),
            organization_id=org1.id,
            engagement_id=eng1.id,
            asset_id=a2.id,
            authorization_scope_id=sc2.id,
            allowed_ports=[443],
            allowed_paths=["/api/v1/*", "/api/v2/*"],
            excluded_paths=[],
            rate_limit_per_minute=60,
            concurrency_limit=5
        )
        es3 = EngagementScope(
            id=UUID("00000000-0000-0000-0000-000000000093"),
            organization_id=org2.id,
            engagement_id=eng2.id,
            asset_id=a4.id,
            authorization_scope_id=sc3.id,
            allowed_ports=[443],
            allowed_paths=["/gateway/v1/*"],
            excluded_paths=[],
            rate_limit_per_minute=30,
            concurrency_limit=3
        )
        session.add_all([es1, es2, es3])
        await session.flush()

        print("Seeding validation executions...")
        exec1 = ValidationExecution(
            id=UUID("00000000-0000-0000-0000-000000000051"),
            organization_id=org1.id,
            project_id=p1.id,
            asset_id=a1.id,
            authorization_id=auth1.id,
            authorization_scope_id=sc1.id,
            engagement_id=eng1.id,
            engagement_scope_id=es1.id,
            template_id="HTTP_SECURITY_HEADER_VALIDATION",
            status=ExecutionStatus.succeeded,
            outcome=ExecutionOutcome.validated,
            risk_tier=RiskTier.tier_1_safe,
            execution_specification={"target": "api.nasari.local", "port": 443, "path": "/healthz", "method": "GET"},
            scope_snapshot={
                "allowedPaths": ["/api/v1/*", "/api/v2/*", "/healthz"],
                "excludedPaths": ["/api/v1/payments/*", "/api/v1/admin/*"],
                "allowedPorts": [443],
                "maxRiskTier": "tier_2_controlled",
                "scopedAssets": [str(a1.id), str(a2.id)]
            },
            safety_snapshot={
                "assetVerified": True,
                "authorizationActive": True,
                "engagementActive": True,
                "scopeMatch": True,
                "windowValid": True,
                "killSwitchInactive": True,
                "riskTierAllowed": True,
                "credentialIssued": True,
                "dispatchBackendAvailable": True,
                "workerAuthModeReady": True
            },
            queued_at=now - timedelta(minutes=15),
            started_at=now - timedelta(minutes=14),
            finished_at=now - timedelta(minutes=13)
        )
        exec2 = ValidationExecution(
            id=UUID("00000000-0000-0000-0000-000000000052"),
            organization_id=org2.id,
            project_id=p2.id,
            asset_id=a4.id,
            authorization_id=auth2.id,
            authorization_scope_id=sc3.id,
            engagement_id=eng2.id,
            engagement_scope_id=es3.id,
            template_id="TLS_VERSION_VALIDATION",
            status=ExecutionStatus.executing,
            outcome=None,
            risk_tier=RiskTier.tier_1_safe,
            execution_specification={"target": "core-gw.bank-mirror.local", "port": 443, "path": "/gateway/v1/health", "method": "GET"},
            scope_snapshot={
                "allowedPaths": ["/gateway/v1/*", "/gateway/v1/health"],
                "excludedPaths": ["/gateway/v1/transfer/*", "/gateway/v1/auth/*"],
                "allowedPorts": [443],
                "maxRiskTier": "tier_1_safe",
                "scopedAssets": [str(a4.id)]
            },
            safety_snapshot={
                "assetVerified": True,
                "authorizationActive": True,
                "engagementActive": True,
                "scopeMatch": True,
                "windowValid": True,
                "killSwitchInactive": True,
                "riskTierAllowed": True,
                "credentialIssued": True,
                "dispatchBackendAvailable": True,
                "workerAuthModeReady": True
            },
            queued_at=now - timedelta(minutes=5),
            started_at=now - timedelta(minutes=4)
        )
        exec3 = ValidationExecution(
            id=UUID("00000000-0000-0000-0000-000000000053"),
            organization_id=org1.id,
            project_id=p1.id,
            asset_id=a2.id,
            authorization_id=auth1.id,
            authorization_scope_id=sc2.id,
            engagement_id=eng1.id,
            engagement_scope_id=es2.id,
            template_id="HTTP_SECURITY_HEADER_VALIDATION",
            status=ExecutionStatus.queued,
            outcome=None,
            risk_tier=RiskTier.tier_1_safe,
            execution_specification={"target": "staging-mobile-api.securescope.test", "port": 443, "path": "/healthz", "method": "GET"},
            scope_snapshot={
                "allowedPaths": ["/api/v1/*", "/api/v2/*", "/healthz"],
                "excludedPaths": ["/api/v1/payments/*", "/api/v1/admin/*"],
                "allowedPorts": [443],
                "maxRiskTier": "tier_2_controlled",
                "scopedAssets": [str(a1.id), str(a2.id)]
            },
            safety_snapshot={
                "assetVerified": True,
                "authorizationActive": True,
                "engagementActive": True,
                "scopeMatch": True,
                "windowValid": True,
                "killSwitchInactive": True,
                "riskTierAllowed": True,
                "credentialIssued": True,
                "dispatchBackendAvailable": True,
                "workerAuthModeReady": True
            },
            queued_at=now - timedelta(seconds=30)
        )
        session.add_all([exec1, exec2, exec3])
        await session.flush()

        print("Seeding steps for succeeded execution...")
        step1 = ValidationStepResult(
            id=UUID("00000000-0000-0000-0000-000000000061"),
            organization_id=org1.id,
            execution_id=exec1.id,
            step_name="TLS handshake and certificate check",
            status=StepStatus.passed,
            evidence={"cipher": "TLS_AES_256_GCM_SHA384", "version": "TLSv1.3"},
            started_at=now - timedelta(minutes=14),
            finished_at=now - timedelta(minutes=13, seconds=50)
        )
        step2 = ValidationStepResult(
            id=UUID("00000000-0000-0000-0000-000000000062"),
            organization_id=org1.id,
            execution_id=exec1.id,
            step_name="HTTP Strict-Transport-Security verification",
            status=StepStatus.passed,
            evidence={"header": "Strict-Transport-Security: max-age=63072000; includeSubDomains; preload"},
            started_at=now - timedelta(minutes=13, seconds=50),
            finished_at=now - timedelta(minutes=13, seconds=40)
        )
        step3 = ValidationStepResult(
            id=UUID("00000000-0000-0000-0000-000000000063"),
            organization_id=org1.id,
            execution_id=exec1.id,
            step_name="X-Content-Type-Options inspection",
            status=StepStatus.passed,
            evidence={"header": "X-Content-Type-Options: nosniff"},
            started_at=now - timedelta(minutes=13, seconds=40),
            finished_at=now - timedelta(minutes=13, seconds=30)
        )
        session.add_all([step1, step2, step3])
        await session.commit()
        print("Database seeding completed successfully!")


if __name__ == "__main__":
    asyncio.run(run_seed())
