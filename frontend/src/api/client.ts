import type {
  LoginRequest,
  LoginResponse,
  UserRead,
  LabTemplateCreate,
  LabTemplateRead,
  LabTemplateUpdate,
  SessionCreate,
  SessionRead,
  SessionDetailRead,
  SessionProvisionResponse,
  StudentCreate,
  StudentRead,
  StudentResetRequest,
  StudentResetResponse,
  CSVImportResponse,
  EventRead,
  LudusRangeListResponse,
  LudusRangeConfigResponse,
  LudusRangeDetailResponse,
  LudusRangeTagsResponse,
  LudusRangeLogsResponse,
  LudusLogHistoryResponse,
  LudusLogEntryDetailResponse,
  LudusTextResponse,
  LudusRangeUsersResponse,
  LudusAccessibleRangesResponse,
  LudusSnapshotListResponse,
  LudusTemplateListResponse,
  LudusTemplateBuildStatusResponse,
  LudusActionResponse,
  PowerActionRequest,
  SnapshotCreateRequest,
  SnapshotRevertRequest,
  TemplateBuildRequest,
  TestingStartRequest,
  TestingStopRequest,
  TestingAllowDenyRequest,
  TestingAllowDenyResponse,
  TestingUpdateRequest,
  LudusGroupListResponse,
  LudusGroupUsersResponse,
  LudusGroupRangesResponse,
  LudusSubscriptionRolesResponse,
  LudusRoleVarsResponse,
  LudusInstalledRolesResponse,
  LudusUserListResponse,
  UserCreateRequest,
  UserCreateResponse,
  PlatformSettings,
  LudusServersResponse,
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

  update: (id: number, data: LabTemplateUpdate) =>
    request<LabTemplateRead>(`/api/labs/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  delete: (id: number) =>
    request<void>(`/api/labs/${id}`, { method: "DELETE" }),

  uploadImage: (id: number, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<LabTemplateRead>(`/api/labs/${id}/image`, {
      method: "POST",
      body: form,
      headers: {},
    });
  },

  deleteImage: (id: number) =>
    request<void>(`/api/labs/${id}/image`, { method: "DELETE" }),
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

  end: (id: number) =>
    request<SessionRead>(`/api/sessions/${id}/end`, { method: "POST" }),

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

  importCsv: (sessionId: number, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<CSVImportResponse>(
      `/api/sessions/${sessionId}/students/import`,
      {
        method: "POST",
        body: form,
        headers: {}, // let browser set multipart boundary
      },
    );
  },
};

/** Build a query string appending ``server`` if it's not ``"default"``. */
function serverQs(server?: string, extra?: Record<string, string>): string {
  const qs = new URLSearchParams();
  if (server && server !== "default") qs.set("server", server);
  if (extra) {
    for (const [k, v] of Object.entries(extra)) qs.set(k, v);
  }
  const q = qs.toString();
  return q ? `?${q}` : "";
}

// Ludus Discovery & Management
export const ludus = {
  ranges: (server?: string) =>
    request<LudusRangeListResponse>(`/api/ludus/ranges${serverQs(server)}`),

  rangeConfig: (rangeNumber: number, server?: string) =>
    request<LudusRangeConfigResponse>(`/api/ludus/ranges/${rangeNumber}/config${serverQs(server)}`),

  deployRange: (rangeNumber: number, data: { user_id: string }, server?: string) =>
    request<LudusActionResponse>(`/api/ludus/ranges/${rangeNumber}/deploy${serverQs(server)}`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  destroyRange: (rangeNumber: number, server?: string, force?: boolean, userId?: string) => {
    const extra: Record<string, string> = {};
    if (force) extra.force = "true";
    if (userId) extra.user_id = userId;
    return request<LudusActionResponse>(
      `/api/ludus/ranges/${rangeNumber}${serverQs(server, Object.keys(extra).length ? extra : undefined)}`,
      { method: "DELETE" },
    );
  },

  powerOn: (rangeNumber: number, data: PowerActionRequest, server?: string) =>
    request<LudusActionResponse>(`/api/ludus/ranges/${rangeNumber}/power-on${serverQs(server)}`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  powerOff: (rangeNumber: number, data: PowerActionRequest, server?: string) =>
    request<LudusActionResponse>(`/api/ludus/ranges/${rangeNumber}/power-off${serverQs(server)}`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  snapshots: (params?: { user_id?: string; range_number?: number; range_id?: string; server?: string }) => {
    const qs = new URLSearchParams();
    if (params?.server && params.server !== "default") qs.set("server", params.server);
    if (params?.user_id) qs.set("user_id", params.user_id);
    if (params?.range_number != null) qs.set("range_number", String(params.range_number));
    if (params?.range_id) qs.set("range_id", params.range_id);
    const q = qs.toString();
    return request<LudusSnapshotListResponse>(`/api/ludus/snapshots${q ? `?${q}` : ""}`);
  },

  createSnapshot: (data: SnapshotCreateRequest, server?: string) =>
    request<LudusActionResponse>(`/api/ludus/snapshots${serverQs(server)}`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  revertSnapshot: (data: SnapshotRevertRequest, server?: string) =>
    request<LudusActionResponse>(`/api/ludus/snapshots/revert${serverQs(server)}`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  deleteSnapshot: (name: string, userId: string, rangeId?: string, server?: string) => {
    const extra: Record<string, string> = { user_id: userId };
    if (rangeId) extra.range_id = rangeId;
    if (server && server !== "default") extra.server = server;
    const qs = new URLSearchParams(extra).toString();
    return request<LudusActionResponse>(`/api/ludus/snapshots/${encodeURIComponent(name)}?${qs}`, {
      method: "DELETE",
    });
  },

  templates: (server?: string) =>
    request<LudusTemplateListResponse>(`/api/ludus/templates${serverQs(server)}`),

  deleteTemplate: (name: string, server?: string) =>
    request<LudusActionResponse>(`/api/ludus/templates/${encodeURIComponent(name)}${serverQs(server)}`, {
      method: "DELETE",
    }),

  buildTemplates: (data: TemplateBuildRequest, server?: string) =>
    request<LudusActionResponse>(`/api/ludus/templates/build${serverQs(server)}`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  abortTemplateBuild: (server?: string) =>
    request<LudusActionResponse>(`/api/ludus/templates/abort${serverQs(server)}`, {
      method: "POST",
    }),

  templateBuildStatus: (server?: string) =>
    request<LudusTemplateBuildStatusResponse>(`/api/ludus/templates/build-status${serverQs(server)}`),

  templateBuildLogs: (server?: string) =>
    request<LudusTextResponse>(`/api/ludus/templates/build-logs${serverQs(server)}`),

  // Range detail / VM operations
  rangeVms: (params?: { range_id?: number; user_id?: string; server?: string }) => {
    const qs = new URLSearchParams();
    if (params?.server && params.server !== "default") qs.set("server", params.server);
    if (params?.range_id != null) qs.set("range_id", String(params.range_id));
    if (params?.user_id) qs.set("user_id", params.user_id);
    const q = qs.toString();
    return request<LudusRangeDetailResponse>(`/api/ludus/range/vms${q ? `?${q}` : ""}`);
  },

  destroyVm: (vmId: number, server?: string) =>
    request<LudusActionResponse>(`/api/ludus/vm/${vmId}${serverQs(server)}`, {
      method: "DELETE",
    }),

  abortRange: (data: { range_id?: number; user_id?: string }, server?: string) =>
    request<LudusActionResponse>(`/api/ludus/range/abort${serverQs(server)}`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  deleteRangeVms: (rangeId: number, userId?: string, server?: string) => {
    const extra: Record<string, string> = {};
    if (userId) extra.user_id = userId;
    return request<LudusActionResponse>(
      `/api/ludus/range/${rangeId}/vms${serverQs(server, extra)}`,
      { method: "DELETE" },
    );
  },

  rangeTags: (server?: string) =>
    request<LudusRangeTagsResponse>(`/api/ludus/range/tags${serverQs(server)}`),

  rangeConfigExample: (server?: string) =>
    request<LudusTextResponse>(`/api/ludus/range/config/example${serverQs(server)}`),

  rangeLogs: (params?: {
    range_id?: number; user_id?: string; tail?: number; cursor?: string; server?: string;
  }) => {
    const qs = new URLSearchParams();
    if (params?.server && params.server !== "default") qs.set("server", params.server);
    if (params?.range_id != null) qs.set("range_id", String(params.range_id));
    if (params?.user_id) qs.set("user_id", params.user_id);
    if (params?.tail != null) qs.set("tail", String(params.tail));
    if (params?.cursor) qs.set("cursor", params.cursor);
    const q = qs.toString();
    return request<LudusRangeLogsResponse>(`/api/ludus/range/logs${q ? `?${q}` : ""}`);
  },

  rangeLogsHistory: (params?: { range_id?: number; user_id?: string; server?: string }) => {
    const qs = new URLSearchParams();
    if (params?.server && params.server !== "default") qs.set("server", params.server);
    if (params?.range_id != null) qs.set("range_id", String(params.range_id));
    if (params?.user_id) qs.set("user_id", params.user_id);
    const q = qs.toString();
    return request<LudusLogHistoryResponse>(`/api/ludus/range/logs/history${q ? `?${q}` : ""}`);
  },

  rangeLogEntry: (logId: number, server?: string) =>
    request<LudusLogEntryDetailResponse>(`/api/ludus/range/logs/history/${logId}${serverQs(server)}`),

  rangeEtcHosts: (params?: { range_id?: number; user_id?: string; server?: string }) => {
    const qs = new URLSearchParams();
    if (params?.server && params.server !== "default") qs.set("server", params.server);
    if (params?.range_id != null) qs.set("range_id", String(params.range_id));
    if (params?.user_id) qs.set("user_id", params.user_id);
    const q = qs.toString();
    return request<LudusTextResponse>(`/api/ludus/range/etchosts${q ? `?${q}` : ""}`);
  },

  rangeSshConfig: (server?: string) =>
    request<LudusTextResponse>(`/api/ludus/range/sshconfig${serverQs(server)}`),

  rangeRdpConfigs: async (params?: { range_id?: number; user_id?: string; server?: string }) => {
    const qs = new URLSearchParams();
    if (params?.server && params.server !== "default") qs.set("server", params.server);
    if (params?.range_id != null) qs.set("range_id", String(params.range_id));
    if (params?.user_id) qs.set("user_id", params.user_id);
    const q = qs.toString();
    const res = await fetch(`/api/ludus/range/rdpconfigs${q ? `?${q}` : ""}`, {
      credentials: "include",
    });
    if (!res.ok) throw new ApiError(res.status, "Failed to download RDP configs");
    return res.blob();
  },

  rangeAnsibleInventory: (params?: { range_id?: number; user_id?: string; server?: string }) => {
    const qs = new URLSearchParams();
    if (params?.server && params.server !== "default") qs.set("server", params.server);
    if (params?.range_id != null) qs.set("range_id", String(params.range_id));
    if (params?.user_id) qs.set("user_id", params.user_id);
    const q = qs.toString();
    return request<LudusTextResponse>(`/api/ludus/range/ansibleinventory${q ? `?${q}` : ""}`);
  },

  createRange: (data: { name: string; range_id: number }, server?: string) =>
    request<LudusActionResponse>(`/api/ludus/ranges/create${serverQs(server)}`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  revokeRange: (data: { user_id: string; range_id: number; force?: boolean }, server?: string) =>
    request<LudusActionResponse>(`/api/ludus/ranges/revoke${serverQs(server)}`, {
      method: "DELETE",
      body: JSON.stringify(data),
    }),

  rangeUsers: (rangeId: number, server?: string) =>
    request<LudusRangeUsersResponse>(`/api/ludus/ranges/${rangeId}/users${serverQs(server)}`),

  accessibleRanges: (server?: string) =>
    request<LudusAccessibleRangesResponse>(`/api/ludus/ranges/accessible${serverQs(server)}`),

  users: (server?: string) =>
    request<LudusUserListResponse>(`/api/ludus/users${serverQs(server)}`),

  createUser: (data: UserCreateRequest, server?: string) =>
    request<UserCreateResponse>(`/api/ludus/users${serverQs(server)}`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  deleteUser: (userId: string, server?: string) =>
    request<LudusActionResponse>(`/api/ludus/users/${encodeURIComponent(userId)}${serverQs(server)}`, {
      method: "DELETE",
    }),

  userWireguard: async (userId: string, server?: string) => {
    const res = await fetch(
      `/api/ludus/users/${encodeURIComponent(userId)}/wireguard${serverQs(server)}`,
      { credentials: "include" },
    );
    if (!res.ok) throw new ApiError(res.status, "Failed to download WireGuard config");
    return res.blob();
  },
};

// Ludus Testing
export const ludusTesting = {
  start: (data: TestingStartRequest, server?: string) =>
    request<LudusActionResponse>(`/api/ludus/testing/start${serverQs(server)}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  stop: (data: TestingStopRequest, server?: string) =>
    request<LudusActionResponse>(`/api/ludus/testing/stop${serverQs(server)}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  allow: (data: TestingAllowDenyRequest, server?: string) =>
    request<TestingAllowDenyResponse>(`/api/ludus/testing/allow${serverQs(server)}`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  deny: (data: TestingAllowDenyRequest, server?: string) =>
    request<TestingAllowDenyResponse>(`/api/ludus/testing/deny${serverQs(server)}`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  update: (data: TestingUpdateRequest, server?: string) =>
    request<LudusActionResponse>(`/api/ludus/testing/update${serverQs(server)}`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
};

// Ludus Groups
export const ludusGroups = {
  list: (server?: string) =>
    request<LudusGroupListResponse>(`/api/ludus/groups${serverQs(server)}`),

  create: (data: { name: string; description?: string }, server?: string) =>
    request<LudusActionResponse>(`/api/ludus/groups${serverQs(server)}`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  delete: (groupName: string, server?: string) =>
    request<LudusActionResponse>(`/api/ludus/groups/${encodeURIComponent(groupName)}${serverQs(server)}`, {
      method: "DELETE",
    }),

  users: (groupName: string, server?: string) =>
    request<LudusGroupUsersResponse>(`/api/ludus/groups/${encodeURIComponent(groupName)}/users${serverQs(server)}`),

  addUsers: (groupName: string, data: { user_ids: string[]; managers?: boolean }, server?: string) =>
    request<LudusActionResponse>(`/api/ludus/groups/${encodeURIComponent(groupName)}/users${serverQs(server)}`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  removeUsers: (groupName: string, data: { user_ids: string[] }, server?: string) =>
    request<LudusActionResponse>(`/api/ludus/groups/${encodeURIComponent(groupName)}/users${serverQs(server)}`, {
      method: "DELETE",
      body: JSON.stringify(data),
    }),

  ranges: (groupName: string, server?: string) =>
    request<LudusGroupRangesResponse>(`/api/ludus/groups/${encodeURIComponent(groupName)}/ranges${serverQs(server)}`),

  addRanges: (groupName: string, data: { range_ids: number[] }, server?: string) =>
    request<LudusActionResponse>(`/api/ludus/groups/${encodeURIComponent(groupName)}/ranges${serverQs(server)}`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  removeRanges: (groupName: string, data: { range_ids: number[] }, server?: string) =>
    request<LudusActionResponse>(`/api/ludus/groups/${encodeURIComponent(groupName)}/ranges${serverQs(server)}`, {
      method: "DELETE",
      body: JSON.stringify(data),
    }),
};

// Ludus Ansible
export const ludusAnsible = {
  subscriptionRoles: (server?: string) =>
    request<LudusSubscriptionRolesResponse>(`/api/ludus/ansible/subscription-roles${serverQs(server)}`),

  installSubscriptionRoles: (data: { roles: string[]; global_?: boolean; force?: boolean }, server?: string) =>
    request<LudusActionResponse>(`/api/ludus/ansible/subscription-roles${serverQs(server)}`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  roleVars: (data: { roles: string[] }, server?: string) =>
    request<LudusRoleVarsResponse>(`/api/ludus/ansible/role/vars${serverQs(server)}`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  list: (params?: { user_id?: string; server?: string }) => {
    const qs = new URLSearchParams();
    if (params?.server && params.server !== "default") qs.set("server", params.server);
    if (params?.user_id) qs.set("user_id", params.user_id);
    const q = qs.toString();
    return request<LudusInstalledRolesResponse>(`/api/ludus/ansible${q ? `?${q}` : ""}`);
  },

  changeRoleScope: (data: { roles: string[]; global_?: boolean; copy?: boolean }, server?: string) =>
    request<LudusActionResponse>(`/api/ludus/ansible/role/scope${serverQs(server)}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  manageRole: (data: { role: string; action: string; version?: string; force?: boolean; global_?: boolean }, server?: string) =>
    request<LudusActionResponse>(`/api/ludus/ansible/role${serverQs(server)}`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  installRoleFromTar: async (file: File, force?: boolean, server?: string) => {
    const form = new FormData();
    form.append("file", file);
    const qs = new URLSearchParams();
    if (server && server !== "default") qs.set("server", server);
    if (force) qs.set("force", "true");
    const q = qs.toString();
    return request<LudusActionResponse>(`/api/ludus/ansible/role/fromtar${q ? `?${q}` : ""}`, {
      method: "PUT",
      body: form,
      headers: {}, // let browser set multipart boundary
    });
  },

  installCollection: (data: { collection: string; version?: string; force?: boolean }, server?: string) =>
    request<LudusActionResponse>(`/api/ludus/ansible/collection${serverQs(server)}`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
};

// Settings
export const settings = {
  get: () => request<PlatformSettings>("/api/settings"),

  ludusServers: () =>
    request<LudusServersResponse>("/api/settings/ludus-servers"),

  testConnection: (server?: string) =>
    request<{ status: string; latency_ms: number }>(
      `/api/settings/test-ludus${serverQs(server)}`,
      { method: "POST" },
    ),

  changePassword: (data: { current_password: string; new_password: string }) =>
    request<void>("/api/settings/change-password", {
      method: "POST",
      body: JSON.stringify(data),
    }),
};

// Events (audit log)
export const events = {
  list: (params?: { session_id?: number; limit?: number; offset?: number }) => {
    const qs = new URLSearchParams();
    if (params?.session_id != null) qs.set("session_id", String(params.session_id));
    if (params?.limit != null) qs.set("limit", String(params.limit));
    if (params?.offset != null) qs.set("offset", String(params.offset));
    const q = qs.toString();
    return request<EventRead[]>(`/api/events${q ? `?${q}` : ""}`);
  },
};
