import { useTranslation } from 'react-i18next';

import { DeleteIcon, DownloadIcon } from '@/components/common/Icons';
import { SelectionActionBar } from '@/components/common/SelectionActionBar';
import type { SelectionActionBarAction } from '@/components/common/SelectionActionBar';

import styles from './ModelAssetSelectionBar.module.css';

interface ModelAssetSelectionBarProps {
  selectedCount: number;
  downloadableCount: number;
  canDelete: boolean;
  isDownloading: boolean;
  isDeleting: boolean;
  onDownload: () => void;
  onDelete: () => void;
  onClear: () => void;
}

export function ModelAssetSelectionBar({
  selectedCount,
  downloadableCount,
  canDelete,
  isDownloading,
  isDeleting,
  onDownload,
  onDelete,
  onClear,
}: ModelAssetSelectionBarProps) {
  const { t } = useTranslation();
  const downloadLabel = isDownloading
    ? t('modelAssetDownloadingSelected')
    : t('modelAssetDownloadSelectedShort', { count: downloadableCount });
  const actions: SelectionActionBarAction[] = [
    {
      id: 'download-models',
      icon: <DownloadIcon width={16} height={16} />,
      label: downloadLabel,
      ariaLabel: downloadLabel,
      tooltip: downloadableCount > 0 ? downloadLabel : t('modelAssetDownloadNoneAvailable'),
      disabled: isDownloading || isDeleting || downloadableCount === 0,
      busy: isDownloading,
      variant: 'primary',
      onClick: onDownload,
    },
  ];

  if (canDelete) {
    const deleteLabel = isDeleting
      ? t('modelAssetDeletingSelected')
      : t('modelAssetDeleteSelected', { count: selectedCount });
    actions.push({
      id: 'delete-models',
      icon: <DeleteIcon width={16} height={16} />,
      ariaLabel: deleteLabel,
      tooltip: deleteLabel,
      disabled: isDownloading || isDeleting,
      busy: isDeleting,
      variant: 'danger',
      onClick: onDelete,
    });
  }

  return (
    <SelectionActionBar
      className={styles.bar}
      selectedCount={selectedCount}
      selectedLabel={t('modelAssetSelectedLabel')}
      countAriaLabel={t('modelAssetSelectedCount', { count: selectedCount })}
      actions={actions}
      clearLabel={t('modelAssetClearSelection')}
      onClear={onClear}
    />
  );
}
