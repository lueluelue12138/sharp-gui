import { useMemo, useRef, useState } from 'react';

import { useTranslation } from 'react-i18next';

import { Button } from '@/components/common/Button';
import {
  CloudUploadIcon,
  CloseIcon,
  DeleteIcon,
  DownloadIcon,
  FormatIcon,
  ResetIcon,
  ShareIcon,
} from '@/components/common/Icons';
import { formatDate, formatFileSize, resolveModelAssetSource } from '@/utils';
import type { ModelAsset, ModelAssetProfileInput, ModelFormat } from '@/types';

import styles from './ModelAssetDetailsPanel.module.css';

interface ModelAssetDetailsPanelProps {
  asset: ModelAsset | null;
  saving: boolean;
  canWrite: boolean;
  canDelete: boolean;
  preferredFormat: ModelFormat;
  onOpen: (asset: ModelAsset) => void;
  onPreviewSource: (asset: ModelAsset) => void;
  onDownload: (asset: ModelAsset) => void;
  onExport: (asset: ModelAsset) => void;
  onDelete: (asset: ModelAsset) => void;
  onSaveProfile: (asset: ModelAsset, profile: ModelAssetProfileInput) => void;
  onUploadCover: (asset: ModelAsset, file: File) => void;
  onRefreshCover: (asset: ModelAsset) => void;
  onClose?: () => void;
}

type DetailsTab = 'details' | 'metadata';

function getCoverSrc(asset: ModelAsset): string | null {
  if (!asset.thumb_url) {
    return null;
  }
  if (asset.thumb_version == null) {
    return asset.thumb_url;
  }
  const separator = asset.thumb_url.includes('?') ? '&' : '?';
  return `${asset.thumb_url}${separator}v=${asset.thumb_version}`;
}

function formatFieldValue(value: unknown, fallback: string): string {
  if (value == null || value === '') {
    return fallback;
  }
  if (Array.isArray(value)) {
    return value.length > 0 ? value.join(', ') : fallback;
  }
  if (typeof value === 'object') {
    return JSON.stringify(value);
  }
  return String(value);
}

