import { useCallback, useEffect, useRef, useState } from 'react';

import { useTranslation } from 'react-i18next';
import { useShallow } from 'zustand/react/shallow';

import { ApiError, deleteModelAsset, downloadModelAsset, fetchModelAssets } from '@/api';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { ChevronRightIcon, DeleteIcon, DownloadIcon, EyeIcon } from '@/components/common/Icons';
import { useAppStore } from '@/store';
import { formatFileSize, localizeModelAssetError, resolveModelAssetSource } from '@/utils';
import type { GalleryItem, ModelAsset } from '@/types';

import styles from './ModelAssetSidebarPanel.module.css';

const RECENT_ASSET_PAGE_SIZE = 16;
const RECENT_LOAD_MORE_THRESHOLD_PX = 96;

interface ModelAssetSidebarPanelProps {
  canDeleteAssets: boolean;
  onOpenLibrary: () => void;
  onOpenModel: () => void;
}

export function ModelAssetSidebarPanel({
  canDeleteAssets,
  onOpenLibrary,
  onOpenModel,
}: ModelAssetSidebarPanelProps) {
  const { t } = useTranslation();
  const getErrorMessage = useCallback((error: unknown) => {
    if (error instanceof ApiError) {
      return localizeModelAssetError(t, error.data?.code, error.data?.error ?? error.message);
    }
    return error instanceof Error ? error.message : t('modelAssetGenericError');
  }, [t]);
  const [deleteTarget, setDeleteTarget] = useState<ModelAsset | null>(null);
  const [recentAssets, setRecentAssets] = useState<ModelAsset[]>([]);
  const [recentNextCursor, setRecentNextCursor] = useState<string | null>(null);
  const [recentLoading, setRecentLoading] = useState(false);
  const [recentTotalSize, setRecentTotalSize] = useState(0);
  const requestIdRef = useRef(0);
  const recentScrollStateRef = useRef({
    loading: false,
    nextCursor: null as string | null,
  });
  const {
    modelAssetTotal,
    currentModelId,
    selectedModelAssetId,
    preferredModelFormat,
    setSelectedModelAsset,
    setCurrentModel,
    setPreviewImage,
    removeModelAsset,
    setModelAssetError,
  } = useAppStore(
    useShallow((state) => ({
      modelAssetTotal: state.modelAssetTotal,
      currentModelId: state.currentModelId,
      selectedModelAssetId: state.selectedModelAssetId,
      preferredModelFormat: state.localModelFormat ?? state.serverModelFormat,
      setSelectedModelAsset: state.setSelectedModelAsset,
      setCurrentModel: state.setCurrentModel,
      setPreviewImage: state.setPreviewImage,
      removeModelAsset: state.removeModelAsset,
      setModelAssetError: state.setModelAssetError,
    })),
  );

  const loadRecentAssets = useCallback(async (cursor: string | null = null, append = false) => {
    const requestId = ++requestIdRef.current;
    recentScrollStateRef.current.loading = true;
    setRecentLoading(true);
    try {
      const response = await fetchModelAssets({
        sort: 'modified_desc',
        cursor,
        limit: RECENT_ASSET_PAGE_SIZE,
      });
      if (requestId !== requestIdRef.current) {
        return;
      }

      setRecentAssets((current) => {
        if (!append) {
          return response.items;
        }

        const existingIds = new Set(current.map((asset) => asset.id));
        const nextItems = response.items.filter((asset) => !existingIds.has(asset.id));
        return [...current, ...nextItems];
      });
      setRecentNextCursor(response.next_cursor);
      setRecentTotalSize(response.total_size);
      recentScrollStateRef.current = {
        loading: false,
        nextCursor: response.next_cursor,
      };
    } catch (error) {
      if (requestId === requestIdRef.current) {
        setModelAssetError(getErrorMessage(error));
      }
    } finally {
      if (requestId === requestIdRef.current) {
        setRecentLoading(false);
        recentScrollStateRef.current.loading = false;
      }
    }
  }, [getErrorMessage, setModelAssetError]);

  useEffect(() => {
    void loadRecentAssets(null, false);
  }, [loadRecentAssets, modelAssetTotal]);

  useEffect(() => {
    recentScrollStateRef.current = {
      loading: recentLoading,
      nextCursor: recentNextCursor,
    };
  }, [recentLoading, recentNextCursor]);

  const handleRecentScroll = useCallback((event: React.UIEvent<HTMLDivElement>) => {
    const state = recentScrollStateRef.current;
    if (state.loading || !state.nextCursor) {
      return;
    }

    const target = event.currentTarget;
    const remaining = target.scrollHeight - target.scrollTop - target.clientHeight;
    if (remaining <= RECENT_LOAD_MORE_THRESHOLD_PX) {
      recentScrollStateRef.current.loading = true;
      void loadRecentAssets(state.nextCursor, true);
    }
  }, [loadRecentAssets]);

  const handleOpen = useCallback((asset: ModelAsset) => {
    onOpenModel();
    setSelectedModelAsset(asset.id);
    const modelSource = resolveModelAssetSource(asset, preferredModelFormat);
    if (!modelSource.url || !modelSource.format) {
      setModelAssetError(t('modelAssetOpenUnavailable'));
      return;
    }
    setCurrentModel({
      id: asset.id,
      url: modelSource.url,
      format: modelSource.format,
      size: modelSource.size,
      source: asset.source_type === 'imported' || asset.is_imported
        ? 'model-asset-imported'
        : 'model-asset-generated',
      sourceMediaType: modelSource.sourceMediaType,
      viewerOrientation: modelSource.viewerOrientation,
    });
  }, [onOpenModel, preferredModelFormat, setCurrentModel, setModelAssetError, setSelectedModelAsset, t]);

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

  const handleDeleteConfirm = useCallback(async () => {
    if (!deleteTarget) {
      return;
    }
    try {
      await deleteModelAsset(deleteTarget.id);
      removeModelAsset(deleteTarget.id);
      setRecentAssets((items) => items.filter((asset) => asset.id !== deleteTarget.id));
      setRecentTotalSize((size) => Math.max(0, size - (deleteTarget.size || deleteTarget.primary_size || 0)));
      if (currentModelId === deleteTarget.id) {
        setCurrentModel(null);
      }
      setDeleteTarget(null);
      void loadRecentAssets(null, false);
    } catch (error) {
      setModelAssetError(getErrorMessage(error));
    }
  }, [currentModelId, deleteTarget, getErrorMessage, loadRecentAssets, removeModelAsset, setCurrentModel, setModelAssetError]);

  const handleActionClick = (
    event: React.MouseEvent<HTMLButtonElement>,
    action: () => void,
  ) => {
    event.stopPropagation();
    action();
  };

  return (
    <div className={styles.panel}>
      <section className={[styles.section, styles.recentSection].join(' ')}>
        <div className={styles.sectionHeader}>
          <span>{t('modelAssetRecentModels')}</span>
          <button
            className={styles.viewAllBtn}
            type="button"
            onClick={onOpenLibrary}
          >
            <span>{t('modelAssetViewAll')}</span>
            <ChevronRightIcon width={12} height={12} />
          </button>
        </div>
        <div className={styles.recentList} onScroll={handleRecentScroll}>
          {!recentLoading && recentAssets.length === 0 ? (
            <div className={styles.empty}>
              <p>{t('modelAssetSidebarEmpty')}</p>
            </div>
          ) : null}
          {recentAssets.map((asset) => {
            const modelSource = resolveModelAssetSource(asset, preferredModelFormat);
            const format = (modelSource.format ?? asset.primary_format ?? asset.formats[0] ?? 'ply').toUpperCase();
            const hasSourcePreview = Boolean(asset.image_url || asset.source_video_url);
            return (
              <div
                key={asset.id}
                className={[
                  styles.recentItem,
                  (selectedModelAssetId === asset.id || currentModelId === asset.id)
                    ? styles.recentItemActive
                    : '',
                ].filter(Boolean).join(' ')}
              >
                <button
                  className={styles.recentMainButton}
                  type="button"
                  aria-label={asset.name}
                  onClick={() => handleOpen(asset)}
                />
                <span className={styles.thumb}>
                  {asset.thumb_url ? (
                    <img src={asset.thumb_url} alt="" loading="lazy" decoding="async" />
                  ) : (
                    <span>{format}</span>
                  )}
                </span>
                <span className={styles.itemText}>
                  <strong>{asset.name}</strong>
                  <small>{format} - {formatFileSize(modelSource.size)}</small>
                </span>
                <span className={styles.itemActions}>
                  {hasSourcePreview ? (
                    <button
                      className={styles.actionBtn}
                      type="button"
                      aria-label={asset.source_video_url ? t('viewOriginalVideo') : t('viewOriginal')}
                      data-tooltip={asset.source_video_url ? t('viewOriginalVideo') : t('viewOriginal')}
                      onClick={(event) => handleActionClick(event, () => handlePreview(asset))}
                    >
                      <EyeIcon width={14} height={14} />
                    </button>
                  ) : null}
                  <button
                    className={styles.actionBtn}
                    type="button"
                    aria-label={t('download')}
                    data-tooltip={t('download')}
                    disabled={!asset.available}
                    onClick={(event) => handleActionClick(event, () => {
                      downloadModelAsset(asset.id, modelSource.format ?? asset.primary_format);
                    })}
                  >
                    <DownloadIcon width={14} height={14} />
                  </button>
                  {canDeleteAssets ? (
                    <button
                      className={[styles.actionBtn, styles.deleteBtn].join(' ')}
                      type="button"
                      aria-label={t('delete')}
                      data-tooltip={t('delete')}
                      onClick={(event) => handleActionClick(event, () => setDeleteTarget(asset))}
                    >
                      <DeleteIcon width={14} height={14} />
                    </button>
                  ) : null}
                </span>
              </div>
            );
          })}
        </div>
        {recentLoading && recentAssets.length > 0 ? (
          <div className={styles.loadingMore} role="status">
            {t('loading')}
          </div>
        ) : null}
      </section>

      <section className={[styles.section, styles.storageSection].join(' ')}>
        <div className={styles.sectionHeader}>
          <span>{t('modelAssetStorage')}</span>
          <span>{formatFileSize(recentTotalSize)}</span>
        </div>
      </section>

      <ConfirmDialog
        isOpen={Boolean(deleteTarget)}
        title={t('delete')}
        message={t('modelAssetDeleteConfirm')}
        confirmLabel={t('delete')}
        danger
        onConfirm={handleDeleteConfirm}
        onClose={() => setDeleteTarget(null)}
      />
    </div>
  );
}
