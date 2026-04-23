// Enums matching backend Pydantic schemas
export type LabMode = "shared" | "dedicated";
export type SessionStatus = "draft" | "provisioning" | "active" | "ended";
export type StudentStatus = "pending" | "ready" | "error";

// Auth
export interface UserRead {
  id: number;
  email: string;
  role: string;
  created_at: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface LoginResponse {
  user: UserRead;
}

// Lab Templates
export interface LabTemplateCreate {
  name: string;
  description: string | null;
  range_config_yaml: string;
  default_mode: LabMode;
  ludus_server?: string;
  entry_point_vm: string | null;
}

export interface LabTemplateRead {
  id: number;
  name: string;
  description: string | null;
  range_config_yaml: string;
  default_mode: LabMode;
  ludus_server: string;
  entry_point_vm: string | null;
  cover_image: string | null;
  created_at: string;
  session_count: number;
}

export interface LabTemplateUpdate {
  name?: string;
  description?: string | null;
  range_config_yaml?: string;
  default_mode?: LabMode;
  ludus_server?: string;
  entry_point_vm?: string | null;
}

// Sessions
export interface SessionCreate {
  name: string;
  lab_template_id: number;
  mode: LabMode;
  start_date: string | null;
  end_date: string | null;
  shared_range_id: string | null;
}

export interface SessionRead {
  id: number;
  name: string;
  lab_template_id: number;
  mode: LabMode;
  start_date: string | null;
  end_date: string | null;
  shared_range_id: string | null;
  status: SessionStatus;
  created_at: string;
}

export interface SessionDetailRead extends SessionRead {
  students: StudentRead[];
}

export interface SessionProvisionResponse {
  provisioned: number;
  failed: number;
  skipped: number;
  students: StudentRead[];
}

// Students
export interface StudentCreate {
  full_name?: string;
  email?: string;
  ludus_userid?: string;
}

export interface StudentRead {
  id: number;
  full_name: string;
  email: string;
  ludus_userid: string;
  range_id: string | null;
  status: StudentStatus;
  invite_redeemed_at: string | null;
  created_at: string;
  invite_url: string;
}

export interface StudentResetRequest {
  snapshot_name?: string;
}

export interface StudentResetResponse {
  status: string;
  snapshot_name: string;
}

// CSV Import
export interface CSVImportResponse {
  created: number;
  failed: number;
  errors: string[];
}

// Ludus Discovery
export interface LudusRange {
  rangeID: string;
  rangeNumber: number;
  name?: string;
  numberOfVMs?: number;
  rangeState?: string;
  lastDeployment?: string;
  description?: string;
  testingEnabled?: boolean;
  [key: string]: unknown; // forward-compat with extra fields
}

export interface LudusRangeListResponse {
  ranges: LudusRange[];
}

export interface LudusRangeConfigResponse {
  range_number: number;
  config_yaml: string;
}

// Ludus Snapshots
export interface LudusSnapshot {
  name: string;
  description?: string;
  vmids?: number[];
  [key: string]: unknown;
}

export interface LudusSnapshotListResponse {
  snapshots: LudusSnapshot[];
}

export interface SnapshotCreateRequest {
  user_id: string;
  name: string;
  description?: string;
  include_ram?: boolean;
  vmids?: number[];
  range_id?: string;
}

export interface SnapshotRevertRequest {
  user_id: string;
  name: string;
  vmids?: number[];
  range_id?: string;
}

// Ludus Templates
export interface LudusTemplate {
  name: string;
  os?: string;
  built?: boolean;
  status?: string; // "built", "not_built", "building"
  [key: string]: unknown;
}

export interface LudusTemplateListResponse {
  templates: LudusTemplate[];
}

export interface TemplateBuildRequest {
  templates: string[];
  parallel?: number;
}

export interface LudusTemplateBuildStatus {
  template: string;
  user?: string;
  [key: string]: unknown;
}

export interface LudusTemplateBuildStatusResponse {
  status: LudusTemplateBuildStatus[];
}

// Ludus Management Actions
export interface PowerActionRequest {
  user_id: string;
  range_id?: string;
  machines?: string[];
}

export interface LudusActionResponse {
  status: string;
  detail?: string;
}

// Platform Settings
export interface PlatformSettings {
  ludus_server_url: string;
  ludus_api_key_masked: string;
  ludus_verify_tls: boolean;
  admin_email: string;
  invite_token_ttl_hours: number;
  public_base_url: string;
}

// Ludus Servers
export interface LudusServerInfo {
  name: string;
  url: string;
  api_key_masked: string;
  verify_tls: boolean;
  source: "env" | "db";
}

export interface LudusServersResponse {
  servers: LudusServerInfo[];
}

export interface LudusServerCreate {
  name: string;
  url: string;
  api_key: string;
  verify_tls: boolean;
}

export interface LudusServerUpdate {
  url?: string;
  api_key?: string;
  verify_tls?: boolean;
}

// Ludus Range Detail / VMs
export interface LudusVM {
  vmID?: number;
  name?: string;
  hostname?: string;
  powerState?: string;
  testingState?: string;
  [key: string]: unknown;
}

export interface LudusRangeDetail {
  rangeID?: string;
  rangeNumber?: number;
  vms: LudusVM[];
  [key: string]: unknown;
}

export interface LudusRangeDetailResponse {
  ranges: LudusRangeDetail[];
}

export interface LudusRangeTagsResponse {
  tags: string[];
}

export interface LudusRangeLogsResponse {
  result?: string;
  cursor?: number | string;
}

export interface LudusLogHistoryEntry {
  logID?: number;
  timestamp?: string;
  action?: string;
  status?: string;
  [key: string]: unknown;
}

export interface LudusLogHistoryResponse {
  entries: LudusLogHistoryEntry[];
}

export interface LudusLogEntryDetailResponse {
  logID?: number;
  output?: string;
  timestamp?: string;
  action?: string;
  status?: string;
  [key: string]: unknown;
}

export interface LudusTextResponse {
  content: string;
}

export interface LudusRangeUser {
  userID: string;
  name?: string;
  [key: string]: unknown;
}

export interface LudusRangeUsersResponse {
  users: LudusRangeUser[];
}

export interface LudusAccessibleRange {
  rangeID?: string;
  rangeNumber?: number;
  name?: string;
  [key: string]: unknown;
}

export interface LudusAccessibleRangesResponse {
  ranges: LudusAccessibleRange[];
}

// Ludus Testing
export interface TestingStartRequest {
  range_id?: number;
  user_id?: string;
}

export interface TestingStopRequest {
  range_id?: number;
  user_id?: string;
  force?: boolean;
}

export interface TestingAllowDenyRequest {
  range_id?: number;
  user_id?: string;
  domains?: string[];
  ips?: string[];
}

export interface TestingAllowDenyResponse {
  result?: string;
  domains?: string[];
  ips?: string[];
  [key: string]: unknown;
}

export interface TestingUpdateRequest {
  name: string;
  range_id?: number;
  user_id?: string;
}

// Ludus Groups
export interface LudusGroup {
  name: string;
  description?: string;
  [key: string]: unknown;
}

export interface LudusGroupListResponse {
  groups: LudusGroup[];
}

export interface LudusGroupUser {
  userID: string;
  name?: string;
  manager?: boolean;
  [key: string]: unknown;
}

export interface LudusGroupUsersResponse {
  users: LudusGroupUser[];
}

export interface LudusGroupRangesResponse {
  ranges: LudusAccessibleRange[];
}

// Ludus Ansible
export interface LudusSubscriptionRole {
  name: string;
  description?: string;
  [key: string]: unknown;
}

export interface LudusSubscriptionRolesResponse {
  roles: LudusSubscriptionRole[];
}

export interface LudusRoleVar {
  name?: string;
  default?: string;
  description?: string;
  [key: string]: unknown;
}

export interface LudusRoleVarsResponse {
  vars: LudusRoleVar[];
}

export interface LudusInstalledRole {
  name: string;
  version?: string;
  scope?: string;
  type?: string;
  [key: string]: unknown;
}

export interface LudusInstalledRolesResponse {
  roles: LudusInstalledRole[];
}

// Ludus Users
export interface LudusUser {
  userID: string;
  name?: string;
  dateCreated?: string;
  proxmoxUsername?: string;
  rangeNumber?: number;
  userNumber?: number;
  [key: string]: unknown;
}

export interface LudusUserListResponse {
  users: LudusUser[];
}

export interface UserCreateRequest {
  user_id: string;
  name: string;
  email: string;
}

export interface UserCreateResponse {
  userID: string;
  apiKey?: string;
  [key: string]: unknown;
}

// Events (audit log)
export interface EventRead {
  id: number;
  session_id: number | null;
  student_id: number | null;
  action: string;
  details_json: Record<string, unknown> | null;
  created_at: string;
}
