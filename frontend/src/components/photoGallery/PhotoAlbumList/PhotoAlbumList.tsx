import { useCallback, useEffect, useState } from 'react';

import { useTranslation } from 'react-i18next';
import { useShallow } from 'zustand/react/shallow';

import {
  addPhotoAlbum,
  browseFolder,
  deletePhotoAlbum,
  fetchPhotoAlbums,
  rescanPhotoAlbum,
} from '@/api';
import {
  CheckIcon,
  CloseIcon,
  DeleteIcon,
  FolderIcon,
  PlusIcon,
  ResetIcon,
} from '@/components/common/Icons';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { TextInputDialog } from '@/components/common/TextInputDialog';
import { useAppStore } from '@/store';
import { getPhotoAlbumErrorKey, isPhotoAlbumAvailable } from '@/utils/photoAlbums';
import type { PhotoAlbum } from '@/types';

import styles from './PhotoAlbumList.module.css';

export function PhotoAlbumList() {
  const { t } = useTranslation();
  const [isBusy, setIsBusy] = useState(false);
  const [pathDialogOpen, setPathDialogOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<PhotoAlbum | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const {
    photoAlbums,
    photoAlbumsLoaded,
    photoAlbumsLoading,
    currentPhotoAlbumId,
    isLocalAccess,
    setPhotoAlbums,
    setPhotoAlbumsLoading,
    setCurrentPhotoAlbum,
  } = useAppStore(
    useShallow((state) => ({
      photoAlbums: state.photoAlbums,
      photoAlbumsLoaded: state.photoAlbumsLoaded,
      photoAlbumsLoading: state.photoAlbumsLoading,
      currentPhotoAlbumId: state.currentPhotoAlbumId,
      isLocalAccess: state.isLocalAccess,
      setPhotoAlbums: state.setPhotoAlbums,
      setPhotoAlbumsLoading: state.setPhotoAlbumsLoading,
      setCurrentPhotoAlbum: state.setCurrentPhotoAlbum,
    })),
  );

  const refreshAlbums = useCallback(async () => {
    setPhotoAlbumsLoading(true);
    try {
      const response = await fetchPhotoAlbums();
      setPhotoAlbums(response.albums);
    } catch (error) {
      setPhotoAlbumsLoading(false);
      throw error;
    }
  }, [setPhotoAlbums, setPhotoAlbumsLoading]);

  useEffect(() => {
    if (photoAlbumsLoaded || photoAlbumsLoading) {
      return;
    }

    void refreshAlbums().catch((error) => {
      const errorMessage = error instanceof Error ? error.message : t('photoAlbumsLoadFailed');
      setMessage(errorMessage);
    });
  }, [photoAlbumsLoaded, photoAlbumsLoading, refreshAlbums, t]);

  useEffect(() => {
    let disposed = false;
    let checking = false;
    const checkAvailability = async () => {
      if (document.visibilityState === 'hidden' || checking) return;
      checking = true;
      try {
        const response = await fetchPhotoAlbums();
        if (!disposed) setPhotoAlbums(response.albums);
      } catch {
        // 网络错误不等于磁盘离线，保留上一次已确认的状态。
      } finally {
        checking = false;
      }
    };
    const interval = window.setInterval(() => void checkAvailability(), 10000);
    const handleFocus = () => void checkAvailability();
    window.addEventListener('focus', handleFocus);
    document.addEventListener('visibilitychange', handleFocus);
    void checkAvailability();
    return () => {
      disposed = true;
      window.clearInterval(interval);
      window.removeEventListener('focus', handleFocus);
      document.removeEventListener('visibilitychange', handleFocus);
    };
  }, [setPhotoAlbums]);

  const handleOpenAlbum = useCallback(async (album: PhotoAlbum) => {
    if (!isPhotoAlbumAvailable(album) || isBusy) return;
    setIsBusy(true);
    try {
      const response = await fetchPhotoAlbums();
      setPhotoAlbums(response.albums);
      const freshAlbum = response.albums.find((item) => item.id === album.id);
      if (isPhotoAlbumAvailable(freshAlbum)) {
        setCurrentPhotoAlbum(album.id);
        setMessage(null);
      } else {
        setMessage(t(getPhotoAlbumErrorKey(freshAlbum?.code)));
      }
    } catch {
      setMessage(t('photoAlbumsLoadFailed'));
    } finally {
      setIsBusy(false);
    }
  }, [isBusy, setCurrentPhotoAlbum, setPhotoAlbums, t]);

  const submitAlbumPath = useCallback(async (selectedPath: string) => {
    if (!selectedPath.trim() || isBusy) {
      return;
    }

    try {
      setIsBusy(true);
      setMessage(null);
      const result = await addPhotoAlbum({ path: selectedPath.trim(), recursive: true });
      if (result.success) {
        await refreshAlbums();
        setCurrentPhotoAlbum(result.album.id);
        setPathDialogOpen(false);
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : t('photoAlbumAddFailed');
      setMessage(errorMessage);
    } finally {
      setIsBusy(false);
    }
  }, [isBusy, refreshAlbums, setCurrentPhotoAlbum, t]);

  const handleAddAlbum = useCallback(async () => {
    if (!isLocalAccess || isBusy) {
      return;
    }

    try {
      setIsBusy(true);
      setMessage(null);
      let selectedPath: string | undefined;

      try {
        const result = await browseFolder(t('photoSelectFolder'));
        if (result.success && result.path) {
          selectedPath = result.path;
        }
      } catch {
        // Fall back to manual path input below.
      }

      if (!selectedPath) {
        setPathDialogOpen(true);
        return;
      }

      await submitAlbumPath(selectedPath);
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : t('photoAlbumAddFailed');
      setMessage(errorMessage);
    } finally {
      setIsBusy(false);
    }
  }, [isBusy, isLocalAccess, submitAlbumPath, t]);

  const handleDeleteAlbum = useCallback(async (
    event: React.MouseEvent<HTMLButtonElement>,
    album: PhotoAlbum,
  ) => {
    event.stopPropagation();
    setDeleteTarget(album);
  }, []);

  const confirmDeleteAlbum = useCallback(async () => {
    if (!deleteTarget) {
      return;
    }

    try {
      setIsBusy(true);
      setMessage(null);
      await deletePhotoAlbum(deleteTarget.id);
      await refreshAlbums();
      setDeleteTarget(null);
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : t('photoAlbumDeleteFailed');
      setMessage(errorMessage);
    } finally {
      setIsBusy(false);
    }
  }, [deleteTarget, refreshAlbums, t]);

  const handleRescanAlbum = useCallback(async (
    event: React.MouseEvent<HTMLButtonElement>,
    album: PhotoAlbum,
  ) => {
    event.stopPropagation();
    try {
      setIsBusy(true);
      setMessage(null);
      const result = await rescanPhotoAlbum(album.id);
      await refreshAlbums();
      if (!result.success) setMessage(t(getPhotoAlbumErrorKey(result.album?.code)));
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : t('photoAlbumScanFailed');
      setMessage(errorMessage);
    } finally {
      setIsBusy(false);
    }
  }, [refreshAlbums, t]);

  return (
    <section className={styles.root} aria-label={t('photoAlbums')}>
      <div className={styles.header}>
        <div>
          <h2>{t('photoAlbums')}</h2>
          <p>{t('photoAlbumsHint')}</p>
        </div>
        <button
          className={styles.addBtn}
          onClick={handleAddAlbum}
          disabled={!isLocalAccess || isBusy}
          data-tooltip={isLocalAccess ? t('photoAddAlbum') : t('photoLocalOnly')}
          aria-label={t('photoAddAlbum')}
          type="button"
        >
          <PlusIcon width={16} height={16} />
        </button>
      </div>

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

      {photoAlbums.length === 0 ? (
        <div className={styles.empty}>
          <FolderIcon width={28} height={28} />
          <p>
            {photoAlbumsLoading
              ? t('photoAlbumsLoading')
              : isLocalAccess ? t('photoNoAlbums') : t('photoNoAlbumsRemote')}
          </p>
          {isLocalAccess ? (
            <button className={styles.emptyBtn} onClick={handleAddAlbum} type="button">
              {t('photoAddAlbum')}
            </button>
          ) : null}
        </div>
      ) : (
        <div className={styles.list}>
          {photoAlbums.map((album) => {
            const name = album.system ? t('sourceAlbumName') : album.name;
            const isActive = album.id === currentPhotoAlbumId;
            const isAvailable = isPhotoAlbumAvailable(album);
            return (
              <div
                key={album.id}
                className={[
                  styles.album,
                  isActive ? styles.albumActive : '',
                  !isAvailable || album.scan_status === 'error' ? styles.albumError : '',
                ].filter(Boolean).join(' ')}
              >
                <button
                  className={styles.albumOpen}
                  onClick={() => void handleOpenAlbum(album)}
                  type="button"
                  disabled={!isAvailable || isBusy}
                  aria-current={isActive ? 'true' : undefined}
                  data-tooltip={!isAvailable ? t(getPhotoAlbumErrorKey(album.code)) : undefined}
                >
                  <div className={styles.cover}>
                    {isAvailable && album.cover_thumb_url ? (
                      <img src={album.cover_thumb_url} alt="" loading="lazy" decoding="async" />
                    ) : (
                      <FolderIcon width={22} height={22} />
                    )}
                  </div>

                  <div className={styles.info}>
                    <span className={styles.name} data-tooltip={name}>{name}</span>
                    <span className={styles.meta}>
                      {getAlbumMetaLabel(t, album)}
                    </span>
                  </div>

                  {isActive ? <CheckIcon className={styles.activeIcon} width={15} height={15} /> : null}
                </button>

                {isLocalAccess && !album.system ? (
                  <span className={styles.actions}>
                    <button
                      className={styles.iconBtn}
                      onClick={(event) => handleRescanAlbum(event, album)}
                      data-tooltip={t('photoRescanAlbum')}
                      aria-label={t('photoRescanAlbum')}
                      type="button"
                      disabled={isBusy}
                    >
                      <ResetIcon width={13} height={13} />
                    </button>
                    <button
                      className={[styles.iconBtn, styles.deleteBtn].join(' ')}
                      onClick={(event) => handleDeleteAlbum(event, album)}
                      data-tooltip={t('photoRemoveAlbum')}
                      aria-label={t('photoRemoveAlbum')}
                      type="button"
                      disabled={isBusy}
                    >
                      <DeleteIcon width={13} height={13} />
                    </button>
                  </span>
                ) : null}
              </div>
            );
          })}
        </div>
      )}

      <TextInputDialog
        isOpen={pathDialogOpen}
        title={t('photoAddAlbum')}
        label={t('photoPathPrompt')}
        placeholder={t('photoPathPlaceholder')}
        confirmLabel={t('photoAddAlbum')}
        isBusy={isBusy}
        onSubmit={submitAlbumPath}
        onClose={() => setPathDialogOpen(false)}
      />

      <ConfirmDialog
        isOpen={Boolean(deleteTarget)}
        title={t('photoRemoveAlbum')}
        message={deleteTarget ? t('photoAlbumDeleteConfirm', {
          name: deleteTarget.name,
        }) : ''}
        confirmLabel={t('photoRemoveAlbum')}
        isBusy={isBusy}
        danger
        onConfirm={confirmDeleteAlbum}
        onClose={() => setDeleteTarget(null)}
      />
    </section>
  );
}

function getAlbumMetaLabel(
  t: (key: string, options?: Record<string, unknown>) => string,
  album: PhotoAlbum,
) {
  if (!isPhotoAlbumAvailable(album)) return t(getPhotoAlbumErrorKey(album.code));
  if (album.scan_status === 'error') {
    return t('photoAlbumUnavailable');
  }
  if (album.scan_status === 'needs_index') {
    return t('photoAlbumNeedsIndex');
  }
  if (album.scan_status === 'indexing' || album.scan_status === 'scanning') {
    return t('photoAlbumIndexing');
  }
  if (album.scan_status === 'stale') {
    const count = album.media_count ?? album.photo_count ?? 0;
    return t('photoAlbumCachedCount', { count });
  }
  return t('photoMediaCount', { count: album.media_count ?? album.photo_count ?? 0 });
}
