import { apiGet, apiPost } from '@/api/client';
import type { ModelSourceLinksResponse, SourceModelsResponse } from '@/types';

export function fetchModelSourceLinks(mediaIds: string[]): Promise<ModelSourceLinksResponse> {
  return apiPost('/api/photo-models', { media_ids: mediaIds });
}

export function fetchSourceModels(mediaId: string): Promise<SourceModelsResponse> {
  return apiGet(`/api/photo-models/${encodeURIComponent(mediaId)}`);
}

export function setSourceDefault(sourceId: string, assetId: string | null): Promise<{ success: boolean }> {
  return apiPost(`/api/model-sources/${encodeURIComponent(sourceId)}/default`, { asset_id: assetId });
}
