import { useCallback, useEffect } from 'react';
import { useShallow } from 'zustand/react/shallow';

import { fetchModelAsset, fetchModelSourceLinks, fetchSourceModels, fetchPhotoAlbums } from '@/api';
import { useAppStore } from '@/store';
import type { ModelAsset, ModelSourceLink, PhotoItem } from '@/types';
import { resolveModelAssetSource } from '@/utils';

export function useModelSourceLinks() {
  const { items, preview, revision, active, canRead } = useAppStore(useShallow((state) => ({
    items: state.photoItems, preview: state.previewPhoto, revision: state.modelSourceRevision,
    active: state.activeView === 'photos', canRead: state.isAuthenticated || state.isOwnerAccess,
  })));
  const ids = [...new Set([...items.map((item) => item.id), ...(preview ? [preview.id] : [])])].join('|');
  useEffect(() => {
    if ((!active && !preview) || !canRead) return;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    const refresh = async () => {
      try {
        const mediaIds = ids ? ids.split('|') : [];
        const links: Record<string, ModelSourceLink> = {};
        let repairing = false;
        let serverRevision: string | null = null;
        // Do not restrict source links to the model library's current page or filters.
        for (let start = 0; start < Math.max(1, mediaIds.length); start += 200) {
          const response = await fetchModelSourceLinks(mediaIds.slice(start, start + 200));
          Object.assign(links, response.links);
          repairing ||= response.repairing;
          serverRevision = response.revision;
        }
        if (disposed) return;
        const changed = useAppStore.getState().modelSourceServerRevision !== serverRevision;
        useAppStore.setState({ modelSourceLinks: links, modelSourceRepairing: repairing, modelSourceServerRevision: serverRevision });
        if (changed) {
          const albums = await fetchPhotoAlbums();
          if (!disposed) useAppStore.getState().setPhotoAlbums(albums.albums);
        }
        if (disposed) return;
        timer = setTimeout(() => void refresh(), repairing ? 1500 : 10000);
      } catch {
        if (!disposed) timer = setTimeout(() => void refresh(), 10000);
      }
    };
    void refresh();
    return () => { disposed = true; clearTimeout(timer); };
  }, [active, canRead, ids, preview, revision]);
}

export async function openLinkedModel(asset: ModelAsset) {
  const before = useAppStore.getState();
  const context = [before.activeView, before.currentPhotoAlbumId, before.previewPhoto?.id, before.sourceModelTarget?.id];
  const fresh = await fetchModelAsset(asset.id);
  const state = useAppStore.getState();
  const currentContext = [state.activeView, state.currentPhotoAlbumId, state.previewPhoto?.id, state.sourceModelTarget?.id];
  if (context.some((value, index) => value !== currentContext[index])) return;
  const source = resolveModelAssetSource(fresh, state.localModelFormat ?? state.serverModelFormat);
  if (!fresh.available || !source.url || !source.format) throw new Error('modelAssetOpenUnavailable');
  state.setCurrentModel({ id: fresh.id, url: source.url, format: source.format, size: source.size,
    source: fresh.is_imported ? 'model-asset-imported' : 'model-asset-generated',
    sourceMediaType: source.sourceMediaType, viewerOrientation: source.viewerOrientation,
    viewerCamera: source.viewerCamera, viewerTransform: source.viewerTransform });
  state.setActiveView('models');
  useAppStore.setState({ previewPhoto: null, sourceModelTarget: null, modelReturnToPhotos: true });
}

export function useSourceModelsEntry() {
  return useCallback(async (item: PhotoItem, allModels = false) => {
    const before = useAppStore.getState();
    const context = [before.activeView, before.currentPhotoAlbumId, before.previewPhoto?.id, before.sourceModelTarget?.id];
    const matchesContext = () => {
      const state = useAppStore.getState();
      const current = [state.activeView, state.currentPhotoAlbumId, state.previewPhoto?.id, state.sourceModelTarget?.id];
      return context.every((value, index) => value === current[index]);
    };
    try {
      const response = await fetchSourceModels(item.id);
      // A changed album/preview must not cause a late request to open an unrelated model.
      const state = useAppStore.getState();
      if (!matchesContext() || state.activeView !== 'photos' || state.currentPhotoAlbumId !== item.album_id) return;
      const available = response.models.filter((asset) => asset.available);
      const preferred = available.find((asset) => asset.id === response.default_model_id);
      if (!allModels && (preferred || available.length === 1)) {
        await openLinkedModel(preferred ?? available[0]);
      } else {
        state.setSourceModelTarget(item);
      }
    } catch {
      const state = useAppStore.getState();
      if (matchesContext() && state.activeView === 'photos' && state.currentPhotoAlbumId === item.album_id) {
        state.setSourceModelTarget(item);
      }
    }
  }, []);
}
