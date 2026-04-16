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
  created_at: string;
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
  full_name: string;
  email: string;
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

// Events (audit log)
export interface EventRead {
  id: number;
  session_id: number | null;
  student_id: number | null;
  action: string;
  details_json: Record<string, unknown> | null;
  created_at: string;
}
