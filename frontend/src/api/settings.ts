import { apiGet, apiPost } from './client';

export interface SettingsData {
  workspace_folder?: string;
  is_local?: boolean;
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
): Promise<{ success: boolean; error?: string }> {
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
export async function restartServer(): Promise<void> {
  try {
    await apiPost('/api/restart');
  } catch {
    // Restart will close connection, this is expected
  }
}
