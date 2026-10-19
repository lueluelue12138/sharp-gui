export interface ConfigurationPreview {
  folder: string;
  source_revision: string;
  target_revision: string;
  workspace_folder: string;
  album_count: number;
}

export interface ConfigurationRestoreResult {
  success: boolean;
  server_instance_id: string;
}
