import { apiGet, apiPost } from './client';
import type { ModelFormat, VideoReconstructionConfig } from '@/types';

export interface SettingsData {
  workspace_folder?: string;
  model_format?: ModelFormat;
  is_local?: boolean;
  server_instance_id?: string;
  video_reconstruction?: VideoReconstructionConfig;
}

interface RestartResponse {
  success: boolean;
  server_instance_id?: string;
}

const RESTART_POLL_INTERVAL_MS = 500;
const RESTART_PROBE_TIMEOUT_MS = 2000;
const RESTART_TIMEOUT_MS = 60000;

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function normalizeWorkspacePath(path: string | undefined): string | null {
  if (!path) return null;
  return path.trim().replace(/\\/g, '/').replace(/\/+$/, '');
}

function workspaceMatches(actual: string | undefined, expected: string | undefined): boolean {
  if (!expected) return true;
  return normalizeWorkspacePath(actual) === normalizeWorkspacePath(expected);
}

/**
 * Fetch current settings
 */
export async function fetchSettings(): Promise<SettingsData> {
  return apiGet<SettingsData>('/api/settings');
}

/**
 * Save settings
 */
export async function saveSettings(
  settings: SettingsData
): Promise<{ success: boolean; needs_restart?: boolean; error?: string }> {
  return apiPost('/api/settings', settings);
}

/**
 * Request folder selection dialog (local only)
 */
export async function browseFolder(
  title: string,
  initialDir?: string
): Promise<{ success: boolean; path?: string; error?: string }> {
  return apiPost('/api/browse-folder', { title, initial_dir: initialDir });
}

/**
 * Restart server (local only)
 */
export async function restartServer(expectedWorkspaceFolder?: string): Promise<void> {
  const beforeRestart = await fetchSettings();
  const response = await apiPost<RestartResponse>('/api/restart');
  const previousInstanceId = response.server_instance_id ?? beforeRestart.server_instance_id;
  const workspaceChanged = !workspaceMatches(beforeRestart.workspace_folder, expectedWorkspaceFolder);
  const deadline = Date.now() + RESTART_TIMEOUT_MS;
  let sawDisconnect = false;

  while (Date.now() < deadline) {
    try {
      const settings = await apiGet<SettingsData>(
        `/api/settings?restart_probe=${Date.now()}`,
        { cache: 'no-store', timeout: RESTART_PROBE_TIMEOUT_MS },
      );
      const instanceChanged = previousInstanceId
        ? Boolean(settings.server_instance_id && settings.server_instance_id !== previousInstanceId)
        : sawDisconnect || workspaceChanged;

      if (instanceChanged && workspaceMatches(settings.workspace_folder, expectedWorkspaceFolder)) {
        return;
      }
    } catch {
      sawDisconnect = true;
    }

    await delay(RESTART_POLL_INTERVAL_MS);
  }

  throw new Error('Server restart timed out');
}

/**
 * Batch convert all existing PLY models to SPZ (local only)
 */
export async function convertAllToSpz(): Promise<{
  success: boolean;
  converted: number;
  skipped: number;
  failed: number;
  total: number;
}> {
  return apiPost('/api/convert-all', undefined, { timeout: 300000 });
}
