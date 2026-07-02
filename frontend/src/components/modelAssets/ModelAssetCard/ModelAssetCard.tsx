import { useTranslation } from 'react-i18next';

import {
  CheckIcon,
  DeleteIcon,
  DownloadIcon,
  EyeIcon,
  InfoIcon,
} from '@/components/common/Icons';
import { useGalleryThumbnail } from '@/hooks/useGalleryThumbnail';
import { formatDate, formatFileSize, resolveModelAssetSource } from '@/utils';
import type { ModelAsset, ModelFormat } from '@/types';

import styles from './ModelAssetCard.module.css';

interface ModelAssetCardProps {
  asset: ModelAsset;
  isSelected: boolean;
  isChecked: boolean;
  selectionMode: boolean;
  openOnClick: boolean;
  preferredFormat: ModelFormat;
  onSelect: (asset: ModelAsset) => void;
  onToggleChecked: (asset: ModelAsset) => void;
  onOpen: (asset: ModelAsset) => void;
  onShowDetails: (asset: ModelAsset) => void;
  onPreview: (asset: ModelAsset) => void;
  onDownload: (asset: ModelAsset) => void;
  onDelete: (asset: ModelAsset) => void;
}

function getThumbnailSrc(asset: ModelAsset): string | null {
  if (!asset.thumb_url) {
    return null;
  }
  if (asset.thumb_version == null) {
    return asset.thumb_url;
  }
  const separator = asset.thumb_url.includes('?') ? '&' : '?';
  return `${asset.thumb_url}${separator}v=${asset.thumb_version}`;
}

export function ModelAssetCard({
  asset,
  isSelected,
  isChecked,
  selectionMode,
  openOnClick,
  preferredFormat,
  onSelect,
  onToggleChecked,
  onOpen,
  onShowDetails,
  onPreview,
  onDownload,
  onDelete,
}: ModelAssetCardProps) {
  const { t } = useTranslation();
  const thumbnailSrc = getThumbnailSrc(asset);
  const thumbnailState = useGalleryThumbnail(thumbnailSrc, Boolean(thumbnailSrc));
  const hasPreview = Boolean(asset.image_url || asset.source_video_url);
  const modelSource = resolveModelAssetSource(asset, preferredFormat);
  const formatLabel = (modelSource.format ?? asset.primary_format ?? asset.formats[0] ?? 'ply').toUpperCase();
  const sourceLabel = t(`modelAssetSource${asset.source_type[0].toUpperCase()}${asset.source_type.slice(1)}`);
  const updatedText = asset.updated_at ? formatDate(asset.updated_at) : t('modelAssetUnknown');
  const metaText = [
    formatFileSize(modelSource.size),
    sourceLabel,
    updatedText,
  ].join(' · ');
  const unavailable = !asset.available;

  const handleActionClick = (
    event: React.MouseEvent<HTMLButtonElement>,
    action: (target: ModelAsset) => void,
  ) => {
    event.stopPropagation();
    action(asset);
  };

  const handleSelect = () => {
    if (selectionMode) {
      onToggleChecked(asset);
      return;
    }
    onSelect(asset);
    if (openOnClick) {
      onOpen(asset);
    }
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      handleSelect();
    }
  };

  return (
    <div
      className={[
        styles.card,
        isSelected ? styles.selected : '',
        isChecked ? styles.checked : '',
        unavailable ? styles.unavailable : '',
      ].filter(Boolean).join(' ')}
      onClick={handleSelect}
      onKeyDown={handleKeyDown}
      role="button"
      tabIndex={0}
      aria-pressed={isSelected}
      aria-label={asset.name}
    >
      <div className={styles.thumbArea}>
        {thumbnailSrc && thumbnailState !== 'error' && thumbnailState !== 'missing' ? (
          <img
            className={[
              styles.thumb,
              thumbnailState === 'ready' ? styles.thumbReady : '',
            ].filter(Boolean).join(' ')}
            src={thumbnailSrc}
            alt={asset.name}
            loading="lazy"
            decoding="async"
            draggable={false}
          />
        ) : null}

        {thumbnailState === 'loading' ? <div className={styles.loadingCover} aria-hidden="true" /> : null}

        {!thumbnailSrc || thumbnailState === 'missing' || thumbnailState === 'error' ? (
          <div className={styles.coverFallback}>
            <span>{formatLabel}</span>
          </div>
        ) : null}

        <span className={styles.formatBadge}>{formatLabel}</span>

        {isChecked ? (
          <span className={styles.checkBadge} aria-hidden="true">
            <CheckIcon width={14} height={14} />
          </span>
        ) : null}

        <div className={styles.quickActions}>
          {hasPreview ? (
            <button
              className={styles.actionButton}
              type="button"
              aria-label={t('modelAssetPreview')}
              data-tooltip={t('modelAssetPreview')}
              onClick={(event) => handleActionClick(event, onPreview)}
            >
              <EyeIcon width={15} height={15} />
            </button>
          ) : null}
          <button
            className={styles.actionButton}
            type="button"
            aria-label={t('showDetails')}
            data-tooltip={t('showDetails')}
            onClick={(event) => handleActionClick(event, onShowDetails)}
          >
            <InfoIcon width={15} height={15} />
          </button>
          <button
            className={styles.actionButton}
            type="button"
            aria-label={t('download')}
            data-tooltip={t('download')}
            disabled={unavailable}
            onClick={(event) => handleActionClick(event, onDownload)}
          >
            <DownloadIcon width={15} height={15} />
          </button>
          <button
            className={[styles.actionButton, styles.deleteButton].join(' ')}
            type="button"
            aria-label={t('delete')}
            data-tooltip={t('delete')}
            onClick={(event) => handleActionClick(event, onDelete)}
          >
            <DeleteIcon width={15} height={15} />
          </button>
        </div>
      </div>

      <div className={styles.cardInfo}>
        <h3 className={styles.name} data-tooltip={asset.name}>{asset.name}</h3>
        <p className={styles.meta} data-tooltip={metaText}>{metaText}</p>
      </div>
    </div>
  );
}
