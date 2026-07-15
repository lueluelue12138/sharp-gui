import { apiDelete, apiGet } from './client';
import type {
  WorkspaceCacheClearResponse,
  WorkspaceStorageStatsResponse,
} from '@/types';

export async function fetchWorkspaceStorageStats(
  refresh = false,
): Promise<WorkspaceStorageStatsResponse> {
  return apiGet<WorkspaceStorageStatsResponse>(
    `/api/workspace-storage${refresh ? '?refresh=1' : ''}`,
    { cache: 'no-store' },
  );
}

export async function clearWorkspaceCache(): Promise<WorkspaceCacheClearResponse> {
  return apiDelete<WorkspaceCacheClearResponse>('/api/workspace-storage');
}
