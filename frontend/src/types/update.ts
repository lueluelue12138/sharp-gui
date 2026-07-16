export type UpdateChannel = 'stable' | 'latest';

export type UpdateAction = 'check' | 'apply' | 'rollback';

export type UpdateRelation =
  | 'ahead'
  | 'behind'
  | 'same'
  | 'current'
  | 'upgrade'
  | 'downgrade'
  | 'diverged'
  | 'unknown';

export type UpdateInstallationKind =
  | 'source'
  | 'release'
  | 'portable'
  | 'legacy-release'
  | 'legacy-portable'
  | 'unknown';

export type UpdateTimestamp = number | string | null;

export interface UpdateInstalledIdentity {
  base_version: string | null;
  commit: string | null;
  short_commit: string | null;
  commits_ahead: number | null;
  display_version: string;
  channel: UpdateChannel | 'unknown' | null;
  installation_kind: UpdateInstallationKind | string;
  managed?: boolean;
  dirty: boolean;
  branch: string | null;
}

export interface UpdateCapabilities {
  can_check: boolean;
  can_apply: boolean;
  can_rollback: boolean;
  reason_code: string | null;
  owner_required?: boolean;
}

export interface UpdateCandidate {
  channel: UpdateChannel;
  target_sha: string;
  short_sha: string;
  base_version: string | null;
  commits_ahead: number | null;
  display_version: string;
  relation: UpdateRelation | string;
  update_available: boolean;
  compatible: boolean;
  compatibility_code: string | null;
  checked_at: UpdateTimestamp;
  cached: boolean;
  target_token?: string | null;
  expires_at?: UpdateTimestamp;
  release_url?: string | null;
  check_error_code?: string | null;
}

export interface UpdateOperation {
  id: string;
  action: UpdateAction | string;
  phase: string;
  progress: number | null;
  channel: UpdateChannel | null;
  target_sha: string | null;
  short_target_sha: string | null;
  previous_sha: string | null;
  short_previous_sha?: string | null;
  error_code: string | null;
  rolled_back?: boolean;
  rollback_available: boolean;
  started_at?: UpdateTimestamp;
  updated_at: UpdateTimestamp;
  completed_at?: UpdateTimestamp;
}

export interface UpdateStatusResponse {
  server_instance_id: string;
  is_owner: boolean;
  current: UpdateInstalledIdentity;
  capabilities: UpdateCapabilities;
  channels: {
    stable?: UpdateCandidate | null;
    latest?: UpdateCandidate | null;
  };
  operation?: UpdateOperation | null;
  checked_at: UpdateTimestamp;
  last_check_error_code?: string | null;
  success?: boolean;
  message?: string;
}

export interface UpdateCheckRequest {
  channel: UpdateChannel;
}

export interface UpdateApplyRequest {
  channel: UpdateChannel;
  target_token: string;
}
