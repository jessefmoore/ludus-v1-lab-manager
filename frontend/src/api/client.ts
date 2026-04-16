import type {
  LoginRequest,
  LoginResponse,
  UserRead,
  LabTemplateCreate,
  LabTemplateRead,
  SessionCreate,
  SessionRead,
  SessionDetailRead,
  SessionProvisionResponse,
  StudentCreate,
  StudentRead,
  StudentResetRequest,
  StudentResetResponse,
} from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

async function request<T>(
  url: string,
  options: RequestInit = {},
): Promise<T> {
  const res = await fetch(url, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
    ...options,
  });

  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      // no JSON body
    }
    // Global 401 handler: redirect to login if session expired
    // Skip for auth endpoints to avoid redirect loops
    if (res.status === 401 && !url.startsWith("/api/auth/")) {
      window.location.href = "/login";
    }
    throw new ApiError(res.status, detail);
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

// Auth
export const auth = {
  login: (data: LoginRequest) =>
    request<LoginResponse>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  logout: () =>
    request<void>("/api/auth/logout", { method: "POST" }),

  me: () => request<UserRead>("/api/auth/me"),
};

// Lab Templates
export const labs = {
  list: () => request<LabTemplateRead[]>("/api/labs"),

  get: (id: number) => request<LabTemplateRead>(`/api/labs/${id}`),

  create: (data: LabTemplateCreate) =>
    request<LabTemplateRead>("/api/labs", {
      method: "POST",
      body: JSON.stringify(data),
    }),
};

// Sessions
export const sessions = {
  list: () => request<SessionRead[]>("/api/sessions"),

  get: (id: number) =>
    request<SessionDetailRead>(`/api/sessions/${id}`),

  create: (data: SessionCreate) =>
    request<SessionRead>("/api/sessions", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  delete: (id: number) =>
    request<void>(`/api/sessions/${id}`, { method: "DELETE" }),

  provision: (id: number) =>
    request<SessionProvisionResponse>(
      `/api/sessions/${id}/provision`,
      { method: "POST" },
    ),
};

// Students
export const students = {
  create: (sessionId: number, data: StudentCreate) =>
    request<StudentRead>(`/api/sessions/${sessionId}/students`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  delete: (id: number) =>
    request<void>(`/api/students/${id}`, { method: "DELETE" }),

  reset: (id: number, data?: StudentResetRequest) =>
    request<StudentResetResponse>(`/api/students/${id}/reset`, {
      method: "POST",
      body: JSON.stringify(data ?? {}),
    }),
};