export function ModelAssetDetailsPanel({
  asset,
  saving,
  canWrite,
  canDelete,
  preferredFormat,
  onOpen,
  onPreviewSource,
  onDownload,
  onExport,
  onDelete,
  onSaveProfile,
  onUploadCover,
  onRefreshCover,
  onClose,
}: ModelAssetDetailsPanelProps) {
  const { t } = useTranslation();
  const coverInputRef = useRef<HTMLInputElement | null>(null);
  const [activeTab, setActiveTab] = useState<DetailsTab>('details');
  const [isEditing, setIsEditing] = useState(false);
  const [nameDraft, setNameDraft] = useState(asset?.name ?? '');
  const [tagsDraft, setTagsDraft] = useState(asset?.tags.join(', ') ?? '');
  const [noteDraft, setNoteDraft] = useState(asset?.note ?? '');

  const coverSrc = asset ? getCoverSrc(asset) : null;
  const modelSource = asset ? resolveModelAssetSource(asset, preferredFormat) : null;
  const modelFile = modelSource?.file ?? asset?.files?.find((file) => file.primary) ?? asset?.files?.[0];
  const displaySize = modelSource?.size ?? asset?.primary_size ?? asset?.size ?? 0;
  const primaryFormat = (modelSource?.format ?? asset?.primary_format ?? asset?.formats?.[0] ?? 'ply').toUpperCase();
  const hasSourcePreview = Boolean(asset?.image_url || asset?.source_video_url);
  const fields = useMemo(() => {
    if (!asset) {
      return [];
    }
    return [
      [t('modelAssetFileName'), modelFile?.filename ?? asset.name],
      [t('modelAssetFormat'), asset.formats.map((format) => format.toUpperCase()).join(', ')],
      [t('modelAssetSource'), t(`modelAssetSource${asset.source_type[0].toUpperCase()}${asset.source_type.slice(1)}`)],
      [t('modelAssetCreated'), asset.created_at ? formatDate(asset.created_at) : t('modelAssetUnknown')],
      [t('modelAssetModified'), asset.updated_at ? formatDate(asset.updated_at) : t('modelAssetUnknown')],
      [t('modelAssetSize'), formatFileSize(displaySize)],
      [t('modelAssetPoints'), formatFieldValue(asset.point_count, t('modelAssetUnknown'))],
      [t('modelAssetBoundingBox'), formatFieldValue(asset.bounding_box, t('modelAssetUnknown'))],
      [t('modelAssetCoordinateSystem'), asset.coordinate_system || t('modelAssetUnknown')],
      [t('modelAssetAttributes'), formatFieldValue(asset.attributes, t('modelAssetUnknown'))],
      [t('modelAssetCompression'), asset.compression || t('modelAssetUnknown')],
      [t('modelAssetVersion'), asset.version || t('modelAssetUnknown')],
      [t('modelAssetDescription'), asset.note || t('modelAssetNoDescription')],
    ];
  }, [asset, displaySize, modelFile?.filename, t]);

  const metadataEntries = useMemo(() => {
    if (!asset?.metadata) {
      return [];
    }
    return Object.entries(asset.metadata)
      .filter(([, value]) => value != null && value !== '')
      .slice(0, 24);
  }, [asset]);

  const handleSave = () => {
    if (!asset) {
      return;
    }
    onSaveProfile(asset, {
      display_name: nameDraft,
      tags: tagsDraft
        .split(',')
        .map((tag) => tag.trim())
        .filter(Boolean),
      note: noteDraft,
    });
  };

  const handleCoverChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (asset && file) {
      onUploadCover(asset, file);
    }
    event.target.value = '';
  };

  if (!asset) {
    return (
      <aside className={styles.panel}>
        <div className={styles.emptyPanel}>
          <div className={styles.emptyCube}>{t('modelAssetNoSelectionIcon')}</div>
          <h2>{t('modelAssetNoSelectionTitle')}</h2>
          <p>{t('modelAssetNoSelectionHint')}</p>
        </div>
      </aside>
    );
  }

  return (
    <aside className={styles.panel}>
      {onClose ? (
        <button
          className={styles.closeButton}
          type="button"
          aria-label={t('close')}
          data-tooltip={t('close')}
          onPointerDown={(event) => event.stopPropagation()}
          onClick={(event) => {
            event.stopPropagation();
            onClose();
          }}
        >
          <CloseIcon width={14} height={14} />
        </button>
      ) : null}

      <div className={styles.preview}>
        {hasSourcePreview ? (
          <button
            className={styles.previewMediaButton}
            type="button"
            aria-label={t('modelAssetPreview')}
            data-tooltip={t('modelAssetPreview')}
            onClick={() => onPreviewSource(asset)}
          >
            {coverSrc ? (
              <img src={coverSrc} alt={asset.name} className={styles.previewImage} />
            ) : (
              <div className={styles.previewFallback}>{primaryFormat}</div>
            )}
          </button>
        ) : (
          <div className={styles.previewMediaSurface}>
            {coverSrc ? (
              <img src={coverSrc} alt={asset.name} className={styles.previewImage} />
            ) : (
              <div className={styles.previewFallback}>{primaryFormat}</div>
            )}
          </div>
        )}
        {canWrite ? (
          <button
            className={styles.coverButton}
            type="button"
            onPointerDown={(event) => event.stopPropagation()}
            onClick={(event) => {
              event.stopPropagation();
              coverInputRef.current?.click();
            }}
            aria-label={t('modelAssetUploadCover')}
            data-tooltip={t('modelAssetUploadCover')}
          >
            <CloudUploadIcon width={15} height={15} />
          </button>
        ) : null}
        {canWrite && asset.thumbnail_kind === 'manual' ? (
          <button
            className={`${styles.coverButton} ${styles.restoreCoverButton}`}
            type="button"
            onPointerDown={(event) => event.stopPropagation()}
            onClick={(event) => {
              event.stopPropagation();
              onRefreshCover(asset);
            }}
            aria-label={t('modelAssetRestoreSystemCover')}
            data-tooltip={t('modelAssetRestoreSystemCover')}
          >
            <ResetIcon width={15} height={15} />
          </button>
        ) : null}
        <input
          ref={coverInputRef}
          type="file"
          accept="image/png,image/jpeg,image/webp"
          hidden
          onChange={handleCoverChange}
        />
      </div>

      <div className={styles.header}>
        {isEditing && canWrite ? (
          <div className={styles.editStack}>
            <label>
              <span>{t('modelAssetName')}</span>
              <input
                value={nameDraft}
                onChange={(event) => setNameDraft(event.target.value)}
                maxLength={120}
              />
            </label>
            <label>
              <span>{t('modelAssetTags')}</span>
              <input
                value={tagsDraft}
                onChange={(event) => setTagsDraft(event.target.value)}
                placeholder={t('modelAssetTagsPlaceholder')}
              />
            </label>
            <label>
              <span>{t('modelAssetNotes')}</span>
              <textarea
                value={noteDraft}
                onChange={(event) => setNoteDraft(event.target.value)}
                rows={3}
              />
            </label>
            <div className={styles.editActions}>
              <Button size="sm" variant="secondary" onClick={() => setIsEditing(false)}>
                {t('cancel')}
              </Button>
              <Button size="sm" onClick={handleSave} disabled={saving}>
                {saving ? t('saving') : t('save')}
              </Button>
            </div>
          </div>
        ) : (
          <>
            <div className={styles.titleRow}>
              <h2>{asset.name}</h2>
              {canWrite ? (
                <button
                  className={styles.editButton}
                  type="button"
                  onClick={() => setIsEditing(true)}
                  aria-label={t('edit')}
                >
                  {t('edit')}
                </button>
              ) : null}
            </div>
            <div className={styles.summary}>
              <span>{primaryFormat}</span>
              <span>{formatFileSize(displaySize)}</span>
              <span>{t(`modelAssetSource${asset.source_type[0].toUpperCase()}${asset.source_type.slice(1)}`)}</span>
            </div>
          </>
        )}
      </div>

      <div className={styles.actions}>
        <Button size="sm" variant="secondary" icon={<FormatIcon />} disabled={!asset.available} onClick={() => onOpen(asset)}>
          {t('open')}
        </Button>
        <Button size="sm" variant="secondary" icon={<DownloadIcon />} disabled={!asset.available} onClick={() => onDownload(asset)}>
          {t('download')}
        </Button>
        <Button
          size="sm"
          variant="secondary"
          icon={<ShareIcon />}
          disabled={!asset.available || !asset.is_generated}
          title={asset.is_generated ? t('export') : t('modelAssetExportUnavailable')}
          onClick={() => onExport(asset)}
        >
          {t('export')}
        </Button>
        {canDelete ? (
          <Button
            size="sm"
            variant="secondary"
            className={styles.dangerAction}
            icon={<DeleteIcon />}
            onClick={() => onDelete(asset)}
          >
            {t('delete')}
          </Button>
        ) : (
          <Button
            size="sm"
            variant="secondary"
            icon={<DeleteIcon />}
            disabled
            title={t('modelAssetDeletePermissionRequired')}
          >
            {t('delete')}
          </Button>
        )}
      </div>

      <div className={styles.tabs} role="tablist" aria-label={t('modelAssetDetailsTabs')}>
        <button
          type="button"
          className={activeTab === 'details' ? styles.tabActive : ''}
          role="tab"
          aria-selected={activeTab === 'details'}
          onClick={() => setActiveTab('details')}
        >
          {t('modelAssetDetails')}
        </button>
        <button
          type="button"
          className={activeTab === 'metadata' ? styles.tabActive : ''}
          role="tab"
          aria-selected={activeTab === 'metadata'}
          onClick={() => setActiveTab('metadata')}
        >
          {t('modelAssetMetadata')}
        </button>
      </div>

      <div className={styles.detailBody}>
        {activeTab === 'details' ? (
          <dl className={styles.fieldList}>
            {fields.map(([label, value]) => (
              <div key={label} className={styles.fieldRow}>
                <dt>{label}</dt>
                <dd>{value}</dd>
              </div>
            ))}
          </dl>
        ) : (
          <dl className={styles.fieldList}>
            {metadataEntries.length > 0 ? metadataEntries.map(([key, value]) => (
              <div key={key} className={styles.fieldRow}>
                <dt>{key}</dt>
                <dd>{formatFieldValue(value, t('modelAssetUnknown'))}</dd>
              </div>
            )) : (
              <div className={styles.metadataEmpty}>{t('modelAssetNoMetadata')}</div>
            )}
          </dl>
        )}
      </div>
    </aside>
  );
}
