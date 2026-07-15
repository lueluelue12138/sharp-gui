import { useLayoutEffect, useMemo, useRef, useState } from 'react';
import type { CSSProperties, PointerEvent as ReactPointerEvent } from 'react';

import { useTranslation } from 'react-i18next';

import {
  CheckIcon,
  CloudUploadIcon,
  FormatIcon,
  GridIcon,
  ResetIcon,
  SortIcon,
} from '@/components/common/Icons';
import { SelectMenu } from '@/components/common/SelectMenu';
import type {
  ModelAsset,
  ModelAssetDensity,
  ModelAssetFormatFilter,
  ModelAssetListCounts,
  ModelAssetSort,
  ModelAssetSourceFilter,
} from '@/types';

import styles from './ModelAssetToolbar.module.css';

export type ModelAssetToolbarMode = 'expanded' | 'compact';

interface ModelAssetToolbarProps {
  total: number;
  counts: ModelAssetListCounts;
  source: ModelAssetSourceFilter;
  format: ModelAssetFormatFilter;
  tag: string | null;
  tags: string[];
  sort: ModelAssetSort;
  density: ModelAssetDensity;
  selectedAsset: ModelAsset | null;
  selectedCount: number;
  selectionMode: boolean;
  loading: boolean;
  importing: boolean;
  canImport: boolean;
  mode: ModelAssetToolbarMode;
  onSourceChange: (source: ModelAssetSourceFilter) => void;
  onFormatChange: (format: ModelAssetFormatFilter) => void;
  onTagChange: (tag: string | null) => void;
  onSortChange: (sort: ModelAssetSort) => void;
  onDensityChange: (density: ModelAssetDensity) => void;
  onRefresh: () => void;
  onImportClick: () => void;
  onToggleSelectionMode: () => void;
  onOpenSelected: () => void;
  onExpandRequest?: () => void;
}

const sourceFilters: ModelAssetSourceFilter[] = ['all', 'generated', 'imported', 'video'];
const formatFilters: ModelAssetFormatFilter[] = ['all', 'spz', 'ply', 'splat', 'rad'];
const sortOptions: ModelAssetSort[] = [
  'modified_desc',
  'created_desc',
  'name_asc',
  'size_desc',
];
const densityOptions: ModelAssetDensity[] = ['comfortable', 'compact', 'expanded'];

function sourceLabelKey(source: ModelAssetSourceFilter): string {
  if (source === 'all') return 'modelAssetFilterAll';
  if (source === 'generated') return 'modelAssetFilterGenerated';
  if (source === 'imported') return 'modelAssetFilterImported';
  return 'modelAssetFilterVideo';
}

function sortLabelKey(sort: ModelAssetSort): string {
  if (sort === 'created_desc') return 'modelAssetSortCreated';
  if (sort === 'name_asc') return 'modelAssetSortName';
  if (sort === 'size_desc') return 'modelAssetSortSize';
  return 'modelAssetSortModified';
}

function densityLabelKey(density: ModelAssetDensity): string {
  if (density === 'compact') return 'modelAssetDensityCompact';
  if (density === 'expanded') return 'modelAssetDensityExpanded';
  return 'modelAssetDensityComfortable';
}

