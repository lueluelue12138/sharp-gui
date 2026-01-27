import { apiGet, apiDelete } from './client';
import type { GalleryItem } from '@/types';

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
 */
export function downloadModel(id: string): void {
  window.location.href = `/api/download/${id}`;
}

/**
 * Export model as standalone HTML
 */
export async function exportModel(id: string): Promise<Blob> {
  const response = await fetch(`/api/export/${id}`);
  if (!response.ok) {
    throw new Error('Export failed');
  }
  return response.blob();
}
