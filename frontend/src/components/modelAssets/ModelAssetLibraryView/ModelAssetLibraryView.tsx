import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import type { DragEvent } from 'react';

import { useTranslation } from 'react-i18next';
import { useShallow } from 'zustand/react/shallow';

import {
  ApiError,
  deleteModelAsset,
  downloadModelAsset,
  fetchGallery,
  fetchModelAsset,
  fetchModelAssets,
  refreshModelAssetCover,
  updateModelAssetProfile,
  uploadModelAssetCover,
} from '@/api';
import { CloseIcon, CloudUploadIcon } from '@/components/common/Icons';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { ModelAssetDetailsPanel } from '@/components/modelAssets/ModelAssetDetailsPanel';
import { ModelAssetGrid } from '@/components/modelAssets/ModelAssetGrid';
import { ModelAssetToolbar } from '@/components/modelAssets/ModelAssetToolbar';
import type { ModelAssetToolbarMode } from '@/components/modelAssets/ModelAssetToolbar';
import { useModelAssetCoverQueue } from '@/hooks/useModelAssetCoverQueue';
import { useAppStore } from '@/store';
import { resolveModelAssetSource } from '@/utils';
import type {
  GalleryItem,
  ModelAsset,
  ModelAssetDensity,
  ModelAssetFormatFilter,
  ModelAssetProfileInput,
  ModelAssetSort,
  ModelAssetSourceFilter,
} from '@/types';

import styles from './ModelAssetLibraryView.module.css';

const MOBILE_TOOLBAR_BREAKPOINT = 1180;
const MOBILE_TOOLBAR_EXPAND_SCROLL_TOP = 1;
const MOBILE_TOOLBAR_COMPACT_SCROLL_TOP = 128;
const MODEL_ASSET_LOAD_MORE_REMAINING_PX = 700;

interface ModelAssetLibraryViewProps {
  canImportAssets: boolean;
  onImportBlocked: () => void;
  onImportFiles: (files: File[]) => void;
}

function getErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.data?.error ?? error.message;
  }
  return error instanceof Error ? error.message : 'Unknown error';
}

