import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { useTranslation } from 'react-i18next';
import { useShallow } from 'zustand/react/shallow';

import {
  ApiError,
  addPhotoAlbum,
  browseFolder,
  convertPhotosToModels,
  downloadPhotos,
  fetchPhotoAlbumPhotos,
  fetchPhotoAlbums,
  rescanPhotoAlbum,
  uploadPhotosToGallery,
} from '@/api';
import { ChevronUpIcon, CloseIcon } from '@/components/common/Icons';
import { TextInputDialog } from '@/components/common/TextInputDialog';
import { PhotoMasonryGrid } from '@/components/photoGallery/PhotoMasonryGrid';
import { PhotoSelectionBar } from '@/components/photoGallery/PhotoSelectionBar';
import { PhotoToolbar } from '@/components/photoGallery/PhotoToolbar';
import type { PhotoToolbarMode } from '@/components/photoGallery/PhotoToolbar';
import { useAppStore } from '@/store';
import type { PhotoItem, PhotoMediaType } from '@/types';

import styles from './PhotoGalleryView.module.css';

const MIN_GRID_COLUMNS = 1;
const MAX_GRID_COLUMNS = 8;
const MOBILE_TOOLBAR_BREAKPOINT = 1100;
const MOBILE_TOOLBAR_EXPAND_SCROLL_TOP = 1;
const MOBILE_TOOLBAR_COMPACT_SCROLL_TOP = 128;
const NOTICE_SUCCESS_AUTO_DISMISS_MS = 3200;
const NOTICE_ERROR_AUTO_DISMISS_MS = 5200;
const BACK_TO_TOP_VISIBLE_SCROLL_TOP = 420;

function getDefaultGridColumns() {
  if (typeof window === 'undefined') {
    return 5;
  }

  if (window.innerWidth <= 768) {
    return 2;
  }
  if (window.innerWidth <= 980) {
    return 3;
  }
  if (window.innerWidth <= 1280) {
    return 4;
  }
  return 5;
}

function clampGridColumns(columns: number) {
  return Math.min(MAX_GRID_COLUMNS, Math.max(MIN_GRID_COLUMNS, columns));
}

function getTouchDistance(touches: TouchList) {
  const dx = touches[0].clientX - touches[1].clientX;
  const dy = touches[0].clientY - touches[1].clientY;
  return Math.sqrt(dx * dx + dy * dy);
}

