export interface WorkspaceStorageBucket {
  files: number;
  bytes: number;
}

export interface WorkspaceClearableCache {
  gallery_indexes: WorkspaceStorageBucket;
  photo_thumbnails: WorkspaceStorageBucket;
  video_posters: WorkspaceStorageBucket;
  model_previews: WorkspaceStorageBucket;
  temporary_downloads: WorkspaceStorageBucket;
  other: WorkspaceStorageBucket;
  total: WorkspaceStorageBucket;
}

export interface WorkspaceProtectedStorage {
  source_images: WorkspaceStorageBucket;
  generated_models: WorkspaceStorageBucket;
  imported_models: WorkspaceStorageBucket;
  asset_library: WorkspaceStorageBucket;
  asset_covers: WorkspaceStorageBucket;
  video_uploads: WorkspaceStorageBucket;
  active_downloads: WorkspaceStorageBucket;
  total: WorkspaceStorageBucket;
}

export interface WorkspaceStorageSnapshot {
  schema_version: number;
  computed_at: string;
  duration_ms: number;
  clearable_cache: WorkspaceClearableCache;
  protected_storage: WorkspaceProtectedStorage;
  managed_total: WorkspaceStorageBucket;
  scan: {
    incomplete: boolean;
    skipped_entries: number;
    symlinks_skipped: number;
  };
}

export interface WorkspaceStorageStatsResponse {
  success: boolean;
  status: 'checking' | 'ready' | 'error';
  refreshing: boolean;
  stale: boolean;
  retry_after_ms: number | null;
  snapshot: WorkspaceStorageSnapshot | null;
  error?: string;
}

export interface WorkspaceCacheClearResponse {
  success: boolean;
  removed: WorkspaceStorageBucket;
  stats: WorkspaceStorageStatsResponse;
  error?: string;
}
