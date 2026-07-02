"use client";

import * as React from "react";
import { useApp } from "@/lib/securescope/store";
import { LoginPage } from "@/components/securescope/pages/LoginPage";
import { DashboardPage } from "@/components/securescope/pages/DashboardPage";
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
  const route = useApp((s) => s.route);
  const authenticated = useApp((s) => s.authenticated);
  const initData = useApp((s) => s.initData);

  React.useEffect(() => {
    if (authenticated) {
      initData();
    }
  }, [authenticated, initData]);

  // Always render the KillSwitchModal so it can be triggered from anywhere
  const modal = <KillSwitchModal />;

  if (!authenticated || route === "login") {
    return (
      <>
        <LoginPage />
        {modal}
      </>
    );
  }

  let content: React.ReactNode = null;
  switch (route) {
    case "dashboard":
      content = <DashboardPage />;
      break;
    case "organizations":
      content = <OrganizationsListPage />;
      break;
    case "organization_detail":
      content = <OrganizationDetailPage />;
      break;
    case "projects":
      content = <ProjectsListPage />;
      break;
    case "project_detail":
      content = <ProjectDetailPage />;
      break;
    case "assets":
      content = <AssetsListPage />;
      break;
    case "asset_detail":
      content = <AssetDetailPage />;
      break;
    case "authorizations":
      content = <AuthorizationsListPage />;
      break;
    case "authorization_detail":
      content = <AuthorizationDetailPage />;
      break;
    case "engagements":
      content = <EngagementsListPage />;
      break;
    case "engagement_detail":
      content = <EngagementDetailPage />;
      break;
    case "execution_wizard":
      content = <ExecutionWizardPage />;
      break;
    case "execution_detail":
      content = <ExecutionDetailPage />;
      break;
    case "workers":
      content = <WorkersPage />;
      break;
    case "audit":
      content = <AuditPage />;
      break;
    case "settings":
      content = <SettingsPage />;
      break;
    default:
      content = <DashboardPage />;
  }

  return (
    <>
      {content}
      {modal}
    </>
  );
}
