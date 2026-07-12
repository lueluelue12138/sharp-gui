import type { RefObject } from 'react';

import { useTranslation } from 'react-i18next';

import { ModelAssetCard } from '@/components/modelAssets/ModelAssetCard';
import type { ModelAsset, ModelAssetDensity, ModelFormat } from '@/types';

import styles from './ModelAssetGrid.module.css';

interface ModelAssetGridProps {
  assets: ModelAsset[];
  density: ModelAssetDensity;
  loading: boolean;
  selectedId: string | null;
  selectionMode: boolean;
  selectedIds: string[];
  openOnCardClick: boolean;
  preferredFormat: ModelFormat;
  scrollElementRef: RefObject<HTMLDivElement | null>;
  onSelect: (asset: ModelAsset) => void;
  onToggleChecked: (asset: ModelAsset) => void;
  onOpen: (asset: ModelAsset) => void;
  onShowDetails: (asset: ModelAsset) => void;
  onPreview: (asset: ModelAsset) => void;
  onDownload: (asset: ModelAsset) => void;
  onDelete: (asset: ModelAsset) => void;
  onScroll: (event: React.UIEvent<HTMLDivElement>) => void;
}

export function ModelAssetGrid({
  assets,
  density,
  loading,
  selectedId,
  selectionMode,
  selectedIds,
  openOnCardClick,
  preferredFormat,
  scrollElementRef,
  onSelect,
  onToggleChecked,
  onOpen,
  onShowDetails,
  onPreview,
  onDownload,
  onDelete,
  onScroll,
}: ModelAssetGridProps) {
  const { t } = useTranslation();
  const gridClasses = [
    styles.grid,
    density === 'compact' ? styles.compact : '',
    density === 'expanded' ? styles.expanded : '',
  ].filter(Boolean).join(' ');

  if (!loading && assets.length === 0) {
    return (
      <div className={styles.emptyState}>
        <div className={styles.emptyIcon}>3D</div>
        <h2>{t('modelAssetEmptyTitle')}</h2>
        <p>{t('modelAssetEmptyHint')}</p>
      </div>
    );
  }

  return (
    <div ref={scrollElementRef} className={styles.root} onScroll={onScroll}>
      <div className={gridClasses} role="list" aria-label={t('modelAssetGrid')}>
        {assets.map((asset) => (
          <ModelAssetCard
            key={asset.id}
            asset={asset}
            isSelected={selectedId === asset.id}
            isChecked={selectedIds.includes(asset.id)}
            selectionMode={selectionMode}
            openOnClick={openOnCardClick}
            preferredFormat={preferredFormat}
            onSelect={onSelect}
            onToggleChecked={onToggleChecked}
            onOpen={onOpen}
            onShowDetails={onShowDetails}
            onPreview={onPreview}
            onDownload={onDownload}
            onDelete={onDelete}
          />
        ))}
        {loading ? (
          Array.from({ length: 8 }).map((_, index) => (
            <div key={`skeleton-${index}`} className={styles.skeletonCard} aria-hidden="true" />
          ))
        ) : null}
      </div>

    </div>
  );
}
