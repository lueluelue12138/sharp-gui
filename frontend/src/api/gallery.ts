import { ApiError, apiGet, apiDelete } from './client';
import type { GalleryItem, GalleryModelFormat, ModelFormat } from '@/types';

/**
 * Fetch gallery items from API
 */
export async function fetchGallery(): Promise<GalleryItem[]> {
  return apiGet<GalleryItem[]>('/api/gallery');
}

/**
 * Delete a gallery item
 */
export async function deleteGalleryItem(
  id: string
): Promise<{ success: boolean; error?: string }> {
  return apiDelete(`/api/delete/${id}`);
}

/**
 * Download model file (triggers browser download)
 * @param format - 'spz' (default) or 'ply'
 */
export function downloadModel(id: string, format: ModelFormat = 'spz'): void {
  window.location.href = `/api/download/${id}?format=${format}`;
}

/**
 * Export model as standalone HTML
 */
export interface ExportModelResult {
  blob: Blob;
  formatUsed: GalleryModelFormat;
  modelBytes: number | null;
  htmlBytes: number | null;
}

export async function exportModel(id: string, format: ModelFormat = 'spz'): Promise<ExportModelResult> {
  const response = await fetch(`/api/export/${id}?format=${format}`, { credentials: 'same-origin' });
  if (!response.ok) {
    const errorData = await response.json().catch(() => null);
    throw new ApiError(errorData?.error || 'Export failed', response.status, errorData);
  }
  const blob = await response.blob();

  const formatHeader = response.headers.get('X-Export-Format')?.toLowerCase();
  const formatUsed: GalleryModelFormat =
    formatHeader === 'ply' || formatHeader === 'splat' || formatHeader === 'rad'
      ? formatHeader
      : 'spz';

  const modelBytesHeader = response.headers.get('X-Export-Model-Bytes');
  const htmlBytesHeader = response.headers.get('X-Export-Html-Bytes');

  return {
    blob,
    formatUsed,
    modelBytes: modelBytesHeader ? Number(modelBytesHeader) : null,
    htmlBytes: htmlBytesHeader ? Number(htmlBytesHeader) : null,
  };
}
