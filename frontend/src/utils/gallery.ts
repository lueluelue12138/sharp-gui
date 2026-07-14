import type { ViewerModelFormat } from '@/constants/spark';
import type { GalleryItem, ModelFormat } from '@/types';

export type GalleryRendererMode = 'virtualized' | 'legacy';

const galleryRendererStorageKey = 'sharp-gallery-renderer-mode';
const defaultGalleryRendererMode: GalleryRendererMode =
  import.meta.env.VITE_ENABLE_VIRTUAL_GALLERY === 'false' ? 'legacy' : 'virtualized';

export const GALLERY_LIST_PADDING = 12;
export const GALLERY_ROW_HEIGHT = 72;
export const GALLERY_VIRTUAL_OVERSCAN = 6;

function areGalleryItemsEquivalent(current: GalleryItem, next: GalleryItem): boolean {
  return (
    current.id === next.id &&
    current.name === next.name &&
    current.image_url === next.image_url &&
    current.thumb_url === next.thumb_url &&
    current.thumb_version === next.thumb_version &&
    current.model_url === next.model_url &&
    current.model_format === next.model_format &&
    current.available_formats?.join(',') === next.available_formats?.join(',') &&
    current.spz_url === next.spz_url &&
    current.size === next.size &&
    current.spz_size === next.spz_size &&
    current.source_media_type === next.source_media_type &&
    current.source_media_id === next.source_media_id &&
    current.source_name === next.source_name &&
    current.source_video_url === next.source_video_url &&
    current.created_at === next.created_at &&
    current.updated_at === next.updated_at
  );
}

export function reconcileGalleryItems(
  previousItems: GalleryItem[],
  nextItems: GalleryItem[],
): GalleryItem[] {
  if (previousItems.length === 0) {
    return nextItems;
  }

  const previousById = new Map(previousItems.map((item) => [item.id, item]));
  let changed = previousItems.length !== nextItems.length;

  const reconciledItems = nextItems.map((nextItem, index) => {
    const previousItem = previousById.get(nextItem.id);
    if (!previousItem) {
      changed = true;
      return nextItem;
    }

    if (areGalleryItemsEquivalent(previousItem, nextItem)) {
      if (!changed && previousItems[index] !== previousItem) {
        changed = true;
      }
      return previousItem;
    }

    changed = true;
    return { ...previousItem, ...nextItem };
  });

  return changed ? reconciledItems : previousItems;
}

export function getGalleryRendererMode(): GalleryRendererMode {
  if (typeof window === 'undefined') {
    return defaultGalleryRendererMode;
  }

  try {
    const storedMode = window.localStorage.getItem(galleryRendererStorageKey);
    if (storedMode === 'legacy' || storedMode === 'virtualized') {
      return storedMode;
    }
  } catch {
    // Ignore storage access issues and fall back to defaults.
  }

  return defaultGalleryRendererMode;
}

export function getGalleryThumbnailSrc(item: GalleryItem): string | null {
  if (!item.thumb_url) {
    return null;
  }

  if (item.thumb_version == null) {
    return item.thumb_url;
  }

  const separator = item.thumb_url.includes('?') ? '&' : '?';
  return `${item.thumb_url}${separator}v=${item.thumb_version}`;
}

export function getGallerySourceVideoUrl(item: GalleryItem): string | null {
  if (item.source_video_url) {
    return item.source_video_url;
  }

  if (item.source_media_type === 'video') {
    return `/api/gallery/${encodeURIComponent(item.id)}/source-video`;
  }

  return null;
}

export function getGalleryModelSource(
  item: GalleryItem,
  preferredFormat: ModelFormat,
): { url: string; format: ViewerModelFormat; size: number | null } {
  if (preferredFormat === 'spz' && item.spz_url) {
    return {
      url: item.spz_url,
      format: 'spz',
      size: item.spz_size ?? null,
    };
  }

  if (item.model_format) {
    return {
      url: item.model_url,
      format: item.model_format,
      size: item.size ?? null,
    };
  }

  const normalizedUrl = item.model_url.toLowerCase().split(/[?#]/, 1)[0];
  if (normalizedUrl.endsWith('.spz')) {
    return { url: item.model_url, format: 'spz', size: item.size ?? null };
  }
  if (normalizedUrl.endsWith('.splat')) {
    return { url: item.model_url, format: 'splat', size: item.size ?? null };
  }
  if (normalizedUrl.endsWith('.rad')) {
    return { url: item.model_url, format: 'rad', size: item.size ?? null };
  }

  return {
    url: item.model_url,
    format: 'ply',
    size: item.size ?? null,
  };
}
