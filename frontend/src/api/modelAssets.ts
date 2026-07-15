import {
  apiDelete,
  apiGet,
  apiPost,
  apiPostFormData,
  apiPostFormDataWithProgress,
} from './client';
import type {
  ModelAsset,
  ModelAssetFormat,
  ModelAssetImportResult,
  ModelAssetListParams,
  ModelAssetListResponse,
  ModelAssetProfileInput,
} from '@/types';

interface UploadProgress {
  loaded: number;
  total: number | null;
  percent: number;
  lengthComputable: boolean;
}

function buildModelAssetQuery(params: ModelAssetListParams = {}): string {
  const query = new URLSearchParams();
  if (params.source && params.source !== 'all') query.set('source', params.source);
  if (params.format && params.format !== 'all') query.set('format', params.format);
  if (params.tag) query.set('tag', params.tag);
  if (params.sort) query.set('sort', params.sort);
  if (params.cursor) query.set('cursor', params.cursor);
  if (params.limit) query.set('limit', String(params.limit));
  if (params.refresh) query.set('refresh', '1');
  const queryString = query.toString();
  return queryString ? `?${queryString}` : '';
}

export async function fetchModelAssets(
  params: ModelAssetListParams = {},
  options?: { signal?: AbortSignal },
): Promise<ModelAssetListResponse> {
  return apiGet<ModelAssetListResponse>(`/api/model-assets${buildModelAssetQuery(params)}`, options);
}

export async function fetchModelAsset(id: string): Promise<ModelAsset> {
  return apiGet<ModelAsset>(`/api/model-assets/${encodeURIComponent(id)}`);
}

export async function importModelAssets(
  files: File[],
  options: { onUploadProgress?: (progress: UploadProgress) => void } = {},
): Promise<ModelAssetImportResult> {
  const formData = new FormData();
  files.forEach((file) => formData.append('files', file));
  return apiPostFormDataWithProgress<ModelAssetImportResult>('/api/model-assets/import', formData, {
    timeout: 0,
    onUploadProgress: options.onUploadProgress,
  });
}

export async function updateModelAssetProfile(
  id: string,
  data: ModelAssetProfileInput,
): Promise<ModelAsset> {
  return apiPost<ModelAsset>(`/api/model-assets/${encodeURIComponent(id)}`, data);
}

export async function uploadModelAssetCover(
  id: string,
  file: File,
  kind: 'manual' | 'system' = 'manual',
): Promise<ModelAsset> {
  const formData = new FormData();
  formData.append('cover', file);
  formData.append('kind', kind);
  return apiPostFormData<ModelAsset>(`/api/model-assets/${encodeURIComponent(id)}/cover`, formData, {
    timeout: 60000,
  });
}

export async function refreshModelAssetCover(id: string): Promise<ModelAsset> {
  return apiPost<ModelAsset>(`/api/model-assets/${encodeURIComponent(id)}/cover/refresh`);
}

export async function deleteModelAsset(id: string): Promise<{ success: boolean }> {
  return apiDelete<{ success: boolean }>(`/api/model-assets/${encodeURIComponent(id)}`);
}

export function downloadModelAsset(id: string, format?: ModelAssetFormat | null): void {
  const query = format ? `?format=${encodeURIComponent(format)}` : '';
  window.location.href = `/api/model-assets/${encodeURIComponent(id)}/download${query}`;
}
