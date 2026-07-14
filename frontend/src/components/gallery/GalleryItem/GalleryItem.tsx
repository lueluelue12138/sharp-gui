import { memo } from 'react';

import { useTranslation } from 'react-i18next';

import { EyeIcon, DownloadIcon, DeleteIcon } from '@/components/common/Icons';
import { useGalleryThumbnail } from '@/hooks/useGalleryThumbnail';
import {
  formatFileSize,
  getGalleryModelSource,
  getGallerySourceVideoUrl,
  getGalleryThumbnailSrc,
} from '@/utils';
import type { GalleryItem as GalleryItemType, ModelFormat } from '@/types';

import styles from './GalleryItem.module.css';

interface GalleryItemProps {
  item: GalleryItemType;
  preferredFormat: ModelFormat;
  isActive: boolean;
  onSelect: (item: GalleryItemType) => void;
  onPreview: (item: GalleryItemType) => void;
  onDownload: (item: GalleryItemType) => void;
  onDelete: (item: GalleryItemType) => void;
}

export const GalleryItem = memo(function GalleryItem({
  item,
  preferredFormat,
  isActive,
  onSelect,
  onPreview,
  onDownload,
  onDelete,
}: GalleryItemProps) {
  const { t } = useTranslation();

  const thumbnailSrc = getGalleryThumbnailSrc(item);
  const sourceVideoUrl = getGallerySourceVideoUrl(item);
  const hasOriginalPreview = Boolean(item.image_url || sourceVideoUrl);
  const thumbnailState = useGalleryThumbnail(thumbnailSrc, Boolean(thumbnailSrc));
  const modelSource = getGalleryModelSource(item, preferredFormat);
  const displaySize = modelSource.size ?? item.size;
  const formatLabel = (modelSource.format ?? 'ply').toUpperCase();
  const thumbnailStatusText =
    thumbnailState === 'loading'
      ? t('galleryThumbLoading')
      : thumbnailState === 'error'
        ? t('galleryThumbFailed')
        : thumbnailState === 'missing'
          ? t('galleryThumbUnavailable')
          : null;
  const metaText = [
    displaySize ? formatFileSize(displaySize) : t('ready'),
    formatLabel,
    thumbnailStatusText,
  ].filter(Boolean).join(' · ');
  const thumbnailFallbackLabel =
    thumbnailState === 'error'
      ? t('galleryThumbFailedShort')
      : t('galleryThumbUnavailableShort');
  const thumbnailAriaLabel =
    thumbnailState === 'ready'
      ? item.name
      : `${item.name} · ${thumbnailStatusText ?? thumbnailFallbackLabel}`;

  const handleButtonClick = (
    event: React.MouseEvent<HTMLButtonElement>,
    action: (galleryItem: GalleryItemType) => void,
  ) => {
    event.stopPropagation();
    action(item);
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      onSelect(item);
    }
  };

  return (
    <div
      className={[styles.item, isActive ? styles.active : ''].filter(Boolean).join(' ')}
      onClick={() => onSelect(item)}
      onKeyDown={handleKeyDown}
      role="button"
      tabIndex={0}
      aria-current={isActive ? 'true' : undefined}
    >
      <div className={styles.thumbShell}>
        {thumbnailSrc && thumbnailState !== 'error' && thumbnailState !== 'missing' ? (
          <img
            src={thumbnailSrc}
            alt={item.name}
            className={[
              styles.thumbImage,
              thumbnailState === 'ready' ? styles.thumbImageReady : '',
            ].filter(Boolean).join(' ')}
            loading="eager"
            decoding="async"
            draggable={false}
          />
        ) : null}

        {thumbnailState === 'loading' ? (
          <div
            className={[styles.thumbPlaceholder, styles.thumbLoading].join(' ')}
            aria-hidden="true"
          />
        ) : null}

        {thumbnailState === 'missing' || thumbnailState === 'error' ? (
          <div
            className={[
              styles.thumbFallback,
              thumbnailState === 'error' ? styles.thumbError : styles.thumbMissing,
            ].join(' ')}
            role="img"
            aria-label={thumbnailAriaLabel}
            data-tooltip={thumbnailStatusText ?? thumbnailFallbackLabel}
          >
            <span>{thumbnailFallbackLabel}</span>
          </div>
        ) : null}
      </div>

      <div className={styles.info}>
        <div className={styles.name} data-tooltip={item.name}>{item.name}</div>
        <div className={styles.meta} data-tooltip={metaText}>{metaText}</div>
      </div>

      {hasOriginalPreview ? (
        <button
          className={styles.actionBtn}
          onClick={(event) => handleButtonClick(event, onPreview)}
          aria-label={sourceVideoUrl ? t('viewOriginalVideo') : t('viewOriginal')}
          data-tooltip={sourceVideoUrl ? t('viewOriginalVideo') : t('viewOriginal')}
          type="button"
        >
          <EyeIcon width={14} height={14} />
        </button>
      ) : null}

      <button
        className={styles.actionBtn}
        onClick={(event) => handleButtonClick(event, onDownload)}
        aria-label={t('download')}
        data-tooltip={t('download')}
        type="button"
      >
        <DownloadIcon width={14} height={14} />
      </button>

      <button
        className={[styles.actionBtn, styles.deleteBtn].join(' ')}
        onClick={(event) => handleButtonClick(event, onDelete)}
        aria-label={t('delete')}
        data-tooltip={t('delete')}
        type="button"
      >
        <DeleteIcon width={14} height={14} />
      </button>
    </div>
  );
});

GalleryItem.displayName = 'GalleryItem';
