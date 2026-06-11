export interface AuthStatusResponse {
  authenticated: boolean;
  is_owner: boolean;
  is_local: boolean;
  is_docker: boolean;
  owner_bootstrap_available: boolean;
  owner_authenticated: boolean;
  access_control_enabled: boolean;
  setup_required: boolean;
  setup_recommended: boolean;
  has_access_code: boolean;
  session_days: number;
  allow_localhost_bypass: boolean;
  allow_remote_generation: boolean;
  lan_bind_enabled: boolean;
}

export interface LoginRequest {
  password: string;
}

export interface OwnerBootstrapRequest {
  token: string;
}

export interface AccessCodeRequest {
  password: string;
  enabled?: boolean;
  session_days?: number;
  allow_remote_generation?: boolean;
}

export interface AuthSettingsRequest {
  enabled?: boolean;
  session_days?: number;
  allow_remote_generation?: boolean;
  allow_localhost_bypass?: boolean;
  lan_bind_enabled?: boolean;
}
