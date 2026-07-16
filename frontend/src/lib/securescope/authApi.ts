// Authentication API client for SecureScope.

const getApiBaseUrl = () => {
  if (typeof window !== "undefined") return "";
  return (
    process.env.API_INTERNAL_BASE_URL ||
    process.env.NEXT_PUBLIC_API_BASE_URL ||
    "http://127.0.0.1:8000"
  );
};

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  email: string;
  username: string;
  password: string;
  full_name?: string;
  role?: string;
}

export interface UserResponse {
  id: string;
  email: string;
  username: string;
  full_name: string | null;
  role: string;
  is_active: boolean;
  organization_id: string | null;
  last_login_at: string | null;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: UserResponse;
}

export interface VerifyTokenResponse {
  valid: boolean;
  user_id: string;
  email: string;
  role: string;
  org_id: string | null;
}

async function authFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${getApiBaseUrl()}/auth${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  });

  if (!response.ok) {
    const errorText = await response.text().catch(() => "Unknown error");
    try {
      const parsed: unknown = JSON.parse(errorText);
      if (
        typeof parsed === "object" &&
        parsed !== null &&
        "detail" in parsed &&
        typeof parsed.detail === "string"
      ) {
        throw new Error(parsed.detail);
      }
    } catch (error) {
      if (error instanceof Error && error.message !== errorText) throw error;
    }
    throw new Error(errorText);
  }

  if (response.status === 204) return null as T;
  return response.json() as Promise<T>;
}

export async function loginUser(request: LoginRequest): Promise<TokenResponse> {
  return authFetch<TokenResponse>("/login", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export async function registerUser(request: RegisterRequest): Promise<UserResponse> {
  const token = getStoredToken();
  if (!token) throw new Error("An administrator session is required.");
  return authFetch<UserResponse>("/register", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify(request),
  });
}

export async function verifyToken(token: string): Promise<VerifyTokenResponse> {
  return authFetch<VerifyTokenResponse>("/verify-token", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
}

export async function getMe(token: string): Promise<UserResponse> {
  return authFetch<UserResponse>("/me", {
    method: "GET",
    headers: { Authorization: `Bearer ${token}` },
  });
}

const TOKEN_KEY = "securescope_token";
const USER_KEY = "securescope_user";

export function saveToken(token: string): void {
  if (typeof window !== "undefined") localStorage.setItem(TOKEN_KEY, token);
}

export function getStoredToken(): string | null {
  return typeof window === "undefined" ? null : localStorage.getItem(TOKEN_KEY);
}

export function saveUser(user: UserResponse): void {
  if (typeof window !== "undefined") {
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  }
}

export function getStoredUser(): UserResponse | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as UserResponse;
  } catch {
    return null;
  }
}

export function clearAuth(): void {
  if (typeof window !== "undefined") {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  }
}

export function isAuthenticated(): boolean {
  return getStoredToken() !== null;
}
