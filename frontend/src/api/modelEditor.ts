import { apiGet, apiPost } from '@/api/client';
import type { ModelAsset } from '@/types/modelAsset';
import type { ModelEditorDescriptor, ModelEditorSaveInput } from '@/types/modelEditor';

export function fetchEditorSource(id: string, signal?: AbortSignal) {
  return apiGet<ModelEditorDescriptor>(`/api/model-assets/${encodeURIComponent(id)}/editor`, {
    signal,
  });
}

export function saveEditedModel(id: string, input: ModelEditorSaveInput) {
  return apiPost<ModelAsset>(`/api/model-assets/${encodeURIComponent(id)}/editor`, input, {
    timeout: 300000,
  });
}
