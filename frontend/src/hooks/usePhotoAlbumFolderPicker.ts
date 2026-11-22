import { useState } from 'react';

import { useTranslation } from 'react-i18next';

import { ApiError, browseFolder } from '@/api';

export function usePhotoAlbumFolderPicker(
  enabled: boolean,
  onSelect: (path: string) => Promise<void>,
  onManualEntry: () => void,
  onBusy: (message: string) => void,
) {
  const { t } = useTranslation();
  const [isPickingFolder, setIsPickingFolder] = useState(false);

  async function pickAlbumFolder() {
    if (!enabled || isPickingFolder) return;
    setIsPickingFolder(true);
    try {
      const result = await browseFolder(t('photoSelectFolder'));
      if (result.success) await onSelect(result.path);
      else if (!result.cancelled) onManualEntry();
    } catch (error) {
      if (error instanceof ApiError && error.data?.code === 'folderPickerBusy') {
        onBusy(t('photoFolderPickerBusy'));
      } else {
        onManualEntry();
      }
    } finally {
      setIsPickingFolder(false);
    }
  }

  return { isPickingFolder, pickAlbumFolder };
}
