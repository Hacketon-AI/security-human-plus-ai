"""Demo seed data — realistic Indonesian fintech & enterprise security scenarios.

Three client organizations, each with real-looking projects, assets, active
authorizations, engagements running right now, and a mix of completed, in-progress,
and queued validation executions. Designed to look like a live platform on demo day.

Run: python -m app.seed
"""

import asyncio
from datetime import datetime, timedelta, UTC
from uuid import UUID
from sqlalchemy import delete

from app.config import get_settings
from app.platform.database import create_engine, create_session_factory
from app.modules.organizations.models import Organization
from app.modules.organizations.enums import OrganizationStatus
from app.modules.projects.models import Project
from app.modules.projects.enums import ProjectStatus
from app.modules.assets.models import Asset
from app.modules.assets.enums import (
    AssetType,
    AssetEnvironment,
    AssetCriticality,
    AssetStatus,
    VerificationMethod,
)
from app.modules.authorizations.models import Authorization, AuthorizationScope
from app.modules.authorizations.enums import AuthorizationStatus, RiskTier
from app.modules.engagements.models import Engagement, EngagementScope
from app.modules.engagements.enums import EngagementStatus
from app.modules.validation_executions.models import (
    ValidationExecution,
    ValidationStepResult,
)
from app.modules.validation_executions.enums import (
    ExecutionStatus,
    ExecutionOutcome,
    StepStatus,
)


