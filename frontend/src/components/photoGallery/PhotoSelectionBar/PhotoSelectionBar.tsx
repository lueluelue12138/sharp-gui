import { useTranslation } from 'react-i18next';

import { DownloadIcon, SparklesIcon } from '@/components/common/Icons';
import { SelectionActionBar } from '@/components/common/SelectionActionBar';
import type { SelectionActionBarAction } from '@/components/common/SelectionActionBar';

interface PhotoSelectionBarProps {
  selectedCount: number;
  convertCount: number;
  videoCount: number;
  canConvert: boolean;
  canReconstructVideo: boolean;
  isConverting: boolean;
  isDownloading: boolean;
  onConvert: () => void;
  onReconstructVideo: () => void;
  onDownload: () => void;
  onClear: () => void;
}

export function PhotoSelectionBar({
  selectedCount,
  convertCount,
  videoCount,
  canConvert,
  canReconstructVideo,
  isConverting,
  isDownloading,
  onConvert,
  onReconstructVideo,
  onDownload,
  onClear,
}: PhotoSelectionBarProps) {
  const { t } = useTranslation();

  const actions: SelectionActionBarAction[] = [
    {
      id: 'convert',
      icon: <SparklesIcon width={16} height={16} />,
      label: isConverting
        ? t('converting')
        : canConvert
          ? t('photoConvertSelectedShort', { count: convertCount })
          : t('photoConvertPhotosOnly'),
      ariaLabel: canConvert ? t('photoConvertSelected') : t('photoConvertPhotosOnly'),
      tooltip: canConvert ? t('photoConvertSelected') : t('photoConvertPhotosOnly'),
      disabled: isConverting || !canConvert,
      busy: isConverting,
      variant: 'primary',
      onClick: onConvert,
    },
  ];

  if (videoCount > 0) {
    actions.push({
      id: 'reconstruct-video',
      icon: <SparklesIcon width={16} height={16} />,
      label: canReconstructVideo ? t('videoReconGenerate3d') : t('videoReconSingleVideoOnly'),
      ariaLabel: canReconstructVideo ? t('videoReconGenerate3d') : t('videoReconSingleVideoOnly'),
      tooltip: canReconstructVideo ? t('videoReconGenerate3d') : t('videoReconSingleVideoOnly'),
      disabled: isConverting || !canReconstructVideo,
      variant: 'primary',
      onClick: onReconstructVideo,
    });
  }

  actions.push({
    id: 'download',
    icon: <DownloadIcon width={16} height={16} />,
    ariaLabel: isDownloading ? t('photoDownloadingSelected') : t('photoDownloadSelected'),
    tooltip: isDownloading ? t('photoDownloadingSelected') : t('photoDownloadSelected'),
    disabled: isDownloading,
    busy: isDownloading,
    onClick: onDownload,
  });

  return (
    <SelectionActionBar
      selectedCount={selectedCount}
      selectedLabel={t('photoSelectedLabel')}
      countAriaLabel={t('photoSelectedCount', { count: selectedCount })}
      actions={actions}
      clearLabel={t('photoClearSelection')}
      onClear={onClear}
    />
  );
}
