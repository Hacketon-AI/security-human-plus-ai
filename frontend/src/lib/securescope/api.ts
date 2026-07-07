// API Client for SecureScope Control Plane

const getApiBaseUrl = () => {
  if (typeof window !== "undefined") {
    // Client-side: relative to handle Next.js rewrites proxy
    return "";
  }
  return process.env.API_INTERNAL_BASE_URL || process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";
};

// Helper for HTTP requests
async function request(path: string, options: RequestInit = {}) {
  const url = `${getApiBaseUrl()}${path}`;
  const response = await fetch(url, options);

  if (!response.ok) {
    const errorText = await response.text().catch(() => "Unknown error");
    throw new Error(`HTTP error ${response.status}: ${errorText}`);
  }

  if (response.status === 204) {
    return null;
  }

  return response.json();
}

// 1. Organizations
export async function fetchOrganizations(): Promise<any[]> {
  // Since the backend doesn't support listing all organizations (multi-tenant isolation),
  // we query the seeded organizations by their known UUIDs in development.
  const seededIds = [
    "00000000-0000-0000-0000-000000000001",
    "00000000-0000-0000-0000-000000000002",
    "00000000-0000-0000-0000-000000000003",
  ];
  const list: any[] = [];
  for (const id of seededIds) {
    try {
      const org = await request(`/api/v1/organizations/${id}`, {
        headers: { "X-Organization-Id": id },
      });
      list.push(org);
    } catch (e) {
      console.warn(`Seeded organization ${id} not found or inactive:`, e);
    }
  }
  return list;
}

export async function fetchOrganization(orgId: string): Promise<any> {
  return request(`/api/v1/organizations/${orgId}`, {
    headers: { "X-Organization-Id": orgId },
  });
}

