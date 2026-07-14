import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';

import { useTranslation } from 'react-i18next';
import { useShallow } from 'zustand/react/shallow';

import { deleteGalleryItem, downloadModel } from '@/api';
import { CloseIcon } from '@/components/common/Icons';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { GalleryItem } from '@/components/gallery/GalleryItem';
import { useGalleryVirtualizer } from '@/hooks/useGalleryVirtualizer';
import { useAppStore } from '@/store';
import {
  GALLERY_LIST_PADDING,
  GALLERY_ROW_HEIGHT,
  getGalleryModelSource,
  getGalleryRendererMode,
  getGallerySourceVideoUrl,
} from '@/utils';
import type { GalleryItem as GalleryItemType } from '@/types';

import styles from './GalleryList.module.css';

interface ScrollAnchor {
  id: string | null;
  offset: number;
}

export function GalleryList() {
  const { t } = useTranslation();

  const items = useAppStore((state) => state.galleryItems);
  const preferredFormat = useAppStore((state) => state.localModelFormat ?? state.serverModelFormat);
  const {
    currentModelId,
    sidebarCollapsed,
    sidebarOpen,
    removeGalleryItem,
    setCurrentModel,
    setPreviewImage,
    setSidebarOpen,
  } = useAppStore(
    useShallow((state) => ({
      currentModelId: state.currentModelId,
      sidebarCollapsed: state.sidebarCollapsed,
      sidebarOpen: state.sidebarOpen,
      removeGalleryItem: state.removeGalleryItem,
      setCurrentModel: state.setCurrentModel,
      setPreviewImage: state.setPreviewImage,
      setSidebarOpen: state.setSidebarOpen,
    })),
  );

  const scrollElementRef = useRef<HTMLDivElement | null>(null);
  const previousItemsRef = useRef(items);
  const scrollAnchorRef = useRef<ScrollAnchor>({ id: items[0]?.id ?? null, offset: 0 });
  const [rendererMode] = useState(() => getGalleryRendererMode());
  const [deleteTarget, setDeleteTarget] = useState<GalleryItemType | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const rowVirtualizer = useGalleryVirtualizer({
    count: items.length,
    getItemKey: (index) => items[index]?.id ?? `gallery-row-${index}`,
    scrollElementRef,
  });

  const updateScrollAnchor = useCallback(() => {
    const scrollElement = scrollElementRef.current;
    if (!scrollElement || items.length === 0) {
      scrollAnchorRef.current = { id: null, offset: 0 };
      return;
    }

    const scrollTop = Math.max(0, scrollElement.scrollTop - GALLERY_LIST_PADDING);
    const index = Math.min(items.length - 1, Math.floor(scrollTop / GALLERY_ROW_HEIGHT));
    const anchorItem = items[index];

    scrollAnchorRef.current = {
      id: anchorItem?.id ?? null,
      offset: scrollTop - index * GALLERY_ROW_HEIGHT,
    };
  }, [items]);

  const restoreScrollAnchor = useCallback(() => {
    const scrollElement = scrollElementRef.current;
    const { id, offset } = scrollAnchorRef.current;
    if (!scrollElement || !id || items.length === 0) {
      return;
    }

    const index = items.findIndex((item) => item.id === id);
    if (index < 0) {
      return;
    }

    scrollElement.scrollTop = GALLERY_LIST_PADDING + index * GALLERY_ROW_HEIGHT + offset;
  }, [items]);

  const scrollItemIntoView = useCallback((index: number) => {
    const scrollElement = scrollElementRef.current;
    if (!scrollElement) {
      return;
    }

    const itemTop = GALLERY_LIST_PADDING + index * GALLERY_ROW_HEIGHT;
    const itemBottom = itemTop + GALLERY_ROW_HEIGHT;
    const viewportTop = scrollElement.scrollTop;
    const viewportBottom = viewportTop + scrollElement.clientHeight;

    if (itemTop < viewportTop) {
      scrollElement.scrollTop = itemTop;
      return;
    }

    if (itemBottom > viewportBottom) {
      scrollElement.scrollTop = itemBottom - scrollElement.clientHeight;
    }
  }, []);

  useLayoutEffect(() => {
    const previousItems = previousItemsRef.current;
    previousItemsRef.current = items;

    if (previousItems === items) {
      return;
    }

    const frame = window.requestAnimationFrame(() => {
      restoreScrollAnchor();
      if (rendererMode === 'virtualized') {
        rowVirtualizer.measure();
      }
    });

    return () => {
      window.cancelAnimationFrame(frame);
    };
  }, [items, rendererMode, restoreScrollAnchor, rowVirtualizer]);

  useEffect(() => {
    if (!currentModelId) {
      return;
    }

    const index = items.findIndex((item) => item.id === currentModelId);
    if (index < 0) {
      return;
    }

    const frame = window.requestAnimationFrame(() => {
      scrollItemIntoView(index);
    });

    return () => {
      window.cancelAnimationFrame(frame);
    };
  }, [currentModelId, items, scrollItemIntoView]);

  useEffect(() => {
    if (rendererMode !== 'virtualized') {
      return;
    }

    const frame = window.requestAnimationFrame(() => {
      rowVirtualizer.measure();
    });

    return () => {
      window.cancelAnimationFrame(frame);
    };
  }, [rendererMode, rowVirtualizer, sidebarCollapsed, sidebarOpen]);

  const handleSelectModel = useCallback((item: GalleryItemType) => {
    const nextModel = getGalleryModelSource(item, preferredFormat);
    setCurrentModel(item.id, nextModel.url, nextModel.format, nextModel.size);

    if (window.innerWidth <= 768 && sidebarOpen) {
      setSidebarOpen(false);
    }
  }, [preferredFormat, setCurrentModel, setSidebarOpen, sidebarOpen]);

  const handlePreview = useCallback((item: GalleryItemType) => {
    const sourceVideoUrl = getGallerySourceVideoUrl(item);
    if (item.image_url || sourceVideoUrl) {
      setPreviewImage(sourceVideoUrl
        ? {
          ...item,
          source_media_type: 'video',
          source_video_url: sourceVideoUrl,
        }
        : item);
    }
  }, [setPreviewImage]);

  const handleDownload = useCallback((item: GalleryItemType) => {
    downloadModel(item.id, preferredFormat);
  }, [preferredFormat]);

  const handleDelete = useCallback((item: GalleryItemType) => {
    setDeleteTarget(item);
  }, []);

  const confirmDelete = useCallback(async () => {
    if (!deleteTarget) {
      return;
    }

    try {
      setIsDeleting(true);
      setMessage(null);
      const result = await deleteGalleryItem(deleteTarget.id);
      if (result.success) {
        removeGalleryItem(deleteTarget.id);
        setDeleteTarget(null);
      } else {
        setMessage(`${t('deleteFailed')}: ${result.error}`);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unknown error';
      setMessage(`${t('errorDeleting')}: ${message}`);
    } finally {
      setIsDeleting(false);
    }
  }, [deleteTarget, removeGalleryItem, t]);

  if (items.length === 0) {
    return (
      <div className={styles.empty}>
        <p>{t('emptyStateTitle')}</p>
      </div>
    );
  }

  return (
    <div className={styles.root}>
      {message ? (
        <div className={styles.notice}>
          <span>{message}</span>
          <button
            onClick={() => setMessage(null)}
            type="button"
            data-tooltip={t('close')}
            aria-label={t('close')}
          >
            <CloseIcon width={13} height={13} />
          </button>
        </div>
      ) : null}

      <div
        ref={scrollElementRef}
        className={styles.viewport}
        onScroll={updateScrollAnchor}
        role="list"
        aria-label={t('gallery')}
      >
        {rendererMode === 'virtualized' ? (
          <div
            className={styles.virtualContent}
            style={{ height: `${rowVirtualizer.getTotalSize() + GALLERY_LIST_PADDING * 2}px` }}
          >
            {rowVirtualizer.getVirtualItems().map((virtualRow) => {
              const item = items[virtualRow.index];
              if (!item) {
                return null;
              }

              return (
                <div
                  key={item.id}
                  className={styles.virtualRow}
                  style={{
                    height: `${GALLERY_ROW_HEIGHT}px`,
                    transform: `translateY(${virtualRow.start + GALLERY_LIST_PADDING}px)`,
                  }}
                >
                  <GalleryItem
                    item={item}
                    preferredFormat={preferredFormat}
                    isActive={currentModelId === item.id}
                    onSelect={handleSelectModel}
                    onPreview={handlePreview}
                    onDownload={handleDownload}
                    onDelete={handleDelete}
                  />
                </div>
              );
            })}
          </div>
        ) : (
          <div className={styles.legacyContent}>
            {items.map((item) => (
              <div key={item.id} className={styles.legacyRow}>
                <GalleryItem
                  item={item}
                  preferredFormat={preferredFormat}
                  isActive={currentModelId === item.id}
                  onSelect={handleSelectModel}
                  onPreview={handlePreview}
                  onDownload={handleDownload}
                  onDelete={handleDelete}
                />
              </div>
            ))}
          </div>
        )}
      </div>

      <ConfirmDialog
        isOpen={Boolean(deleteTarget)}
        title={t('delete')}
        message={t('confirmDeleteFull')}
        confirmLabel={t('delete')}
        isBusy={isDeleting}
        danger
        onConfirm={confirmDelete}
        onClose={() => setDeleteTarget(null)}
      />
    </div>
  );
}