export function ModelAssetToolbar({
  total,
  counts,
  source,
  format,
  tag,
  tags,
  sort,
  density,
  selectedAsset,
  selectedCount,
  selectionMode,
  loading,
  importing,
  canImport,
  mode,
  onSourceChange,
  onFormatChange,
  onTagChange,
  onSortChange,
  onDensityChange,
  onRefresh,
  onImportClick,
  onToggleSelectionMode,
  onOpenSelected,
  onExpandRequest,
}: ModelAssetToolbarProps) {
  const { t } = useTranslation();
  const toolbarContentRef = useRef<HTMLDivElement | null>(null);
  const [reservedHeight, setReservedHeight] = useState<number | null>(null);
  const isExpandedMode = mode === 'expanded';

  const formatOptions = useMemo(
    () => formatFilters.map((value) => ({
      value,
      label: value === 'all' ? t('modelAssetFormatAll') : value.toUpperCase(),
    })),
    [t],
  );
  const tagOptions = useMemo(
    () => [
      { value: '', label: t('modelAssetTagAll') },
      ...tags.map((tagValue) => ({ value: tagValue, label: tagValue })),
    ],
    [tags, t],
  );
  const sortMenuOptions = useMemo(
    () => sortOptions.map((value) => ({ value, label: t(sortLabelKey(value)) })),
    [t],
  );
  const densityMenuOptions = useMemo(
    () => densityOptions.map((value) => ({ value, label: t(densityLabelKey(value)) })),
    [t],
  );
  const compactTitle = `${t('modelAssetLibraryTitle')} ${total}`;
  const selectedLabel = selectionMode
    ? t('modelAssetSelectedCount', { count: selectedCount })
    : t('select');
  const toolbarStyle = reservedHeight
    ? ({ '--toolbar-reserved-height': `${reservedHeight}px` } as CSSProperties)
    : undefined;

  useLayoutEffect(() => {
    const el = toolbarContentRef.current;
    if (!el) {
      return;
    }

    let frameId: number | null = null;
    const measure = () => {
      frameId = null;
      const nextHeight = el.offsetHeight;
      if (nextHeight <= 0) {
        return;
      }

      setReservedHeight((current) => {
        if (mode === 'compact') {
          return current ?? nextHeight;
        }
        return current === nextHeight ? current : nextHeight;
      });
    };
    const scheduleMeasure = () => {
      if (frameId !== null) {
        return;
      }
      frameId = window.requestAnimationFrame(measure);
    };

    measure();
    const observer = new ResizeObserver(scheduleMeasure);
    observer.observe(el);
    return () => {
      observer.disconnect();
      if (frameId !== null) {
        window.cancelAnimationFrame(frameId);
      }
    };
  }, [counts.all, counts.generated, counts.imported, counts.video, mode, selectedLabel, total]);

  const handleToolbarPointerDown = (event: ReactPointerEvent<HTMLElement>) => {
    if (mode !== 'compact' || !onExpandRequest) {
      return;
    }

    const target = event.target as HTMLElement;
    if (target.closest('button,input,[role="button"],[role="dialog"],[role="listbox"],a')) {
      return;
    }

    onExpandRequest();
  };

  return (
    <header
      className={[
        styles.toolbar,
        styles[mode],
      ].filter(Boolean).join(' ')}
      style={toolbarStyle}
      onPointerDown={handleToolbarPointerDown}
    >
      <div ref={toolbarContentRef} className={styles.toolbarContent}>
        <div className={styles.titleBlock}>
          <h1>{t('modelAssetLibraryTitle')}</h1>
          <span className={styles.countBadge}>{total}</span>
          <span className={styles.compactTitle}>{compactTitle}</span>
        </div>

        <div className={styles.sourceTabs} role="tablist" aria-label={t('modelAssetSourceFilter')}>
          {sourceFilters.map((sourceValue) => (
            <button
              key={sourceValue}
              className={[
                styles.sourceTab,
                source === sourceValue ? styles.sourceTabActive : '',
              ].filter(Boolean).join(' ')}
              type="button"
              role="tab"
              aria-selected={source === sourceValue}
              onClick={() => onSourceChange(sourceValue)}
            >
              <span>{t(sourceLabelKey(sourceValue))}</span>
              <span className={styles.tabCount}>{counts[sourceValue]}</span>
            </button>
          ))}
        </div>

        <div className={styles.spacer} />

        <div className={styles.controls}>
          <SelectMenu
            className={[styles.controlMenu, styles.sortMenu].join(' ')}
            value={sort}
            options={sortMenuOptions}
            onChange={(value) => onSortChange(value as ModelAssetSort)}
            ariaLabel={t('modelAssetSort')}
            icon={<SortIcon width={15} height={15} />}
            compact
            showSelectedLabel={isExpandedMode}
          />
          <SelectMenu
            className={[styles.controlMenu, styles.formatMenu].join(' ')}
            value={format}
            options={formatOptions}
            onChange={(value) => onFormatChange(value as ModelAssetFormatFilter)}
            ariaLabel={t('modelAssetFormat')}
            compact
          />
          <SelectMenu
            className={[styles.controlMenu, styles.tagMenu].join(' ')}
            value={tag ?? ''}
            options={tagOptions}
            onChange={(value) => onTagChange(value || null)}
            ariaLabel={t('modelAssetTag')}
            compact
            disabled={tags.length === 0}
          />
          <SelectMenu
            className={[styles.controlMenu, styles.densityMenu].join(' ')}
            value={density}
            options={densityMenuOptions}
            onChange={(value) => onDensityChange(value as ModelAssetDensity)}
            ariaLabel={t('modelAssetDensity')}
            icon={<GridIcon width={15} height={15} />}
            compact
            showSelectedLabel={false}
          />
          <button
            className={[styles.iconBtn, styles.refreshAction].join(' ')}
            type="button"
            aria-label={t('refresh')}
            data-tooltip={t('refresh')}
            disabled={loading}
            onClick={onRefresh}
          >
            <ResetIcon width={15} height={15} />
          </button>
          <button
            className={[styles.textBtn, styles.importAction].join(' ')}
            type="button"
            disabled={importing || !canImport}
            aria-label={canImport ? t('modelAssetImport') : t('modelAssetWritePermissionRequired')}
            data-tooltip={canImport ? t('modelAssetImport') : t('modelAssetWritePermissionRequired')}
            onClick={onImportClick}
          >
            <CloudUploadIcon width={15} height={15} />
            <span>{t('modelAssetImport')}</span>
          </button>
          <button
            className={[
              styles.textBtn,
              styles.selectAction,
              selectionMode ? styles.textBtnActive : '',
            ].filter(Boolean).join(' ')}
            type="button"
            tabIndex={isExpandedMode ? undefined : -1}
            aria-hidden={!isExpandedMode}
            onClick={onToggleSelectionMode}
          >
            <CheckIcon width={15} height={15} />
            <span>{selectedLabel}</span>
          </button>
          <button
            className={[styles.textBtn, styles.openAction].join(' ')}
            type="button"
            disabled={!selectedAsset?.available}
            onClick={onOpenSelected}
          >
            <FormatIcon width={15} height={15} />
            <span>{t('open')}</span>
          </button>
        </div>
      </div>
    </header>
  );
}
