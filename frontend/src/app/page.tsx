"use client";

import * as React from "react";
import { getStoredToken, verifyToken, clearAuth } from "@/lib/securescope/authApi";
import { useApp } from "@/lib/securescope/store";
import { LoginPage } from "@/components/securescope/pages/LoginPage";
import { DashboardPage } from "@/components/securescope/pages/DashboardPage";
import { PentestAuditPage } from "@/components/securescope/pages/PentestAuditPage";
import { ExecutionWizardPage } from "@/components/securescope/pages/ExecutionWizardPage";
import { ExecutionDetailPage } from "@/components/securescope/pages/ExecutionDetailPage";
import { AssetsListPage, AssetDetailPage } from "@/components/securescope/pages/AssetPages";
import { OrganizationDetailPage, OrganizationsListPage } from "@/components/securescope/pages/OrganizationPages";
import { ProjectDetailPage, ProjectsListPage } from "@/components/securescope/pages/ProjectPages";
import { AuthorizationDetailPage, AuthorizationsListPage } from "@/components/securescope/pages/AuthorizationPages";
import { EngagementDetailPage, EngagementsListPage } from "@/components/securescope/pages/EngagementPages";
import { WorkersPage } from "@/components/securescope/pages/WorkersPage";
import { AuditPage } from "@/components/securescope/pages/AuditPage";
import { SettingsPage } from "@/components/securescope/pages/SettingsPage";
import { KillSwitchModal } from "@/components/securescope/shell/KillSwitchModal";

export default function Page() {
  const route = useApp((state) => state.route);
  const authenticated = useApp((state) => state.authenticated);
  const login = useApp((state) => state.login);
  const initData = useApp((state) => state.initData);
  const [checkingAuth, setCheckingAuth] = React.useState(true);

  React.useEffect(() => {
    const checkStoredAuth = async () => {
      const token = getStoredToken();
      if (token) {
        try {
          const verified = await verifyToken(token);
          if (!verified.org_id) throw new Error("Account has no organization assignment");
          login(verified.org_id);
        } catch {
          clearAuth();
        }
      }
      setCheckingAuth(false);
    };
    void checkStoredAuth();
  }, [login]);

  React.useEffect(() => {
    if (authenticated) void initData();
  }, [authenticated, initData]);

  const modal = <KillSwitchModal />;
  if (checkingAuth) {
    return (
      <div className="min-h-screen bg-[#020408] flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-cyan-400/20 border-t-cyan-400 rounded-full animate-spin" />
          <span className="font-(--font-jetbrains) text-[10px] uppercase tracking-widest text-slate-500">Verifying session...</span>
        </div>
      </div>
    );
  }

  if (!authenticated || route === "login") {
    return <><LoginPage />{modal}</>;
  }

  let content: React.ReactNode;
  switch (route) {
    case "dashboard": content = <DashboardPage view="overview" />; break;
    case "operations": content = <DashboardPage view="operations" />; break;
    case "ai_intelligence": content = <DashboardPage view="ai" />; break;
    case "pentest_audit": content = <PentestAuditPage />; break;
    case "organizations": content = <OrganizationsListPage />; break;
    case "organization_detail": content = <OrganizationDetailPage />; break;
    case "projects": content = <ProjectsListPage />; break;
    case "project_detail": content = <ProjectDetailPage />; break;
    case "assets": content = <AssetsListPage />; break;
    case "asset_detail": content = <AssetDetailPage />; break;
    case "authorizations": content = <AuthorizationsListPage />; break;
    case "authorization_detail": content = <AuthorizationDetailPage />; break;
    case "engagements": content = <EngagementsListPage />; break;
    case "engagement_detail": content = <EngagementDetailPage />; break;
    case "execution_wizard": content = <ExecutionWizardPage />; break;
    case "execution_detail": content = <ExecutionDetailPage />; break;
    case "workers": content = <WorkersPage />; break;
    case "audit": content = <AuditPage />; break;
    case "settings": content = <SettingsPage />; break;
    default: content = <DashboardPage view="overview" />;
  }
  return <>{content}{modal}</>;
}