export async function createOrganization(payload: { name: string; slug?: string }): Promise<any> {
  // Provisioning organization doesn't require a tenant context header
  return request("/api/v1/organizations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

// 2. Projects
export async function fetchProjects(orgId: string): Promise<any[]> {
  return request("/api/v1/projects", {
    headers: { "X-Organization-Id": orgId },
  });
}

export async function fetchProject(orgId: string, projectId: string): Promise<any> {
  return request(`/api/v1/projects/${projectId}`, {
    headers: { "X-Organization-Id": orgId },
  });
}

export async function createProject(orgId: string, payload: { name: string; slug?: string; description?: string }): Promise<any> {
  return request("/api/v1/projects", {
    method: "POST",
    headers: {
      "X-Organization-Id": orgId,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

// 3. Assets
export async function fetchAssets(orgId: string, projectId?: string): Promise<any[]> {
  const path = projectId ? `/api/v1/assets?project_id=${projectId}` : "/api/v1/assets";
  return request(path, {
    headers: { "X-Organization-Id": orgId },
  });
}

export async function fetchAsset(orgId: string, assetId: string): Promise<any> {
  return request(`/api/v1/assets/${assetId}`, {
    headers: { "X-Organization-Id": orgId },
  });
}

export async function createAsset(
  orgId: string,
  payload: {
    project_id: string;
    name: string;
    asset_type: string;
    environment: string;
    target: string;
    criticality: string;
  }
): Promise<any> {
  return request("/api/v1/assets", {
    method: "POST",
    headers: {
      "X-Organization-Id": orgId,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

export async function updateAsset(
  orgId: string,
  assetId: string,
  payload: { name?: string; criticality?: string }
): Promise<any> {
  return request(`/api/v1/assets/${assetId}`, {
    method: "PATCH",
    headers: {
      "X-Organization-Id": orgId,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

export async function requestAssetVerification(
  orgId: string,
  assetId: string,
  payload: { method: string }
): Promise<any> {
  return request(`/api/v1/assets/${assetId}/request-verification`, {
    method: "POST",
    headers: {
      "X-Organization-Id": orgId,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

// 4. Authorizations
export async function fetchAuthorizations(orgId: string, projectId: string): Promise<any[]> {
  return request(`/api/v1/projects/${projectId}/authorizations`, {
    headers: { "X-Organization-Id": orgId },
  });
}

export async function fetchAuthorization(orgId: string, authId: string): Promise<any> {
  return request(`/api/v1/authorizations/${authId}`, {
    headers: { "X-Organization-Id": orgId },
  });
}

export async function createAuthorization(orgId: string, projectId: string, payload: any): Promise<any> {
  return request(`/api/v1/projects/${projectId}/authorizations`, {
    method: "POST",
    headers: {
      "X-Organization-Id": orgId,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

export async function updateAuthorization(orgId: string, authId: string, payload: any): Promise<any> {
  return request(`/api/v1/authorizations/${authId}`, {
    method: "PATCH",
    headers: {
      "X-Organization-Id": orgId,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

export async function submitAuthorization(orgId: string, authId: string): Promise<any> {
  return request(`/api/v1/authorizations/${authId}/submit`, {
    method: "POST",
    headers: { "X-Organization-Id": orgId },
  });
}

export async function activateAuthorization(orgId: string, authId: string): Promise<any> {
  return request(`/api/v1/authorizations/${authId}/activate`, {
    method: "POST",
    headers: { "X-Organization-Id": orgId },
  });
}

export async function rejectAuthorization(orgId: string, authId: string, payload: { reason: string }): Promise<any> {
  return request(`/api/v1/authorizations/${authId}/reject`, {
    method: "POST",
    headers: {
      "X-Organization-Id": orgId,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

export async function revokeAuthorization(orgId: string, authId: string, payload: { reason: string }): Promise<any> {
  return request(`/api/v1/authorizations/${authId}/revoke`, {
    method: "POST",
    headers: {
      "X-Organization-Id": orgId,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

// 5. Engagements
export async function fetchEngagements(orgId: string, projectId: string): Promise<any[]> {
  return request(`/api/v1/projects/${projectId}/engagements`, {
    headers: { "X-Organization-Id": orgId },
  });
}

export async function fetchEngagement(orgId: string, engId: string): Promise<any> {
  return request(`/api/v1/engagements/${engId}`, {
    headers: { "X-Organization-Id": orgId },
  });
}

export async function createEngagement(orgId: string, projectId: string, payload: any): Promise<any> {
  return request(`/api/v1/projects/${projectId}/engagements`, {
    method: "POST",
    headers: {
      "X-Organization-Id": orgId,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

export async function updateEngagement(orgId: string, engId: string, payload: any): Promise<any> {
  return request(`/api/v1/engagements/${engId}`, {
    method: "PATCH",
    headers: {
      "X-Organization-Id": orgId,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

export async function scheduleEngagement(orgId: string, engId: string): Promise<any> {
  return request(`/api/v1/engagements/${engId}/schedule`, {
    method: "POST",
    headers: { "X-Organization-Id": orgId },
  });
}

export async function activateEngagement(orgId: string, engId: string): Promise<any> {
  return request(`/api/v1/engagements/${engId}/activate`, {
    method: "POST",
    headers: { "X-Organization-Id": orgId },
  });
}

export async function pauseEngagement(orgId: string, engId: string): Promise<any> {
  return request(`/api/v1/engagements/${engId}/pause`, {
    method: "POST",
    headers: { "X-Organization-Id": orgId },
  });
}

export async function resumeEngagement(orgId: string, engId: string): Promise<any> {
  return request(`/api/v1/engagements/${engId}/resume`, {
    method: "POST",
    headers: { "X-Organization-Id": orgId },
  });
}

export async function completeEngagement(orgId: string, engId: string): Promise<any> {
  return request(`/api/v1/engagements/${engId}/complete`, {
    method: "POST",
    headers: { "X-Organization-Id": orgId },
  });
}

export async function cancelEngagement(orgId: string, engId: string): Promise<any> {
  return request(`/api/v1/engagements/${engId}/cancel`, {
    method: "POST",
    headers: { "X-Organization-Id": orgId },
  });
}

export async function killSwitchEngagement(orgId: string, engId: string, payload: { active: boolean; reason: string }): Promise<any> {
  return request(`/api/v1/engagements/${engId}/kill-switch`, {
    method: "POST",
    headers: {
      "X-Organization-Id": orgId,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

// 6. Validation Executions
export async function fetchExecutions(orgId: string, projectId: string): Promise<any[]> {
  return request(`/api/v1/projects/${projectId}/validation-executions`, {
    headers: { "X-Organization-Id": orgId },
  });
}

export async function fetchExecution(orgId: string, execId: string): Promise<any> {
  return request(`/api/v1/validation-executions/${execId}`, {
    headers: { "X-Organization-Id": orgId },
  });
}

export async function createExecution(
  orgId: string,
  payload: {
    asset_id: string;
    engagement_id: string;
    template_id: string;
    risk_tier: string;
    execution_specification: any;
  }
): Promise<any> {
  return request("/api/v1/validation-executions", {
    method: "POST",
    headers: {
      "X-Organization-Id": orgId,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

export async function cancelExecution(orgId: string, execId: string): Promise<any> {
  return request(`/api/v1/validation-executions/${execId}/cancel`, {
    method: "POST",
    headers: { "X-Organization-Id": orgId },
  });
}
