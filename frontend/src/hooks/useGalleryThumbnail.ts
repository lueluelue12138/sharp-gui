import { useEffect, useSyncExternalStore } from 'react';

export type GalleryThumbnailState = 'missing' | 'loading' | 'ready' | 'error';

interface ThumbnailCacheEntry {
  state: GalleryThumbnailState;
  started: boolean;
  listeners: Set<() => void>;
}

const thumbnailCache = new Map<string, ThumbnailCacheEntry>();
const MAX_THUMBNAIL_CACHE_ENTRIES = 512;

function pruneThumbnailCache(): void {
  if (thumbnailCache.size <= MAX_THUMBNAIL_CACHE_ENTRIES) {
    return;
  }

  for (const [src, entry] of thumbnailCache) {
    if (entry.listeners.size === 0 && entry.state !== 'loading') {
      thumbnailCache.delete(src);
    }
    if (thumbnailCache.size <= MAX_THUMBNAIL_CACHE_ENTRIES) {
      return;
    }
  }
}

function getThumbnailEntry(src: string): ThumbnailCacheEntry {
  const existing = thumbnailCache.get(src);
  if (existing) {
    return existing;
  }

  const entry: ThumbnailCacheEntry = {
    state: 'loading',
    started: false,
    listeners: new Set(),
  };
  thumbnailCache.set(src, entry);
  return entry;
}

function notifyThumbnailListeners(entry: ThumbnailCacheEntry): void {
  for (const listener of entry.listeners) {
    listener();
  }
}

function setThumbnailState(src: string, state: GalleryThumbnailState): void {
  const entry = getThumbnailEntry(src);
  if (entry.state === state) {
    return;
  }

  entry.state = state;
  notifyThumbnailListeners(entry);
  pruneThumbnailCache();
}

function loadThumbnail(src: string): void {
  const entry = getThumbnailEntry(src);
  if (entry.started || entry.state === 'ready' || entry.state === 'error') {
    return;
  }

  entry.started = true;
  entry.state = 'loading';
  notifyThumbnailListeners(entry);

  const image = new Image();
  image.decoding = 'async';
  image.src = src;

  if (image.complete && image.naturalWidth > 0) {
    setThumbnailState(src, 'ready');
    return;
  }

  image.onload = () => {
    setThumbnailState(src, 'ready');
  };

  image.onerror = () => {
    setThumbnailState(src, 'error');
  };
}

function subscribeToThumbnail(src: string | null, listener: () => void): () => void {
  if (!src) {
    return () => undefined;
  }

  const entry = getThumbnailEntry(src);
  entry.listeners.add(listener);

  return () => {
    entry.listeners.delete(listener);
    pruneThumbnailCache();
  };
}

function getThumbnailSnapshot(src: string | null): GalleryThumbnailState {
  if (!src) {
    return 'missing';
  }

  return getThumbnailEntry(src).state;
}

export function useGalleryThumbnail(
  src: string | null,
  shouldLoad: boolean,
): GalleryThumbnailState {
  const state = useSyncExternalStore(
    (listener) => subscribeToThumbnail(src, listener),
    () => getThumbnailSnapshot(src),
    () => getThumbnailSnapshot(src),
  );

  useEffect(() => {
    if (src && shouldLoad) {
      loadThumbnail(src);
    }
  }, [src, shouldLoad]);

  return state;
}