export function PhotoGalleryView() {
  const { t } = useTranslation();
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const hasCustomGridColumns = useRef(false);
  const pinchRef = useRef<{ distance: number; columns: number } | null>(null);
  const toolbarModeRef = useRef<PhotoToolbarMode>('expanded');
  const scrollFrameRef = useRef<number | null>(null);
  const resizeFrameRef = useRef<number | null>(null);
  const lastViewportWidthRef = useRef(typeof window === 'undefined' ? 0 : window.innerWidth);
  const scrollStateRef = useRef<{
    isLoading: boolean;
    isLoadingMore: boolean;
    loadPhotos: (cursor: string | null, append: boolean) => void;
    photoNextCursor: string | null;
  } | null>(null);
  const [sort, setSort] = useState('mtime_desc');
  const [gridColumns, setGridColumns] = useState(getDefaultGridColumns);
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [isConverting, setIsConverting] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);
  const [isAddingAlbum, setIsAddingAlbum] = useState(false);
  const [isUploadingPhotos, setIsUploadingPhotos] = useState(false);
  const [uploadingPhotoCount, setUploadingPhotoCount] = useState(0);
  const [toolbarMode, setToolbarMode] = useState<PhotoToolbarMode>('expanded');
  const gridColumnsRef = useRef(gridColumns);
  const [error, setError] = useState<string | null>(null);
  const [pathDialogOpen, setPathDialogOpen] = useState(false);
  const [notice, setNotice] = useState<{ tone: 'success' | 'error'; message: string } | null>(null);
  const [showBackToTop, setShowBackToTop] = useState(false);

  const {
    photoAlbums,
    photoAlbumsLoaded,
    photoAlbumsLoading,
    currentPhotoAlbumId,
    photoItems,
    photoNextCursor,
    photoSnapshot,
    photoTotal,
    photoMediaType,
    photoMediaCounts,
    photoSelectionMode,
    selectedPhotoIds,
    isLocalAccess,
    authStatus,
    sidebarCollapsed,
    setPhotoAlbums,
    setPhotoAlbumsLoading,
    setPhotoItems,
    clearPhotoItems,
    setPhotoMediaType,
    setPhotoSelectionMode,
    toggleSelectedPhoto,
    clearSelectedPhotos,
    setPreviewPhoto,
    openVideoReconstructionDialog,
    upsertTasks,
    setCurrentPhotoAlbum,
  } = useAppStore(
    useShallow((state) => ({
      photoAlbums: state.photoAlbums,
      photoAlbumsLoaded: state.photoAlbumsLoaded,
      photoAlbumsLoading: state.photoAlbumsLoading,
      currentPhotoAlbumId: state.currentPhotoAlbumId,
      photoItems: state.photoItems,
      photoNextCursor: state.photoNextCursor,
      photoSnapshot: state.photoSnapshot,
      photoTotal: state.photoTotal,
      photoMediaType: state.photoMediaType,
      photoMediaCounts: state.photoMediaCounts,
      photoSelectionMode: state.photoSelectionMode,
      selectedPhotoIds: state.selectedPhotoIds,
      isLocalAccess: state.isLocalAccess,
      authStatus: state.authStatus,
      sidebarCollapsed: state.sidebarCollapsed,
      setPhotoAlbums: state.setPhotoAlbums,
      setPhotoAlbumsLoading: state.setPhotoAlbumsLoading,
      setPhotoItems: state.setPhotoItems,
      clearPhotoItems: state.clearPhotoItems,
      setPhotoMediaType: state.setPhotoMediaType,
      setPhotoSelectionMode: state.setPhotoSelectionMode,
      toggleSelectedPhoto: state.toggleSelectedPhoto,
      clearSelectedPhotos: state.clearSelectedPhotos,
      setPreviewPhoto: state.setPreviewPhoto,
      openVideoReconstructionDialog: state.openVideoReconstructionDialog,
      upsertTasks: state.upsertTasks,
      setCurrentPhotoAlbum: state.setCurrentPhotoAlbum,
    })),
  );

  const currentAlbum = photoAlbums.find((album) => album.id === currentPhotoAlbumId) ?? null;
  const currentAlbumIsIndexing = Boolean(
    currentAlbum && ['needs_index', 'indexing', 'scanning'].includes(currentAlbum.scan_status),
  );
  const selectedPhotoIdSet = useMemo(() => new Set(selectedPhotoIds), [selectedPhotoIds]);
  const selectedItems = useMemo(
    () => photoItems.filter((photo) => selectedPhotoIdSet.has(photo.id)),
    [photoItems, selectedPhotoIdSet],
  );
  const selectedImageItems = useMemo(
    () => selectedItems.filter((photo) => photo.media_type === 'image'),
    [selectedItems],
  );
  const selectedVideoItems = useMemo(
    () => selectedItems.filter((photo) => photo.media_type === 'video'),
    [selectedItems],
  );
  const canUploadPhotos = Boolean(currentAlbum) && (
    isLocalAccess || Boolean(authStatus?.access_control_enabled)
  );

  const updateToolbarMode = useCallback((nextMode: PhotoToolbarMode) => {
    if (toolbarModeRef.current === nextMode) {
      return;
    }
    toolbarModeRef.current = nextMode;
    setToolbarMode(nextMode);
  }, []);

  useEffect(() => {
    const handleResize = () => {
      if (resizeFrameRef.current !== null) {
        return;
      }

      resizeFrameRef.current = window.requestAnimationFrame(() => {
        resizeFrameRef.current = null;
        const nextWidth = window.innerWidth;

        // Mobile browser chrome can resize only viewport height while scrolling.
        // Ignoring height-only resize avoids rebuilding the masonry grid mid-scroll.
        if (Math.abs(nextWidth - lastViewportWidthRef.current) < 1) {
          return;
        }
        lastViewportWidthRef.current = nextWidth;

        if (nextWidth > MOBILE_TOOLBAR_BREAKPOINT) {
          updateToolbarMode('expanded');
        }

        if (hasCustomGridColumns.current) {
          setGridColumns((current) => {
            const nextColumns = clampGridColumns(current);
            return current === nextColumns ? current : nextColumns;
          });
          return;
        }

        const nextColumns = getDefaultGridColumns();
        setGridColumns((current) => current === nextColumns ? current : nextColumns);
      });
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [updateToolbarMode]);

  useEffect(() => {
    gridColumnsRef.current = gridColumns;
  }, [gridColumns]);

  useEffect(() => () => {
    if (scrollFrameRef.current !== null) {
      window.cancelAnimationFrame(scrollFrameRef.current);
    }
    if (resizeFrameRef.current !== null) {
      window.cancelAnimationFrame(resizeFrameRef.current);
    }
  }, []);

  useEffect(() => {
    if (!notice || isUploadingPhotos) {
      return;
    }

    const timeout = window.setTimeout(
      () => setNotice(null),
      notice.tone === 'success' ? NOTICE_SUCCESS_AUTO_DISMISS_MS : NOTICE_ERROR_AUTO_DISMISS_MS,
    );
    return () => window.clearTimeout(timeout);
  }, [isUploadingPhotos, notice]);

  const refreshAlbums = useCallback(async () => {
    setPhotoAlbumsLoading(true);
    try {
      const response = await fetchPhotoAlbums();
      setPhotoAlbums(response.albums);
    } catch (refreshError) {
      setPhotoAlbumsLoading(false);
      throw refreshError;
    }
  }, [setPhotoAlbums, setPhotoAlbumsLoading]);

  useEffect(() => {
    if (photoAlbumsLoaded || photoAlbumsLoading) {
      return;
    }

    void refreshAlbums().catch((loadError) => {
      const message = loadError instanceof Error ? loadError.message : t('photoAlbumsLoadFailed');
      setError(message);
    });
  }, [photoAlbumsLoaded, photoAlbumsLoading, refreshAlbums, t]);

  const loadPhotos = useCallback(async (
    cursor: string | null,
    append: boolean,
    albumId = currentPhotoAlbumId,
  ) => {
    if (!albumId) {
      clearPhotoItems();
      return;
    }

    try {
      if (append) {
        setIsLoadingMore(true);
      } else {
        setIsLoading(true);
      }
      setError(null);

      const response = await fetchPhotoAlbumPhotos(
        albumId,
        cursor,
        60,
        sort,
        photoMediaType,
        append ? photoSnapshot : null,
      );
      setPhotoItems(
        response.items,
        response.next_cursor,
        response.total,
        append,
        response.media_counts,
        response.snapshot ?? null,
      );
      if (response.error) {
        setError(response.error);
      }
    } catch (loadError) {
      const message = loadError instanceof Error ? loadError.message : t('photoLoadFailed');
      setError(message);
      if (!append) {
        clearPhotoItems();
      }
    } finally {
      setIsLoading(false);
      setIsLoadingMore(false);
    }
  }, [clearPhotoItems, currentPhotoAlbumId, photoMediaType, photoSnapshot, setPhotoItems, sort, t]);

  useEffect(() => {
    scrollStateRef.current = {
      isLoading,
      isLoadingMore,
      loadPhotos: (cursor, append) => {
        void loadPhotos(cursor, append);
      },
      photoNextCursor,
    };
  }, [isLoading, isLoadingMore, loadPhotos, photoNextCursor]);

  useEffect(() => {
    void loadPhotos(null, false);
  }, [loadPhotos]);

  useEffect(() => {
    if (!currentAlbum || !['needs_index', 'indexing', 'scanning'].includes(currentAlbum.scan_status)) {
      return;
    }

    const interval = window.setInterval(() => {
      void refreshAlbums().catch(() => {
        // Keep the current cached UI; manual refresh can surface the error.
      });
    }, 1600);
    return () => window.clearInterval(interval);
  }, [currentAlbum, refreshAlbums]);

  const handleScroll = useCallback(() => {
    if (scrollFrameRef.current !== null) {
      return;
    }

    scrollFrameRef.current = window.requestAnimationFrame(() => {
      scrollFrameRef.current = null;
      const el = scrollRef.current;
      if (!el) {
        return;
      }

      const scrollTop = el.scrollTop;
      setShowBackToTop((current) => {
        const nextVisible = scrollTop >= BACK_TO_TOP_VISIBLE_SCROLL_TOP;
        return current === nextVisible ? current : nextVisible;
      });

      if (window.innerWidth <= MOBILE_TOOLBAR_BREAKPOINT) {
        if (scrollTop <= MOBILE_TOOLBAR_EXPAND_SCROLL_TOP) {
          updateToolbarMode('expanded');
        } else if (toolbarModeRef.current === 'expanded' && scrollTop >= MOBILE_TOOLBAR_COMPACT_SCROLL_TOP) {
          updateToolbarMode('compact');
        }
      }

      const scrollState = scrollStateRef.current;
      if (!scrollState || !scrollState.photoNextCursor || scrollState.isLoadingMore || scrollState.isLoading) {
        return;
      }

      const remaining = el.scrollHeight - el.scrollTop - el.clientHeight;
      if (remaining < 700) {
        scrollState.isLoadingMore = true;
        scrollState.loadPhotos(scrollState.photoNextCursor, true);
      }
    });
  }, [updateToolbarMode]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) {
      return;
    }

    el.addEventListener('scroll', handleScroll, { passive: true });
    return () => el.removeEventListener('scroll', handleScroll);
  }, [handleScroll]);

  const submitAlbumPath = useCallback(async (selectedPath: string) => {
    if (!selectedPath.trim() || isAddingAlbum) {
      return;
    }

    try {
      setIsAddingAlbum(true);
      setNotice(null);
      const result = await addPhotoAlbum({ path: selectedPath.trim(), recursive: true });
      await refreshAlbums();
      setCurrentPhotoAlbum(result.album.id);
      setPathDialogOpen(false);
    } catch (addError) {
      const message = addError instanceof Error ? addError.message : t('photoAlbumAddFailed');
      setNotice({ tone: 'error', message });
    } finally {
      setIsAddingAlbum(false);
    }
  }, [isAddingAlbum, refreshAlbums, setCurrentPhotoAlbum, t]);

  const handleAddAlbum = useCallback(async () => {
    if (!isLocalAccess) {
      return;
    }

    let selectedPath: string | undefined;
    try {
      const result = await browseFolder(t('photoSelectFolder'));
      if (result.success && result.path) {
        selectedPath = result.path;
      }
    } catch {
      // Fall back to manual path input.
    }

    if (!selectedPath) {
      setPathDialogOpen(true);
      return;
    }

    void submitAlbumPath(selectedPath);
  }, [isLocalAccess, submitAlbumPath, t]);

  const handleRefresh = useCallback(async () => {
    if (currentAlbum) {
      await rescanPhotoAlbum(currentAlbum.id);
    }
    await refreshAlbums();
    await loadPhotos(null, false);
  }, [currentAlbum, loadPhotos, refreshAlbums]);

  const handleUploadPhotos = useCallback(async (files: FileList | File[]) => {
    if (!currentAlbum) {
      return;
    }

    const imageFiles = Array.from(files).filter((file) =>
      file.type.startsWith('image/') || /\.(jpe?g|png|webp)$/i.test(file.name),
    );

    if (imageFiles.length === 0) {
      setNotice({ tone: 'error', message: t('selectImageFiles') });
      return;
    }

    if (isUploadingPhotos) {
      return;
    }

    const targetAlbumId = currentAlbum.id;

    try {
      setIsUploadingPhotos(true);
      setUploadingPhotoCount(imageFiles.length);
      setNotice({ tone: 'success', message: t('photoUploadPreparing') });

      const result = await uploadPhotosToGallery(targetAlbumId, imageFiles);
      await refreshAlbums();
      await loadPhotos(null, false, targetAlbumId);

      const failedCount = result.failed?.length ?? 0;
      setNotice({
        tone: failedCount > 0 ? 'error' : 'success',
        message: failedCount > 0
          ? t('photoUploadPartial', { success: result.uploaded, failed: failedCount })
          : t('photoUploadComplete', { count: result.uploaded }),
      });
    } catch (uploadError) {
      const message = uploadError instanceof ApiError && uploadError.status === 403
        ? t('photoUploadAccessDenied')
        : uploadError instanceof Error
          ? uploadError.message
          : t('photoUploadFailed');
      setNotice({ tone: 'error', message });
    } finally {
      setIsUploadingPhotos(false);
      setUploadingPhotoCount(0);
    }
  }, [currentAlbum, isUploadingPhotos, loadPhotos, refreshAlbums, t]);

  const handleSortChange = useCallback((nextSort: string) => {
    setSort(nextSort);
    scrollRef.current?.scrollTo({ top: 0 });
  }, []);

  const handleMediaTypeChange = useCallback((nextType: PhotoMediaType) => {
    setPhotoMediaType(nextType);
    scrollRef.current?.scrollTo({ top: 0 });
  }, [setPhotoMediaType]);

  const handleGridColumnsChange = useCallback((nextColumns: number) => {
    hasCustomGridColumns.current = true;
    setGridColumns(clampGridColumns(nextColumns));
  }, []);

  const handleExpandToolbar = useCallback(() => {
    updateToolbarMode('expanded');
  }, [updateToolbarMode]);

  const handleBackToTop = useCallback(() => {
    scrollRef.current?.scrollTo({ top: 0, behavior: 'smooth' });
    updateToolbarMode('expanded');
  }, [updateToolbarMode]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) {
      return;
    }

    const handleTouchMove = (event: TouchEvent) => {
      if (!pinchRef.current || event.touches.length !== 2) {
        return;
      }

      event.preventDefault();
      const distance = getTouchDistance(event.touches);
      const delta = distance - pinchRef.current.distance;
      if (Math.abs(delta) < 34) {
        return;
      }

      const nextColumns = delta > 0
        ? pinchRef.current.columns - 1
        : pinchRef.current.columns + 1;
      const clampedColumns = clampGridColumns(nextColumns);
      hasCustomGridColumns.current = true;
      setGridColumns((current) => current === clampedColumns ? current : clampedColumns);
      gridColumnsRef.current = clampedColumns;
      pinchRef.current = {
        distance,
        columns: clampedColumns,
      };
    };

    const handleTouchEnd = () => {
      pinchRef.current = null;
      el.removeEventListener('touchmove', handleTouchMove);
    };

    const handleTouchStart = (event: TouchEvent) => {
      if (event.touches.length !== 2) {
        return;
      }

      pinchRef.current = {
        distance: getTouchDistance(event.touches),
        columns: gridColumnsRef.current,
      };
      el.addEventListener('touchmove', handleTouchMove, { passive: false });
    };

    el.addEventListener('touchstart', handleTouchStart, { passive: true });
    el.addEventListener('touchend', handleTouchEnd, { passive: true });
    el.addEventListener('touchcancel', handleTouchEnd, { passive: true });
    return () => {
      el.removeEventListener('touchstart', handleTouchStart);
      el.removeEventListener('touchmove', handleTouchMove);
      el.removeEventListener('touchend', handleTouchEnd);
      el.removeEventListener('touchcancel', handleTouchEnd);
    };
  }, []);

  const convertPhotos = useCallback(async (photos: PhotoItem[]) => {
    const imagePhotos = photos.filter((photo) => photo.media_type === 'image');
    if (imagePhotos.length === 0 || isConverting) {
      return;
    }

    try {
      setIsConverting(true);
      setNotice({ tone: 'success', message: t('photoConvertPreparing') });
      const result = await convertPhotosToModels(imagePhotos.map((photo) => photo.id));
      if (result.tasks?.length) {
        upsertTasks(result.tasks);
      }
      clearSelectedPhotos();
      const failedCount = result.failed?.length ?? 0;
      const queuedCount = result.tasks?.length ?? 0;
      setNotice({
        tone: failedCount > 0 ? 'error' : 'success',
        message: failedCount > 0
          ? t('photoConvertPartial', { success: queuedCount, failed: failedCount })
          : t('photoConvertQueued', { count: queuedCount }),
      });
    } catch (convertError) {
      const message = convertError instanceof Error ? convertError.message : t('photoConvertFailed');
      setNotice({ tone: 'error', message });
    } finally {
      setIsConverting(false);
    }
  }, [clearSelectedPhotos, isConverting, t, upsertTasks]);

  const handleConvertSelected = useCallback(() => {
    void convertPhotos(selectedItems);
  }, [convertPhotos, selectedItems]);

  const handleConvertOne = useCallback((photo: PhotoItem) => {
    void convertPhotos([photo]);
  }, [convertPhotos]);

  const handleReconstructVideo = useCallback((photo: PhotoItem) => {
    if (photo.media_type !== 'video') {
      return;
    }
    openVideoReconstructionDialog(photo);
  }, [openVideoReconstructionDialog]);

  const handleReconstructSelectedVideo = useCallback(() => {
    if (selectedVideoItems.length !== 1) {
      return;
    }
    openVideoReconstructionDialog(selectedVideoItems[0]);
  }, [openVideoReconstructionDialog, selectedVideoItems]);

  const handleDownloadSelected = useCallback(async () => {
    if (selectedPhotoIds.length === 0 || isDownloading) {
      return;
    }

    try {
      setIsDownloading(true);
      const result = await downloadPhotos(selectedPhotoIds);
      setNotice({
        tone: result.failed > 0 ? 'error' : 'success',
        message: result.failed > 0
          ? t('photoDownloadPartial', { success: result.downloaded, failed: result.failed })
          : t('photoDownloadReady', { count: result.downloaded }),
      });
    } catch (downloadError) {
      const message = downloadError instanceof Error ? downloadError.message : t('photoDownloadFailed');
      setNotice({ tone: 'error', message });
    } finally {
      setIsDownloading(false);
    }
  }, [isDownloading, selectedPhotoIds, t]);

  return (
    <div className={styles.root}>
      <div className={styles.backdrop} />
      <div
        ref={scrollRef}
        className={[
          styles.scrollArea,
          !sidebarCollapsed ? styles.scrollAreaWithSidebar : '',
        ].filter(Boolean).join(' ')}
      >
        <PhotoToolbar
          album={currentAlbum}
          total={photoTotal}
          mediaType={photoMediaType}
          mediaCounts={photoMediaCounts}
          sort={sort}
          selectionMode={photoSelectionMode}
          selectedCount={selectedPhotoIds.length}
          selectedImageCount={selectedImageItems.length}
          gridColumns={gridColumns}
          isLocalAccess={isLocalAccess}
          isLoading={isLoading}
          canUploadPhotos={canUploadPhotos}
          isUploadingPhotos={isUploadingPhotos}
          uploadingPhotoCount={uploadingPhotoCount}
          mode={toolbarMode}
          onAddAlbum={handleAddAlbum}
          onUploadPhotos={handleUploadPhotos}
          onRefresh={handleRefresh}
          onMediaTypeChange={handleMediaTypeChange}
          onSortChange={handleSortChange}
          onGridColumnsChange={handleGridColumnsChange}
          onToggleSelection={() => setPhotoSelectionMode(!photoSelectionMode)}
          onConvertSelected={handleConvertSelected}
          onExpandRequest={handleExpandToolbar}
        />

        {error ? <div className={styles.error}>{error}</div> : null}
        {!error && currentAlbumIsIndexing ? (
          <div className={styles.error}>
            {currentAlbum?.scan_status === 'needs_index'
              ? t('photoAlbumNeedsIndex')
              : t('photoAlbumIndexing')}
          </div>
        ) : null}

        <PhotoMasonryGrid
          items={photoItems}
          isLoading={isLoading || isLoadingMore}
          selectionMode={photoSelectionMode}
          selectedPhotoIds={selectedPhotoIds}
          columns={gridColumns}
          mediaType={photoMediaType}
          onOpenPhoto={setPreviewPhoto}
          onTogglePhoto={toggleSelectedPhoto}
          onConvertPhoto={handleConvertOne}
          onReconstructVideo={handleReconstructVideo}
        />
      </div>

      <button
        className={[
          styles.backToTop,
          showBackToTop ? styles.backToTopVisible : '',
          photoSelectionMode ? styles.backToTopWithSelection : '',
        ].filter(Boolean).join(' ')}
        onClick={handleBackToTop}
        type="button"
        data-tooltip={t('photoBackToTop')}
        aria-label={t('photoBackToTop')}
      >
        <ChevronUpIcon width={20} height={20} />
      </button>

      {notice ? (
        <div className={[styles.notice, styles[notice.tone]].join(' ')} role="status" aria-live="polite">
          <span>{notice.message}</span>
          <button
            onClick={() => setNotice(null)}
            type="button"
            data-tooltip={t('close')}
            aria-label={t('close')}
          >
            <CloseIcon width={14} height={14} />
          </button>
        </div>
      ) : null}

      <PhotoSelectionBar
        selectedCount={selectedPhotoIds.length}
        isConverting={isConverting}
        isDownloading={isDownloading}
        canConvert={selectedImageItems.length > 0}
        convertCount={selectedImageItems.length}
        videoCount={selectedVideoItems.length}
        canReconstructVideo={selectedVideoItems.length === 1}
        onConvert={handleConvertSelected}
        onReconstructVideo={handleReconstructSelectedVideo}
        onDownload={handleDownloadSelected}
        onClear={clearSelectedPhotos}
      />

      <TextInputDialog
        isOpen={pathDialogOpen}
        title={t('photoAddAlbum')}
        label={t('photoPathPrompt')}
        placeholder={t('photoPathPlaceholder')}
        confirmLabel={t('photoAddAlbum')}
        isBusy={isAddingAlbum}
        onSubmit={submitAlbumPath}
        onClose={() => setPathDialogOpen(false)}
      />
    </div>
  );
}