async def run_seed():
    settings = get_settings()
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)

    async with session_factory() as session:
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

        now = datetime.now(UTC)

        # ------------------------------------------------------------------ #
        # ORGANIZATIONS
        # Three real-sounding Indonesian enterprise clients.
        # org1  → BRI Ventures Digital (fintech / OJK-regulated)
        # org2  → Telkom Sigma Cloud (infrastructure / MSP)
        # org3  → Mandiri Sekuritas (capital markets / broker-dealer)
        # ------------------------------------------------------------------ #
        print("Seeding organizations...")

        org1 = Organization(
            id=UUID("00000000-0000-0000-0000-000000000001"),
            name="BRI Ventures Digital",
            slug="bri-ventures",
            status=OrganizationStatus.active,
        )
        org2 = Organization(
            id=UUID("00000000-0000-0000-0000-000000000002"),
            name="Telkom Sigma Cloud",
            slug="telkom-sigma",
            status=OrganizationStatus.active,
        )
        org3 = Organization(
            id=UUID("00000000-0000-0000-0000-000000000003"),
            name="Mandiri Sekuritas",
            slug="mandiri-sek",
            status=OrganizationStatus.active,
        )
        session.add_all([org1, org2, org3])
        await session.flush()


        # ------------------------------------------------------------------ #
        # PROJECTS
        # ------------------------------------------------------------------ #
        print("Seeding projects...")

        # BRI Ventures — two projects: consumer lending API and OJK compliance
        p1 = Project(
            id=UUID("00000000-0000-0000-0000-000000000011"),
            organization_id=org1.id,
            name="Pinjamanku Lending API",
            slug="pinjamanku-api",
            description=(
                "Security validation for the consumer micro-lending REST API "
                "exposed to 3rd-party fintech partners under OJK POJK 77 scope."
            ),
            status=ProjectStatus.active,
        )
        p2 = Project(
            id=UUID("00000000-0000-0000-0000-000000000012"),
            organization_id=org1.id,
            name="OJK Compliance Portal",
            slug="ojk-portal",
            description=(
                "Internal reporting portal submitted to OJK sandbox. "
                "Annual penetration test mandatory under regulatory schedule."
            ),
            status=ProjectStatus.active,
        )

        # Telkom Sigma — cloud management & SIEM dashboard
        p3 = Project(
            id=UUID("00000000-0000-0000-0000-000000000013"),
            organization_id=org2.id,
            name="SigmaCloud Management Console",
            slug="sigma-console",
            description=(
                "Multi-tenant cloud management console. Customer-facing control "
                "plane used by ~2 000 enterprise tenants across AWS, GCP, and "
                "bare-metal colocations."
            ),
            status=ProjectStatus.active,
        )
        p4 = Project(
            id=UUID("00000000-0000-0000-0000-000000000014"),
            organization_id=org2.id,
            name="SIEM Event Ingest API",
            slug="siem-ingest",
            description=(
                "High-throughput event ingest endpoint for the managed SIEM "
                "service. Accepts signed payloads from on-prem collectors."
            ),
            status=ProjectStatus.active,
        )

        # Mandiri Sekuritas — trading platform and KYC service
        p5 = Project(
            id=UUID("00000000-0000-0000-0000-000000000015"),
            organization_id=org3.id,
            name="MOST Trading Platform",
            slug="most-trading",
            description=(
                "Retail online trading platform (Mandiri Online Saham & "
                "Investasi). IDX-connected order routing with OJK broker-dealer "
                "licensing constraints."
            ),
            status=ProjectStatus.active,
        )

        session.add_all([p1, p2, p3, p4, p5])
        await session.flush()


        # ------------------------------------------------------------------ #
        # ASSETS
        # Real-looking domain names, realistic criticality tiers, mixed status
        # ------------------------------------------------------------------ #
        print("Seeding assets...")

        # BRI Ventures — Pinjamanku API (p1)
        a1 = Asset(
            id=UUID("00000000-0000-0000-0000-000000000021"),
            organization_id=org1.id,
            project_id=p1.id,
            name="Pinjamanku Partner API (Production)",
            asset_type=AssetType.api,
            environment=AssetEnvironment.production,
            target="api.pinjamanku.co.id",
            criticality=AssetCriticality.critical,
            status=AssetStatus.verified,
            ownership_verified_at=now - timedelta(days=14),
            verification_method=VerificationMethod.dns_txt_record,
        )
        a2 = Asset(
            id=UUID("00000000-0000-0000-0000-000000000022"),
            organization_id=org1.id,
            project_id=p1.id,
            name="Pinjamanku Staging Gateway",
            asset_type=AssetType.api,
            environment=AssetEnvironment.staging,
            target="staging-api.pinjamanku.co.id",
            criticality=AssetCriticality.high,
            status=AssetStatus.verified,
            ownership_verified_at=now - timedelta(days=14),
            verification_method=VerificationMethod.dns_txt_record,
        )
        a3 = Asset(
            id=UUID("00000000-0000-0000-0000-000000000023"),
            organization_id=org1.id,
            project_id=p1.id,
            name="OAuth 2.0 Token Service",
            asset_type=AssetType.api,
            environment=AssetEnvironment.production,
            target="auth.pinjamanku.co.id",
            criticality=AssetCriticality.critical,
            status=AssetStatus.pending_verification,
            verification_method=VerificationMethod.dns_txt_record,
            verification_requested_at=now - timedelta(hours=6),
        )

        # BRI Ventures — OJK Portal (p2)
        a4 = Asset(
            id=UUID("00000000-0000-0000-0000-000000000024"),
            organization_id=org1.id,
            project_id=p2.id,
            name="OJK Reporting Portal (Web)",
            asset_type=AssetType.web_application,
            environment=AssetEnvironment.production,
            target="ojk-portal.briventures.co.id",
            criticality=AssetCriticality.high,
            status=AssetStatus.verified,
            ownership_verified_at=now - timedelta(days=30),
            verification_method=VerificationMethod.dns_txt_record,
        )


        # Telkom Sigma — Cloud Console (p3)
        a5 = Asset(
            id=UUID("00000000-0000-0000-0000-000000000025"),
            organization_id=org2.id,
            project_id=p3.id,
            name="SigmaCloud Control Plane API",
            asset_type=AssetType.api,
            environment=AssetEnvironment.production,
            target="api.sigmacloud.telkom.co.id",
            criticality=AssetCriticality.critical,
            status=AssetStatus.verified,
            ownership_verified_at=now - timedelta(days=21),
            verification_method=VerificationMethod.dns_txt_record,
        )
        a6 = Asset(
            id=UUID("00000000-0000-0000-0000-000000000026"),
            organization_id=org2.id,
            project_id=p3.id,
            name="SigmaCloud Web Console",
            asset_type=AssetType.web_application,
            environment=AssetEnvironment.production,
            target="console.sigmacloud.telkom.co.id",
            criticality=AssetCriticality.high,
            status=AssetStatus.verified,
            ownership_verified_at=now - timedelta(days=21),
            verification_method=VerificationMethod.dns_txt_record,
        )

        # Telkom Sigma — SIEM Ingest (p4)
        a7 = Asset(
            id=UUID("00000000-0000-0000-0000-000000000027"),
            organization_id=org2.id,
            project_id=p4.id,
            name="SIEM Collector Ingest Endpoint",
            asset_type=AssetType.api,
            environment=AssetEnvironment.production,
            target="ingest.siem.sigmacloud.telkom.co.id",
            criticality=AssetCriticality.high,
            status=AssetStatus.verified,
            ownership_verified_at=now - timedelta(days=7),
            verification_method=VerificationMethod.dns_txt_record,
        )
        a8 = Asset(
            id=UUID("00000000-0000-0000-0000-000000000028"),
            organization_id=org2.id,
            project_id=p4.id,
            name="SIEM Ingest (Preproduction)",
            asset_type=AssetType.api,
            environment=AssetEnvironment.preproduction,
            target="ingest-preprod.siem.sigmacloud.telkom.co.id",
            criticality=AssetCriticality.medium,
            status=AssetStatus.draft,
        )

        # Mandiri Sekuritas — MOST Trading (p5)
        a9 = Asset(
            id=UUID("00000000-0000-0000-0000-000000000029"),
            organization_id=org3.id,
            project_id=p5.id,
            name="MOST Order Routing API",
            asset_type=AssetType.api,
            environment=AssetEnvironment.production,
            target="order-api.most.mandiri-sekuritas.co.id",
            criticality=AssetCriticality.critical,
            status=AssetStatus.verified,
            ownership_verified_at=now - timedelta(days=45),
            verification_method=VerificationMethod.dns_txt_record,
        )
        a10 = Asset(
            id=UUID("00000000-0000-0000-0000-000000000030"),
            organization_id=org3.id,
            project_id=p5.id,
            name="MOST Web Trading App",
            asset_type=AssetType.web_application,
            environment=AssetEnvironment.production,
            target="most.mandiri-sekuritas.co.id",
            criticality=AssetCriticality.critical,
            status=AssetStatus.verified,
            ownership_verified_at=now - timedelta(days=45),
            verification_method=VerificationMethod.dns_txt_record,
        )

        session.add_all([a1, a2, a3, a4, a5, a6, a7, a8, a9, a10])
        await session.flush()


        # ------------------------------------------------------------------ #
        # AUTHORIZATIONS
        # Realistic reference numbers, real-sounding document names, real contacts
        # ------------------------------------------------------------------ #
        print("Seeding authorizations...")

        # BRI Ventures — Pinjamanku API annual pentest authorization
        auth1 = Authorization(
            id=UUID("00000000-0000-0000-0000-000000000031"),
            organization_id=org1.id,
            project_id=p1.id,
            reference_number="BRIV-PENTEST-2026-003",
            title="Annual Penetration Test — Pinjamanku Partner API Q3 2026",
            status=AuthorizationStatus.active,
            valid_from=now - timedelta(days=3),
            valid_until=now + timedelta(days=11),
            timezone="Asia/Jakarta",
            maximum_risk_tier=RiskTier.tier_2_controlled,
            emergency_contact_name="Reza Firmansyah",
            emergency_contact_phone="+62-812-9100-4477",
            authorization_document_name="BRIV-PENTEST-2026-003-Authorization-Letter.pdf",
            authorization_document_sha256="a3f8d2e1c7b94056f1208d3e7a9c0b5e2d4f6a8c1e3b5d7f9a0c2e4b6d8f0a2",
        )

        # BRI Ventures — OJK Portal compliance scan (tight window)
        auth2 = Authorization(
            id=UUID("00000000-0000-0000-0000-000000000032"),
            organization_id=org1.id,
            project_id=p2.id,
            reference_number="BRIV-OJK-2026-011",
            title="OJK Sandbox Compliance Scan — Reporting Portal",
            status=AuthorizationStatus.active,
            valid_from=now - timedelta(hours=8),
            valid_until=now + timedelta(hours=16),
            timezone="Asia/Jakarta",
            maximum_risk_tier=RiskTier.tier_1_safe,
            emergency_contact_name="Dewi Anggraini",
            emergency_contact_phone="+62-811-2233-5566",
            authorization_document_name="BRIV-OJK-2026-011-Signed-Scope.pdf",
            authorization_document_sha256="b5c7e9f1a3d50278e3410f5c8b2d4a6e8c0a2e4c6a8e0b2d4f6a8c0e2d4f6b8",
        )

        # Telkom Sigma — SigmaCloud control plane quarterly assessment
        auth3 = Authorization(
            id=UUID("00000000-0000-0000-0000-000000000033"),
            organization_id=org2.id,
            project_id=p3.id,
            reference_number="TSIG-INFRASEC-2026-007",
            title="SigmaCloud Control Plane — Q3 2026 Security Assessment",
            status=AuthorizationStatus.active,
            valid_from=now - timedelta(days=1),
            valid_until=now + timedelta(days=6),
            timezone="Asia/Jakarta",
            maximum_risk_tier=RiskTier.tier_2_controlled,
            emergency_contact_name="Hendra Kusuma",
            emergency_contact_phone="+62-813-5544-3322",
            authorization_document_name="TSIG-INFRASEC-2026-007-Auth-Package.pdf",
            authorization_document_sha256="c9d1e3f5a7b90234d5670b9c1e3f5a7b9c1e3d5f7a9b1c3e5d7f9a1c3e5d7f9",
        )

        # Telkom Sigma — SIEM ingest TLS hardening (upcoming, draft)
        auth4 = Authorization(
            id=UUID("00000000-0000-0000-0000-000000000034"),
            organization_id=org2.id,
            project_id=p4.id,
            reference_number="TSIG-SIEM-2026-002",
            title="SIEM Ingest TLS & Header Hardening Review",
            status=AuthorizationStatus.draft,
            valid_from=now + timedelta(days=4),
            valid_until=now + timedelta(days=9),
            timezone="Asia/Jakarta",
            maximum_risk_tier=RiskTier.tier_1_safe,
            emergency_contact_name="Hendra Kusuma",
            emergency_contact_phone="+62-813-5544-3322",
            authorization_document_name="TSIG-SIEM-2026-002-Draft-Scope.pdf",
            authorization_document_sha256="d1e3f5a7b9c1e3f5a7b9c1e3f5a7b9c1e3f5a7b9c1e3f5a7b9c1e3f5a7b9c1",
        )

        # Mandiri Sekuritas — MOST trading platform pre-go-live security gate
        auth5 = Authorization(
            id=UUID("00000000-0000-0000-0000-000000000035"),
            organization_id=org3.id,
            project_id=p5.id,
            reference_number="MANSEK-MOST-2026-019",
            title="MOST Platform Pre-Release Security Gate — v4.2.0",
            status=AuthorizationStatus.active,
            valid_from=now - timedelta(days=2),
            valid_until=now + timedelta(days=2),
            timezone="Asia/Jakarta",
            maximum_risk_tier=RiskTier.tier_2_controlled,
            emergency_contact_name="Agus Priyanto",
            emergency_contact_phone="+62-816-7788-9900",
            authorization_document_name="MANSEK-MOST-2026-019-Security-Gate-Authorization.pdf",
            authorization_document_sha256="e3f5a7b9c1e3f5a7b9c1e3f5a7b9c1e3f5a7b9c1e3f5a7b9c1e3f5a7b9c1e3",
        )

        session.add_all([auth1, auth2, auth3, auth4, auth5])
        await session.flush()


        # ------------------------------------------------------------------ #
        # AUTHORIZATION SCOPES
        # ------------------------------------------------------------------ #
        print("Seeding authorization scopes...")

        sc1 = AuthorizationScope(
            id=UUID("00000000-0000-0000-0000-000000000081"),
            organization_id=org1.id,
            authorization_id=auth1.id,
            asset_id=a1.id,
            allowed_ports=[443],
            allowed_paths="/v1/*,/v2/*,/health,/status",
            excluded_paths="/v1/disbursement/*,/v1/repayment/*,/v2/admin/*",
            maximum_requests_per_minute=40,
            maximum_concurrency=4,
        )
        sc2 = AuthorizationScope(
            id=UUID("00000000-0000-0000-0000-000000000082"),
            organization_id=org1.id,
            authorization_id=auth1.id,
            asset_id=a2.id,
            allowed_ports=[443],
            allowed_paths="/v1/*,/v2/*,/health",
            excluded_paths="/v1/disbursement/*",
            maximum_requests_per_minute=60,
            maximum_concurrency=6,
        )
        sc3 = AuthorizationScope(
            id=UUID("00000000-0000-0000-0000-000000000083"),
            organization_id=org1.id,
            authorization_id=auth2.id,
            asset_id=a4.id,
            allowed_ports=[443],
            allowed_paths="/portal/*,/portal/health",
            excluded_paths="/portal/admin/*,/portal/export/*",
            maximum_requests_per_minute=20,
            maximum_concurrency=2,
        )
        sc4 = AuthorizationScope(
            id=UUID("00000000-0000-0000-0000-000000000084"),
            organization_id=org2.id,
            authorization_id=auth3.id,
            asset_id=a5.id,
            allowed_ports=[443],
            allowed_paths="/api/v3/*,/api/v3/health",
            excluded_paths="/api/v3/billing/*,/api/v3/iam/delete/*",
            maximum_requests_per_minute=50,
            maximum_concurrency=5,
        )
        sc5 = AuthorizationScope(
            id=UUID("00000000-0000-0000-0000-000000000085"),
            organization_id=org2.id,
            authorization_id=auth3.id,
            asset_id=a6.id,
            allowed_ports=[443],
            allowed_paths="/console/*,/console/health",
            excluded_paths="/console/admin/delete/*",
            maximum_requests_per_minute=30,
            maximum_concurrency=3,
        )
        sc6 = AuthorizationScope(
            id=UUID("00000000-0000-0000-0000-000000000086"),
            organization_id=org3.id,
            authorization_id=auth5.id,
            asset_id=a9.id,
            allowed_ports=[443],
            allowed_paths="/orders/*,/orders/health,/market-data/snapshot",
            excluded_paths="/orders/cancel-all,/orders/admin/*",
            maximum_requests_per_minute=25,
            maximum_concurrency=3,
        )
        sc7 = AuthorizationScope(
            id=UUID("00000000-0000-0000-0000-000000000087"),
            organization_id=org3.id,
            authorization_id=auth5.id,
            asset_id=a10.id,
            allowed_ports=[443],
            allowed_paths="/app/*,/app/health",
            excluded_paths="/app/admin/*,/app/kyc/delete/*",
            maximum_requests_per_minute=25,
            maximum_concurrency=3,
        )

        session.add_all([sc1, sc2, sc3, sc4, sc5, sc6, sc7])
        await session.flush()


        # ------------------------------------------------------------------ #
        # ENGAGEMENTS
        # Mix: active right now, scheduled tomorrow, completed yesterday
        # ------------------------------------------------------------------ #
        print("Seeding engagements...")

        # BRI Ventures — running now (started 90 min ago, ends in 6.5 hrs)
        eng1 = Engagement(
            id=UUID("00000000-0000-0000-0000-000000000041"),
            organization_id=org1.id,
            project_id=p1.id,
            authorization_id=auth1.id,
            name="Pinjamanku API — TLS & Auth Header Sweep",
            description=(
                "Validate TLS 1.3 enforcement, HSTS preload, CSP, and OAuth 2.0 "
                "token header hygiene on both production and staging endpoints."
            ),
            status=EngagementStatus.active,
            starts_at=now - timedelta(minutes=90),
            ends_at=now + timedelta(hours=6, minutes=30),
            timezone="Asia/Jakarta",
            max_risk_tier=RiskTier.tier_2_controlled,
            default_rate_limit_per_minute=40,
            default_concurrency_limit=4,
            emergency_contact_name="Reza Firmansyah",
            emergency_contact_email="reza.firmansyah@briventures.co.id",
            emergency_contact_phone="+62-812-9100-4477",
            kill_switch_active=False,
        )

        # BRI Ventures — OJK compliance scan (started 2 hrs ago, narrow window)
        eng2 = Engagement(
            id=UUID("00000000-0000-0000-0000-000000000042"),
            organization_id=org1.id,
            project_id=p2.id,
            authorization_id=auth2.id,
            name="OJK Portal — Mandatory Compliance Scan",
            description=(
                "OJK POJK 38 annual mandatory security scan. Read-only "
                "reconnaissance and header/TLS inspection only. Kill switch armed."
            ),
            status=EngagementStatus.active,
            starts_at=now - timedelta(hours=2),
            ends_at=now + timedelta(hours=14),
            timezone="Asia/Jakarta",
            max_risk_tier=RiskTier.tier_1_safe,
            default_rate_limit_per_minute=20,
            default_concurrency_limit=2,
            emergency_contact_name="Dewi Anggraini",
            emergency_contact_email="dewi.anggraini@briventures.co.id",
            emergency_contact_phone="+62-811-2233-5566",
            kill_switch_active=False,
        )

        # Telkom Sigma — infrastructure assessment (started 30 min ago)
        eng3 = Engagement(
            id=UUID("00000000-0000-0000-0000-000000000043"),
            organization_id=org2.id,
            project_id=p3.id,
            authorization_id=auth3.id,
            name="SigmaCloud API — Authentication & Rate-Limit Validation",
            description=(
                "Validate authentication enforcement, rate-limit headers, and "
                "mTLS configuration on the multi-tenant control plane API."
            ),
            status=EngagementStatus.active,
            starts_at=now - timedelta(minutes=30),
            ends_at=now + timedelta(hours=5),
            timezone="Asia/Jakarta",
            max_risk_tier=RiskTier.tier_2_controlled,
            default_rate_limit_per_minute=50,
            default_concurrency_limit=5,
            emergency_contact_name="Hendra Kusuma",
            emergency_contact_email="hendra.kusuma@telkomsigma.co.id",
            emergency_contact_phone="+62-813-5544-3322",
            kill_switch_active=False,
        )

        # Mandiri Sekuritas — pre-release security gate (scheduled for tomorrow)
        eng4 = Engagement(
            id=UUID("00000000-0000-0000-0000-000000000044"),
            organization_id=org3.id,
            project_id=p5.id,
            authorization_id=auth5.id,
            name="MOST v4.2.0 — Pre-Release Security Gate",
            description=(
                "Security gate before v4.2.0 goes live to IDX. Covers order "
                "routing API and web app: TLS, CSP, CORS, and session management."
            ),
            status=EngagementStatus.scheduled,
            starts_at=now + timedelta(days=1),
            ends_at=now + timedelta(days=1, hours=8),
            timezone="Asia/Jakarta",
            max_risk_tier=RiskTier.tier_2_controlled,
            default_rate_limit_per_minute=25,
            default_concurrency_limit=3,
            emergency_contact_name="Agus Priyanto",
            emergency_contact_email="agus.priyanto@mandiri-sekuritas.co.id",
            emergency_contact_phone="+62-816-7788-9900",
            kill_switch_active=False,
        )

        session.add_all([eng1, eng2, eng3, eng4])
        await session.flush()


        # ------------------------------------------------------------------ #
        # ENGAGEMENT SCOPES
        # ------------------------------------------------------------------ #
        print("Seeding engagement scopes...")

        es1 = EngagementScope(
            id=UUID("00000000-0000-0000-0000-000000000091"),
            organization_id=org1.id,
            engagement_id=eng1.id,
            asset_id=a1.id,
            authorization_scope_id=sc1.id,
            allowed_ports=[443],
            allowed_paths=["/v1/*", "/v2/*", "/health"],
            excluded_paths=["/v1/disbursement/*", "/v1/repayment/*"],
            rate_limit_per_minute=40,
            concurrency_limit=4,
        )
        es2 = EngagementScope(
            id=UUID("00000000-0000-0000-0000-000000000092"),
            organization_id=org1.id,
            engagement_id=eng1.id,
            asset_id=a2.id,
            authorization_scope_id=sc2.id,
            allowed_ports=[443],
            allowed_paths=["/v1/*", "/v2/*", "/health"],
            excluded_paths=["/v1/disbursement/*"],
            rate_limit_per_minute=60,
            concurrency_limit=6,
        )
        es3 = EngagementScope(
            id=UUID("00000000-0000-0000-0000-000000000093"),
            organization_id=org1.id,
            engagement_id=eng2.id,
            asset_id=a4.id,
            authorization_scope_id=sc3.id,
            allowed_ports=[443],
            allowed_paths=["/portal/*", "/portal/health"],
            excluded_paths=["/portal/admin/*"],
            rate_limit_per_minute=20,
            concurrency_limit=2,
        )
        es4 = EngagementScope(
            id=UUID("00000000-0000-0000-0000-000000000094"),
            organization_id=org2.id,
            engagement_id=eng3.id,
            asset_id=a5.id,
            authorization_scope_id=sc4.id,
            allowed_ports=[443],
            allowed_paths=["/api/v3/*", "/api/v3/health"],
            excluded_paths=["/api/v3/billing/*"],
            rate_limit_per_minute=50,
            concurrency_limit=5,
        )
        es5 = EngagementScope(
            id=UUID("00000000-0000-0000-0000-000000000095"),
            organization_id=org2.id,
            engagement_id=eng3.id,
            asset_id=a6.id,
            authorization_scope_id=sc5.id,
            allowed_ports=[443],
            allowed_paths=["/console/*", "/console/health"],
            excluded_paths=[],
            rate_limit_per_minute=30,
            concurrency_limit=3,
        )

        session.add_all([es1, es2, es3, es4, es5])
        await session.flush()


        # ------------------------------------------------------------------ #
        # VALIDATION EXECUTIONS
        # Mix: completed with real evidence, currently running, queued
        # ------------------------------------------------------------------ #
        print("Seeding validation executions...")

        # ── Execution 1: completed, validated (BRI Ventures prod API) ──
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
            execution_specification={
                "target": "api.pinjamanku.co.id",
                "port": 443,
                "path": "/health",
                "method": "GET",
            },
            scope_snapshot={
                "allowedPaths": ["/v1/*", "/v2/*", "/health"],
                "excludedPaths": ["/v1/disbursement/*", "/v1/repayment/*"],
                "allowedPorts": [443],
                "maxRiskTier": "tier_2_controlled",
                "scopedAssets": [str(a1.id), str(a2.id)],
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
                "workerAuthModeReady": True,
            },
            queued_at=now - timedelta(minutes=72),
            started_at=now - timedelta(minutes=71),
            finished_at=now - timedelta(minutes=69),
        )

        # ── Execution 2: completed, validated (BRI Ventures staging) ──
        exec2 = ValidationExecution(
            id=UUID("00000000-0000-0000-0000-000000000052"),
            organization_id=org1.id,
            project_id=p1.id,
            asset_id=a2.id,
            authorization_id=auth1.id,
            authorization_scope_id=sc2.id,
            engagement_id=eng1.id,
            engagement_scope_id=es2.id,
            template_id="TLS_VERSION_VALIDATION",
            status=ExecutionStatus.succeeded,
            outcome=ExecutionOutcome.validated,
            risk_tier=RiskTier.tier_1_safe,
            execution_specification={
                "target": "staging-api.pinjamanku.co.id",
                "port": 443,
                "path": "/health",
                "method": "GET",
            },
            scope_snapshot={
                "allowedPaths": ["/v1/*", "/v2/*", "/health"],
                "excludedPaths": ["/v1/disbursement/*"],
                "allowedPorts": [443],
                "maxRiskTier": "tier_2_controlled",
                "scopedAssets": [str(a1.id), str(a2.id)],
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
                "workerAuthModeReady": True,
            },
            queued_at=now - timedelta(minutes=65),
            started_at=now - timedelta(minutes=64),
            finished_at=now - timedelta(minutes=62),
        )


        # ── Execution 3: currently executing (Telkom Sigma control plane) ──
        exec3 = ValidationExecution(
            id=UUID("00000000-0000-0000-0000-000000000053"),
            organization_id=org2.id,
            project_id=p3.id,
            asset_id=a5.id,
            authorization_id=auth3.id,
            authorization_scope_id=sc4.id,
            engagement_id=eng3.id,
            engagement_scope_id=es4.id,
            template_id="HTTP_SECURITY_HEADER_VALIDATION",
            status=ExecutionStatus.executing,
            outcome=None,
            risk_tier=RiskTier.tier_1_safe,
            execution_specification={
                "target": "api.sigmacloud.telkom.co.id",
                "port": 443,
                "path": "/api/v3/health",
                "method": "GET",
            },
            scope_snapshot={
                "allowedPaths": ["/api/v3/*", "/api/v3/health"],
                "excludedPaths": ["/api/v3/billing/*"],
                "allowedPorts": [443],
                "maxRiskTier": "tier_2_controlled",
                "scopedAssets": [str(a5.id), str(a6.id)],
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
                "workerAuthModeReady": True,
            },
            queued_at=now - timedelta(minutes=8),
            started_at=now - timedelta(minutes=7),
        )

        # ── Execution 4: queued (OJK portal compliance scan) ──
        exec4 = ValidationExecution(
            id=UUID("00000000-0000-0000-0000-000000000054"),
            organization_id=org1.id,
            project_id=p2.id,
            asset_id=a4.id,
            authorization_id=auth2.id,
            authorization_scope_id=sc3.id,
            engagement_id=eng2.id,
            engagement_scope_id=es3.id,
            template_id="TLS_VERSION_VALIDATION",
            status=ExecutionStatus.queued,
            outcome=None,
            risk_tier=RiskTier.tier_1_safe,
            execution_specification={
                "target": "ojk-portal.briventures.co.id",
                "port": 443,
                "path": "/portal/health",
                "method": "GET",
            },
            scope_snapshot={
                "allowedPaths": ["/portal/*", "/portal/health"],
                "excludedPaths": ["/portal/admin/*"],
                "allowedPorts": [443],
                "maxRiskTier": "tier_1_safe",
                "scopedAssets": [str(a4.id)],
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
                "workerAuthModeReady": True,
            },
            queued_at=now - timedelta(seconds=45),
        )

        session.add_all([exec1, exec2, exec3, exec4])
        await session.flush()


        # ------------------------------------------------------------------ #
        # VALIDATION STEP RESULTS
        # Detailed evidence for the two completed executions
        # ------------------------------------------------------------------ #
        print("Seeding validation step results...")

        # Steps for exec1 — BRI Ventures prod API (all passed)
        step1 = ValidationStepResult(
            id=UUID("00000000-0000-0000-0000-000000000061"),
            organization_id=org1.id,
            execution_id=exec1.id,
            step_name="TLS handshake and certificate verification",
            status=StepStatus.passed,
            evidence={
                "protocol": "TLSv1.3",
                "cipher": "TLS_AES_256_GCM_SHA384",
                "cert_issuer": "DigiCert TLS RSA SHA256 2020 CA1",
                "cert_subject": "api.pinjamanku.co.id",
                "cert_expiry": (now + timedelta(days=187)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "san_match": True,
            },
            started_at=now - timedelta(minutes=71),
            finished_at=now - timedelta(minutes=70, seconds=48),
        )
        step2 = ValidationStepResult(
            id=UUID("00000000-0000-0000-0000-000000000062"),
            organization_id=org1.id,
            execution_id=exec1.id,
            step_name="HTTP Strict-Transport-Security header validation",
            status=StepStatus.passed,
            evidence={
                "header_present": True,
                "value": "max-age=31536000; includeSubDomains; preload",
                "max_age_seconds": 31536000,
                "include_subdomains": True,
                "preload_eligible": True,
            },
            started_at=now - timedelta(minutes=70, seconds=48),
            finished_at=now - timedelta(minutes=70, seconds=36),
        )
        step3 = ValidationStepResult(
            id=UUID("00000000-0000-0000-0000-000000000063"),
            organization_id=org1.id,
            execution_id=exec1.id,
            step_name="Security response headers inspection",
            status=StepStatus.passed,
            evidence={
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "Referrer-Policy": "strict-origin-when-cross-origin",
                "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
                "Content-Security-Policy": "default-src 'self'; script-src 'self'",
            },
            started_at=now - timedelta(minutes=70, seconds=36),
            finished_at=now - timedelta(minutes=70, seconds=20),
        )
        step4 = ValidationStepResult(
            id=UUID("00000000-0000-0000-0000-000000000064"),
            organization_id=org1.id,
            execution_id=exec1.id,
            step_name="Authorization header and OAuth scope enforcement",
            status=StepStatus.passed,
            evidence={
                "unauthenticated_returns_401": True,
                "www_authenticate_present": True,
                "www_authenticate": "Bearer realm=\"api.pinjamanku.co.id\"",
                "bearer_without_scope_returns_403": True,
            },
            started_at=now - timedelta(minutes=70, seconds=20),
            finished_at=now - timedelta(minutes=69, seconds=55),
        )

        # Steps for exec2 — BRI Ventures staging (all passed)
        step5 = ValidationStepResult(
            id=UUID("00000000-0000-0000-0000-000000000065"),
            organization_id=org1.id,
            execution_id=exec2.id,
            step_name="TLS version enforcement check",
            status=StepStatus.passed,
            evidence={
                "tls_1_0_rejected": True,
                "tls_1_1_rejected": True,
                "tls_1_2_accepted": True,
                "tls_1_3_accepted": True,
                "negotiated": "TLSv1.3",
            },
            started_at=now - timedelta(minutes=64),
            finished_at=now - timedelta(minutes=63, seconds=44),
        )
        step6 = ValidationStepResult(
            id=UUID("00000000-0000-0000-0000-000000000066"),
            organization_id=org1.id,
            execution_id=exec2.id,
            step_name="Cipher suite assessment",
            status=StepStatus.passed,
            evidence={
                "weak_ciphers_present": False,
                "forward_secrecy_supported": True,
                "preferred_cipher": "TLS_AES_256_GCM_SHA384",
                "deprecated_ciphers_rejected": ["RC4", "3DES", "NULL"],
            },
            started_at=now - timedelta(minutes=63, seconds=44),
            finished_at=now - timedelta(minutes=63, seconds=20),
        )
        step7 = ValidationStepResult(
            id=UUID("00000000-0000-0000-0000-000000000067"),
            organization_id=org1.id,
            execution_id=exec2.id,
            step_name="HTTP Strict-Transport-Security header validation",
            status=StepStatus.passed,
            evidence={
                "header_present": True,
                "value": "max-age=31536000; includeSubDomains",
                "max_age_seconds": 31536000,
                "include_subdomains": True,
                "preload_eligible": False,
                "note": "Staging: preload flag intentionally omitted.",
            },
            started_at=now - timedelta(minutes=63, seconds=20),
            finished_at=now - timedelta(minutes=63, seconds=4),
        )

        session.add_all([step1, step2, step3, step4, step5, step6, step7])
        await session.commit()

        print("+ Database seeding completed.")
        print()
        print("  Login with Organization ID:")
        print("  BRI Ventures Digital   ->  00000000-0000-0000-0000-000000000001  (dev default)")
        print("  Telkom Sigma Cloud     ->  00000000-0000-0000-0000-000000000002")
        print("  Mandiri Sekuritas      ->  00000000-0000-0000-0000-000000000003")


if __name__ == "__main__":
    asyncio.run(run_seed())
