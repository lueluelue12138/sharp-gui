import { memo, useMemo, useState } from 'react';
import type { CSSProperties } from 'react';

import { useTranslation } from 'react-i18next';

import {
  CheckIcon,
  GalleryIcon,
  PlayIcon,
  SparklesIcon,
} from '@/components/common/Icons';
import type { PhotoItem, PhotoMediaType } from '@/types';
import { SourceModelBadge } from '@/components/photoGallery/SourceModelBadge';
import { useAppStore } from '@/store';

import styles from './PhotoMasonryGrid.module.css';

interface PhotoMasonryGridProps {
  items: PhotoItem[];
  isLoading: boolean;
  selectionMode: boolean;
  selectedPhotoIds: string[];
  columns: number;
  mediaType: PhotoMediaType;
  onOpenPhoto: (photo: PhotoItem) => void;
  onTogglePhoto: (photoId: string) => void;
  onConvertPhoto: (photo: PhotoItem) => void;
  onReconstructVideo: (photo: PhotoItem) => void;
}

export const PhotoMasonryGrid = memo(function PhotoMasonryGrid({
  items,
  isLoading,
  selectionMode,
  selectedPhotoIds,
  columns,
  mediaType,
  onOpenPhoto,
  onTogglePhoto,
  onConvertPhoto,
  onReconstructVideo,
}: PhotoMasonryGridProps) {
  const { t } = useTranslation();
  const links = useAppStore((state) => state.modelSourceLinks);
  const [failedThumbIds, setFailedThumbIds] = useState<Set<string>>(() => new Set());
  const columnCount = Math.max(1, Math.floor(columns));
  const columnItems = useMemo(() => {
    const nextColumns = Array.from({ length: columnCount }, () => [] as PhotoItem[]);
    items.forEach((photo, index) => {
      nextColumns[index % columnCount].push(photo);
    });
    return nextColumns;
  }, [columnCount, items]);

  if (!isLoading && items.length === 0) {
    const emptyTitle = mediaType === 'video'
      ? t('photoVideoGridEmptyTitle')
      : mediaType === 'image'
        ? t('photoGridEmptyTitle')
        : t('photoMediaGridEmptyTitle');
    const emptyHint = mediaType === 'video'
      ? t('photoVideoGridEmptyHint')
      : mediaType === 'image'
        ? t('photoGridEmptyHint')
        : t('photoMediaGridEmptyHint');

    return (
      <div className={styles.empty}>
        <GalleryIcon width={42} height={42} />
        <h2>{emptyTitle}</h2>
        <p>{emptyHint}</p>
      </div>
    );
  }

  const rootStyle = {
    '--photo-grid-columns': String(columnCount),
  } as CSSProperties;

  return (
    <div className={styles.root} style={rootStyle} aria-label={t('photoGrid')} role="list">
      {columnItems.map((column, columnIndex) => (
        <div className={styles.column} key={`photo-column-${columnIndex}`} role="presentation">
          {column.map((photo) => {
            const isSelected = selectedPhotoIds.includes(photo.id);
            const isVideo = photo.media_type === 'video';
            const thumbUrl = photo.thumb_url ?? undefined;
            const hasThumb = Boolean(thumbUrl) && !failedThumbIds.has(photo.id);
            const ratio = photo.width && photo.height
              ? `${photo.width} / ${photo.height}`
              : isVideo ? '16 / 9' : '4 / 3';
            const durationLabel = isVideo && typeof photo.duration === 'number'
              ? formatDuration(photo.duration)
              : null;
            const specLabel = isVideo
              ? getVideoSpecLabel(photo)
              : null;

            return (
              <article
                key={photo.id}
                className={[
                  styles.card,
                  isVideo ? styles.videoCard : '',
                  isSelected ? styles.selected : '',
                ].filter(Boolean).join(' ')}
                style={{ aspectRatio: ratio }}
                role="listitem"
              >
                <SourceModelBadge item={photo} />
                <button
                  className={styles.imageBtn}
                  onClick={() => selectionMode ? onTogglePhoto(photo.id) : onOpenPhoto(photo)}
                  type="button"
                  aria-label={selectionMode ? t('photoToggleSelection', { name: photo.name }) : t('photoOpen', { name: photo.name })}
                >
                  {hasThumb ? (
                    <img
                      src={thumbUrl}
                      alt={photo.name}
                      loading="lazy"
                      decoding="async"
                      draggable={false}
                      onError={() => {
                        setFailedThumbIds((current) => {
                          if (current.has(photo.id)) {
                            return current;
                          }
                          const next = new Set(current);
                          next.add(photo.id);
                          return next;
                        });
                      }}
                    />
                  ) : (
                    <span className={[styles.fallback, isVideo ? styles.videoFallback : ''].filter(Boolean).join(' ')}>
                      {isVideo ? <PlayIcon width={24} height={24} /> : null}
                      <span>{isVideo ? t('photoVideoPosterUnavailable') : t('galleryThumbUnavailableShort')}</span>
                    </span>
                  )}
                  {isVideo ? (
                    <>
                      <span className={styles.playBadge} aria-hidden="true">
                        <PlayIcon width={18} height={18} />
                      </span>
                      <span className={styles.videoMetaPill}>
                        {durationLabel ?? t('photoVideo')}
                      </span>
                    </>
                  ) : null}
                </button>

                <div className={styles.topActions}>
                  <button
                    className={[
                      styles.selectBtn,
                      isSelected ? styles.selectBtnActive : '',
                    ].filter(Boolean).join(' ')}
                    onClick={() => onTogglePhoto(photo.id)}
                    type="button"
                    data-tooltip={t('photoSelect')}
                    aria-label={t('photoToggleSelection', { name: photo.name })}
                  >
                    {isSelected ? <CheckIcon width={14} height={14} /> : null}
                  </button>
                </div>

                <div className={styles.footer}>
                  <span className={styles.footerText}>
                    <span data-tooltip={photo.name}>{photo.name}</span>
                    {specLabel ? <small data-tooltip={specLabel}>{specLabel}</small> : null}
                  </span>
                  {(links[photo.id]?.total_count ?? photo.model_link?.total_count ?? 0) > 0 ? null : isVideo ? (
                    <button
                      className={styles.convertBtn}
                      onClick={() => onReconstructVideo(photo)}
                      type="button"
                      data-tooltip={t('videoReconGenerate3d')}
                      aria-label={t('videoReconGenerate3d')}
                    >
                      <SparklesIcon width={14} height={14} />
                    </button>
                  ) : (
                    <button
                      className={styles.convertBtn}
                      onClick={() => onConvertPhoto(photo)}
                      type="button"
                      data-tooltip={t('photoConvertOne')}
                      aria-label={t('photoConvertOne')}
                    >
                      <SparklesIcon width={14} height={14} />
                    </button>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      ))}

      {isLoading ? (
        <div className={styles.loadingRow} aria-hidden="true">
          {Array.from({ length: Math.min(columnCount, 3) }, (_, index) => (
            <div className={styles.skeleton} key={`photo-skeleton-${index}`} />
          ))}
        </div>
      ) : null}
    </div>
  );
});

PhotoMasonryGrid.displayName = 'PhotoMasonryGrid';

function formatDuration(durationSeconds: number): string {
  const totalSeconds = Math.max(0, Math.round(durationSeconds));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
  }
  return `${minutes}:${String(seconds).padStart(2, '0')}`;
}

function getVideoSpecLabel(photo: PhotoItem): string | null {
  const resolution = photo.width && photo.height ? `${photo.width} × ${photo.height}` : null;
  const codec = photo.video_codec ? photo.video_codec.toUpperCase() : null;
  if (resolution && codec) {
    return `${resolution} · ${codec}`;
  }
  return resolution ?? codec;
}