export function ModelAssetLibraryView({
  canImportAssets,
  onImportBlocked,
  onImportFiles,
}: ModelAssetLibraryViewProps) {
  const { t } = useTranslation();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const gridScrollRef = useRef<HTMLDivElement | null>(null);
  const workbenchRef = useRef<HTMLDivElement | null>(null);
  const toolbarModeRef = useRef<ModelAssetToolbarMode>('expanded');
  const scrollFrameRef = useRef<number | null>(null);
  const scrollSaveFrameRef = useRef<number | null>(null);
  const resizeFrameRef = useRef<number | null>(null);
  const dragDepthRef = useRef(0);
  const lastScrollTopRef = useRef(useAppStore.getState().modelAssetScrollTop);
  const restoredScrollKeyRef = useRef<string | null>(null);
  const assetScrollStateRef = useRef<{
    isLoading: boolean;
    loadAssets: (cursor: string | null, append: boolean) => void;
    nextCursor: string | null;
  } | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<ModelAsset | null>(null);
  const [toolbarMode, setToolbarMode] = useState<ModelAssetToolbarMode>('expanded');
  const [openCardsDirectly, setOpenCardsDirectly] = useState(true);
  const [mobileDetailsOpen, setMobileDetailsOpen] = useState(false);
  const [dropActive, setDropActive] = useState(false);
  const {
    modelAssets,
    modelAssetTotal,
    modelAssetNextCursor,
    modelAssetCounts,
    modelAssetAvailableTags,
    modelAssetSource,
    modelAssetFormat,
    modelAssetTag,
    modelAssetSort,
    modelAssetDensity,
    modelAssetBatchSize,
    modelAssetCacheReady,
    modelAssetCacheGeneration,
    selectedModelAssetId,
    modelAssetSelectionMode,
    selectedModelAssetIds,
    modelAssetLoading,
    modelAssetImporting,
    modelAssetEditing,
    modelAssetError,
    preferredModelFormat,
    setModelAssets,
    setModelAssetLoading,
    setModelAssetError,
    setModelAssetFilters,
    setModelAssetDensity,
    setModelAssetScrollTop,
    setSelectedModelAsset,
    upsertModelAssets,
    removeModelAsset,
    setModelAssetSelectionMode,
    toggleSelectedModelAsset,
    setModelAssetEditing,
    setCurrentModel,
    setPreviewImage,
    setGalleryItems,
  } = useAppStore(
    useShallow((state) => ({
      modelAssets: state.modelAssets,
      modelAssetTotal: state.modelAssetTotal,
      modelAssetNextCursor: state.modelAssetNextCursor,
      modelAssetCounts: state.modelAssetCounts,
      modelAssetAvailableTags: state.modelAssetAvailableTags,
      modelAssetSource: state.modelAssetSource,
      modelAssetFormat: state.modelAssetFormat,
      modelAssetTag: state.modelAssetTag,
      modelAssetSort: state.modelAssetSort,
      modelAssetDensity: state.modelAssetDensity,
      modelAssetBatchSize: state.modelAssetBatchSize,
      modelAssetCacheReady: state.modelAssetCacheReady,
      modelAssetCacheGeneration: state.modelAssetCacheGeneration,
      selectedModelAssetId: state.selectedModelAssetId,
      modelAssetSelectionMode: state.modelAssetSelectionMode,
      selectedModelAssetIds: state.selectedModelAssetIds,
      modelAssetLoading: state.modelAssetLoading,
      modelAssetImporting: state.modelAssetImporting,
      modelAssetEditing: state.modelAssetEditing,
      modelAssetError: state.modelAssetError,
      preferredModelFormat: state.localModelFormat ?? state.serverModelFormat,
      setModelAssets: state.setModelAssets,
      setModelAssetLoading: state.setModelAssetLoading,
      setModelAssetError: state.setModelAssetError,
      setModelAssetFilters: state.setModelAssetFilters,
      setModelAssetDensity: state.setModelAssetDensity,
      setModelAssetScrollTop: state.setModelAssetScrollTop,
      setSelectedModelAsset: state.setSelectedModelAsset,
      upsertModelAssets: state.upsertModelAssets,
      removeModelAsset: state.removeModelAsset,
      setModelAssetSelectionMode: state.setModelAssetSelectionMode,
      toggleSelectedModelAsset: state.toggleSelectedModelAsset,
      setModelAssetEditing: state.setModelAssetEditing,
      setCurrentModel: state.setCurrentModel,
      setPreviewImage: state.setPreviewImage,
      setGalleryItems: state.setGalleryItems,
    })),
  );

  const explicitlySelectedAsset = useMemo(
    () => (selectedModelAssetId ? modelAssets.find((asset) => asset.id === selectedModelAssetId) ?? null : null),
    [modelAssets, selectedModelAssetId],
  );
  const selectedAsset = explicitlySelectedAsset ?? modelAssets[0] ?? null;

  const updateToolbarMode = useCallback((nextMode: ModelAssetToolbarMode) => {
    if (toolbarModeRef.current === nextMode) {
      return;
    }
    toolbarModeRef.current = nextMode;
    setToolbarMode(nextMode);
  }, []);

  const maybeLoadMoreAssets = useCallback((el: HTMLElement) => {
    const scrollState = assetScrollStateRef.current;
    if (!scrollState || !scrollState.nextCursor || scrollState.isLoading) {
      return;
    }

    const remaining = el.scrollHeight - el.scrollTop - el.clientHeight;
    if (remaining < MODEL_ASSET_LOAD_MORE_REMAINING_PX) {
      scrollState.isLoading = true;
      scrollState.loadAssets(scrollState.nextCursor, true);
    }
  }, []);

  const getAssetScrollElement = useCallback(() => (
    window.innerWidth > MOBILE_TOOLBAR_BREAKPOINT
      ? gridScrollRef.current
      : workbenchRef.current
  ), []);

  const saveScrollPosition = useCallback((scrollTop: number) => {
    lastScrollTopRef.current = scrollTop;
    if (scrollSaveFrameRef.current !== null) {
      return;
    }
    scrollSaveFrameRef.current = window.requestAnimationFrame(() => {
      scrollSaveFrameRef.current = null;
      setModelAssetScrollTop(lastScrollTopRef.current);
    });
  }, [setModelAssetScrollTop]);

  const scrollContextKey = [
    modelAssetSource,
    modelAssetFormat,
    modelAssetTag ?? '',
    modelAssetSort,
    modelAssetDensity,
  ].join('|');

  useEffect(() => {
    const handleResize = () => {
      if (resizeFrameRef.current !== null) {
        return;
      }

      resizeFrameRef.current = window.requestAnimationFrame(() => {
        resizeFrameRef.current = null;
        if (window.innerWidth > MOBILE_TOOLBAR_BREAKPOINT) {
          updateToolbarMode('expanded');
        }
        const scrollElement = getAssetScrollElement();
        if (scrollElement) {
          maybeLoadMoreAssets(scrollElement);
        }
      });
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [getAssetScrollElement, maybeLoadMoreAssets, updateToolbarMode]);

  useEffect(() => {
    const pointerQuery = window.matchMedia('(hover: hover) and (pointer: fine)');
    const updatePointerMode = () => {
      const canOpenDirectly = pointerQuery.matches;
      setOpenCardsDirectly(canOpenDirectly);
      if (canOpenDirectly) {
        setMobileDetailsOpen(false);
      }
    };

    updatePointerMode();
    pointerQuery.addEventListener('change', updatePointerMode);
    return () => pointerQuery.removeEventListener('change', updatePointerMode);
  }, []);

  useEffect(() => () => {
    if (scrollFrameRef.current !== null) {
      window.cancelAnimationFrame(scrollFrameRef.current);
    }
    if (resizeFrameRef.current !== null) {
      window.cancelAnimationFrame(resizeFrameRef.current);
    }
    if (scrollSaveFrameRef.current !== null) {
      window.cancelAnimationFrame(scrollSaveFrameRef.current);
    }
    setModelAssetScrollTop(lastScrollTopRef.current);
  }, [setModelAssetScrollTop]);

  const handleWorkbenchScroll = useCallback(() => {
    if (scrollFrameRef.current !== null) {
      return;
    }

    scrollFrameRef.current = window.requestAnimationFrame(() => {
      scrollFrameRef.current = null;
      const el = workbenchRef.current;
      if (!el || window.innerWidth > MOBILE_TOOLBAR_BREAKPOINT) {
        return;
      }

      const scrollTop = el.scrollTop;
      saveScrollPosition(scrollTop);
      if (scrollTop <= MOBILE_TOOLBAR_EXPAND_SCROLL_TOP) {
        updateToolbarMode('expanded');
      } else if (toolbarModeRef.current === 'expanded' && scrollTop >= MOBILE_TOOLBAR_COMPACT_SCROLL_TOP) {
        updateToolbarMode('compact');
      }

      maybeLoadMoreAssets(el);
    });
  }, [maybeLoadMoreAssets, saveScrollPosition, updateToolbarMode]);

  useEffect(() => {
    const el = workbenchRef.current;
    if (!el) {
      return;
    }

    el.addEventListener('scroll', handleWorkbenchScroll, { passive: true });
    return () => el.removeEventListener('scroll', handleWorkbenchScroll);
  }, [handleWorkbenchScroll]);

  const handleExpandToolbar = useCallback(() => {
    updateToolbarMode('expanded');
  }, [updateToolbarMode]);

  const handleGeneratedCover = useCallback((asset: ModelAsset) => {
    upsertModelAssets([asset]);
  }, [upsertModelAssets]);

  useModelAssetCoverQueue(modelAssets, handleGeneratedCover, modelAssetCacheGeneration);

  const loadAssets = useCallback(async (cursor: string | null = null, append = false) => {
    const requestGeneration = modelAssetCacheGeneration;
    try {
      if (assetScrollStateRef.current) {
        assetScrollStateRef.current.isLoading = true;
      }
      setModelAssetLoading(true);
      const response = await fetchModelAssets({
        source: modelAssetSource,
        format: modelAssetFormat,
        tag: modelAssetTag,
        sort: modelAssetSort,
        cursor,
        limit: modelAssetBatchSize,
      });
      if (useAppStore.getState().modelAssetCacheGeneration !== requestGeneration) {
        return;
      }
      setModelAssets(response, append);
    } catch (error) {
      if (useAppStore.getState().modelAssetCacheGeneration !== requestGeneration) {
        return;
      }
      setModelAssetError(getErrorMessage(error));
    }
  }, [
    modelAssetFormat,
    modelAssetBatchSize,
    modelAssetCacheGeneration,
    modelAssetSort,
    modelAssetSource,
    modelAssetTag,
    setModelAssetError,
    setModelAssetLoading,
    setModelAssets,
  ]);

  useEffect(() => {
    assetScrollStateRef.current = {
      isLoading: modelAssetLoading,
      loadAssets: (cursor, append) => {
        void loadAssets(cursor, append);
      },
      nextCursor: modelAssetNextCursor,
    };
  }, [loadAssets, modelAssetLoading, modelAssetNextCursor]);

  useEffect(() => {
    if (modelAssetCacheReady || modelAssetLoading) {
      return;
    }
    void loadAssets(null, false);
  }, [loadAssets, modelAssetCacheReady, modelAssetLoading]);

  useLayoutEffect(() => {
    if (restoredScrollKeyRef.current === scrollContextKey) {
      return;
    }
    const scrollElement = getAssetScrollElement();
    if (!scrollElement) {
      return;
    }
    const savedScrollTop = useAppStore.getState().modelAssetScrollTop;
    scrollElement.scrollTop = savedScrollTop;
    lastScrollTopRef.current = scrollElement.scrollTop;
    restoredScrollKeyRef.current = scrollContextKey;
  }, [
    getAssetScrollElement,
    modelAssets.length,
    modelAssetLoading,
    scrollContextKey,
  ]);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      const scrollElement = getAssetScrollElement();
      if (scrollElement) {
        maybeLoadMoreAssets(scrollElement);
      }
    });
    return () => window.cancelAnimationFrame(frame);
  }, [
    getAssetScrollElement,
    maybeLoadMoreAssets,
    modelAssets.length,
    modelAssetDensity,
    modelAssetLoading,
    modelAssetNextCursor,
  ]);

  const handleImportClick = useCallback(() => {
    if (!canImportAssets) {
      onImportBlocked();
      return;
    }
    fileInputRef.current?.click();
  }, [canImportAssets, onImportBlocked]);

  const loadAssetDetails = useCallback(async (assetId: string) => {
    try {
      const asset = await fetchModelAsset(assetId);
      upsertModelAssets([asset]);
    } catch (error) {
      setModelAssetError(getErrorMessage(error));
    }
  }, [setModelAssetError, upsertModelAssets]);

  const handleSelectAsset = useCallback((asset: ModelAsset) => {
    setSelectedModelAsset(asset.id);
    if (!openCardsDirectly) {
      updateToolbarMode('compact');
      setMobileDetailsOpen(true);
      void loadAssetDetails(asset.id);
    }
  }, [loadAssetDetails, openCardsDirectly, setSelectedModelAsset, updateToolbarMode]);

  const handleShowDetails = useCallback((asset: ModelAsset) => {
    setSelectedModelAsset(asset.id);
    if (!openCardsDirectly) {
      updateToolbarMode('compact');
      setMobileDetailsOpen(true);
    }
    void loadAssetDetails(asset.id);
  }, [loadAssetDetails, openCardsDirectly, setSelectedModelAsset, updateToolbarMode]);

  const handleImportFiles = useCallback((files: FileList | File[] | null) => {
    if (!files || files.length === 0) {
      return;
    }
    if (!canImportAssets) {
      onImportBlocked();
      return;
    }

    setNotice(null);
    onImportFiles(Array.from(files));
  }, [
    canImportAssets,
    onImportBlocked,
    onImportFiles,
  ]);

  const handleLibraryDragEnter = useCallback((event: DragEvent<HTMLElement>) => {
    if (!event.dataTransfer.types.includes('Files')) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    dragDepthRef.current += 1;
    setDropActive(true);
  }, []);

  const handleLibraryDragOver = useCallback((event: DragEvent<HTMLElement>) => {
    if (!event.dataTransfer.types.includes('Files')) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    event.dataTransfer.dropEffect = canImportAssets ? 'copy' : 'none';
  }, [canImportAssets]);

  const handleLibraryDragLeave = useCallback((event: DragEvent<HTMLElement>) => {
    event.preventDefault();
    event.stopPropagation();
    dragDepthRef.current = Math.max(0, dragDepthRef.current - 1);
    if (dragDepthRef.current === 0) {
      setDropActive(false);
    }
  }, []);

  const handleLibraryDrop = useCallback((event: DragEvent<HTMLElement>) => {
    event.preventDefault();
    event.stopPropagation();
    dragDepthRef.current = 0;
    setDropActive(false);
    handleImportFiles(event.dataTransfer.files);
  }, [handleImportFiles]);

  useEffect(() => {
    if (!dropActive) {
      return;
    }
    const resetDropState = () => {
      dragDepthRef.current = 0;
      setDropActive(false);
    };
    window.addEventListener('dragend', resetDropState);
    window.addEventListener('drop', resetDropState);
    return () => {
      window.removeEventListener('dragend', resetDropState);
      window.removeEventListener('drop', resetDropState);
    };
  }, [dropActive]);

  const handleOpen = useCallback((asset: ModelAsset) => {
    const modelSource = resolveModelAssetSource(asset, preferredModelFormat);
    if (!modelSource.url || !modelSource.format) {
      setModelAssetError(t('modelAssetOpenUnavailable'));
      return;
    }
    setCurrentModel(
      asset.id,
      modelSource.url,
      modelSource.format,
      modelSource.size,
      asset.is_imported ? 'model-asset-imported' : 'model-asset-generated',
    );
  }, [preferredModelFormat, setCurrentModel, setModelAssetError, t]);

  const handlePreview = useCallback((asset: ModelAsset) => {
    if (!asset.image_url && !asset.source_video_url) {
      return;
    }
    const modelSource = resolveModelAssetSource(asset, preferredModelFormat);
    setPreviewImage({
      id: asset.id,
      name: asset.name,
      model_url: modelSource.url ?? asset.default_open_url ?? '',
      image_url: asset.image_url ?? null,
      thumb_url: asset.thumb_url ?? null,
      source_media_type: asset.source_media_type,
      source_media_id: asset.source_media_id,
      source_name: asset.source_name,
      source_video_url: asset.source_video_url,
    } as GalleryItem);
  }, [preferredModelFormat, setPreviewImage]);

  const handleDownload = useCallback((asset: ModelAsset) => {
    const modelSource = resolveModelAssetSource(asset, preferredModelFormat);
    downloadModelAsset(asset.id, modelSource.format ?? asset.primary_format);
  }, [preferredModelFormat]);

  const handleDelete = useCallback((asset: ModelAsset) => {
    setDeleteTarget(asset);
  }, []);

  const confirmDelete = useCallback(async () => {
    if (!deleteTarget) {
      return;
    }
    try {
      await deleteModelAsset(deleteTarget.id);
      removeModelAsset(deleteTarget.id);
      if (deleteTarget.id === selectedModelAssetId) {
        setMobileDetailsOpen(false);
      }
      setDeleteTarget(null);
      if (deleteTarget.is_generated) {
        const gallery = await fetchGallery();
        setGalleryItems(gallery);
      }
      await loadAssets(null, false);
    } catch (error) {
      setModelAssetError(getErrorMessage(error));
    }
  }, [
    deleteTarget,
    loadAssets,
    removeModelAsset,
    selectedModelAssetId,
    setGalleryItems,
    setModelAssetError,
  ]);

  const handleSaveProfile = useCallback(async (asset: ModelAsset, profile: ModelAssetProfileInput) => {
    try {
      setModelAssetEditing(true);
      const updated = await updateModelAssetProfile(asset.id, profile);
      upsertModelAssets([updated]);
      setSelectedModelAsset(updated.id);
      setNotice(t('modelAssetSaved'));
    } catch (error) {
      setModelAssetError(getErrorMessage(error));
    } finally {
      setModelAssetEditing(false);
    }
  }, [setModelAssetEditing, setModelAssetError, setSelectedModelAsset, t, upsertModelAssets]);

  const handleUploadCover = useCallback(async (asset: ModelAsset, file: File) => {
    try {
      setModelAssetEditing(true);
      const updated = await uploadModelAssetCover(asset.id, file);
      upsertModelAssets([updated]);
      setNotice(t('modelAssetCoverSaved'));
    } catch (error) {
      setModelAssetError(getErrorMessage(error));
    } finally {
      setModelAssetEditing(false);
    }
  }, [setModelAssetEditing, setModelAssetError, t, upsertModelAssets]);

  const handleRefreshCover = useCallback(async (asset: ModelAsset) => {
    try {
      setModelAssetEditing(true);
      const updated = await refreshModelAssetCover(asset.id);
      upsertModelAssets([updated]);
      setNotice(t('modelAssetSystemCoverQueued'));
    } catch (error) {
      setModelAssetError(getErrorMessage(error));
    } finally {
      setModelAssetEditing(false);
    }
  }, [setModelAssetEditing, setModelAssetError, t, upsertModelAssets]);

  const handleSourceChange = useCallback((source: ModelAssetSourceFilter) => {
    setMobileDetailsOpen(false);
    setModelAssetFilters({ source });
  }, [setModelAssetFilters]);

  const handleFormatChange = useCallback((format: ModelAssetFormatFilter) => {
    setMobileDetailsOpen(false);
    setModelAssetFilters({ format });
  }, [setModelAssetFilters]);

  const handleTagChange = useCallback((tag: string | null) => {
    setMobileDetailsOpen(false);
    setModelAssetFilters({ tag });
  }, [setModelAssetFilters]);

  const handleSortChange = useCallback((sort: ModelAssetSort) => {
    setMobileDetailsOpen(false);
    setModelAssetFilters({ sort });
  }, [setModelAssetFilters]);

  const handleDensityChange = useCallback((density: ModelAssetDensity) => {
    setModelAssetDensity(density);
  }, [setModelAssetDensity]);

  const handleGridScroll = useCallback((event: React.UIEvent<HTMLDivElement>) => {
    saveScrollPosition(event.currentTarget.scrollTop);
    maybeLoadMoreAssets(event.currentTarget);
  }, [maybeLoadMoreAssets, saveScrollPosition]);

  return (
    <section
      className={styles.library}
      aria-label={t('modelAssetLibraryTitle')}
      onDragEnter={handleLibraryDragEnter}
      onDragOver={handleLibraryDragOver}
      onDragLeave={handleLibraryDragLeave}
      onDrop={handleLibraryDrop}
    >
      <input
        ref={fileInputRef}
        type="file"
        accept=".ply,.spz,.splat,.rad"
        multiple
        hidden
        onChange={(event) => {
          handleImportFiles(event.target.files);
          event.target.value = '';
        }}
      />

      {dropActive ? (
        <div className={styles.dropOverlay} aria-hidden="true">
          <div className={styles.dropCard}>
            <span className={styles.dropIcon}>
              <CloudUploadIcon width={30} height={30} />
            </span>
            <strong>{t('modelAssetDropImportTitle')}</strong>
            <span>{t('modelAssetDropImportHint')}</span>
          </div>
        </div>
      ) : null}

      <ModelAssetToolbar
        total={modelAssetTotal}
        counts={modelAssetCounts}
        source={modelAssetSource}
        format={modelAssetFormat}
        tag={modelAssetTag}
        tags={modelAssetAvailableTags}
        sort={modelAssetSort}
        density={modelAssetDensity}
        selectedAsset={selectedAsset}
        selectedCount={selectedModelAssetIds.length}
        selectionMode={modelAssetSelectionMode}
        loading={modelAssetLoading}
        importing={modelAssetImporting}
        mode={toolbarMode}
        onSourceChange={handleSourceChange}
        onFormatChange={handleFormatChange}
        onTagChange={handleTagChange}
        onSortChange={handleSortChange}
        onDensityChange={handleDensityChange}
        onRefresh={() => void loadAssets(null, false)}
        onImportClick={handleImportClick}
        onToggleSelectionMode={() => setModelAssetSelectionMode(!modelAssetSelectionMode)}
        onOpenSelected={() => selectedAsset && handleOpen(selectedAsset)}
        onExpandRequest={handleExpandToolbar}
      />

      {modelAssetError || notice ? (
        <div className={[styles.notice, modelAssetError ? styles.noticeError : ''].join(' ')} role="status">
          <span>{modelAssetError ?? notice}</span>
          <button
            type="button"
            aria-label={t('close')}
            data-tooltip={t('close')}
            onClick={() => {
              setNotice(null);
              setModelAssetError(null);
            }}
          >
            <CloseIcon width={13} height={13} />
          </button>
        </div>
      ) : null}

      <div ref={workbenchRef} className={styles.workbench}>
        <ModelAssetGrid
          assets={modelAssets}
          density={modelAssetDensity}
          loading={modelAssetLoading}
          selectedId={selectedModelAssetId}
          selectionMode={modelAssetSelectionMode}
          selectedIds={selectedModelAssetIds}
          openOnCardClick={openCardsDirectly}
          preferredFormat={preferredModelFormat}
          scrollElementRef={gridScrollRef}
          onSelect={handleSelectAsset}
          onToggleChecked={(asset) => toggleSelectedModelAsset(asset.id)}
          onOpen={handleOpen}
          onShowDetails={handleShowDetails}
          onPreview={handlePreview}
          onDownload={handleDownload}
          onDelete={handleDelete}
          onScroll={handleGridScroll}
        />

        <div
          className={[
            styles.detailsSlot,
            mobileDetailsOpen && explicitlySelectedAsset ? styles.detailsSlotOpen : '',
          ].filter(Boolean).join(' ')}
        >
          <ModelAssetDetailsPanel
            key={selectedAsset?.id ?? 'empty-model-asset-details'}
            asset={selectedAsset}
            saving={modelAssetEditing}
            preferredFormat={preferredModelFormat}
            onOpen={handleOpen}
            onPreviewSource={handlePreview}
            onDownload={handleDownload}
            onDelete={handleDelete}
            onSaveProfile={handleSaveProfile}
            onUploadCover={handleUploadCover}
            onRefreshCover={handleRefreshCover}
            onClose={() => {
              setMobileDetailsOpen(false);
              setSelectedModelAsset(null);
            }}
          />
        </div>
      </div>

      <ConfirmDialog
        isOpen={Boolean(deleteTarget)}
        title={t('delete')}
        message={t('modelAssetDeleteConfirm')}
        confirmLabel={t('delete')}
        danger
        onConfirm={confirmDelete}
        onClose={() => setDeleteTarget(null)}
      />
    </section>
  );
}
