import { useTranslation } from 'react-i18next';
import { useAppStore } from '@/store';
import { downloadModel, deleteGalleryItem } from '@/api';
import { GalleryItem } from '../GalleryItem';
import type { GalleryItem as GalleryItemType } from '@/types';
import styles from './GalleryList.module.css';

interface GalleryListProps {
  items: GalleryItemType[];
  onSelectModel: (item: GalleryItemType) => void;
}

export function GalleryList({ items, onSelectModel }: GalleryListProps) {
  const { t } = useTranslation();
  const { currentModelId, setGalleryItems } = useAppStore();

  const handlePreview = (item: GalleryItemType) => {
    if (item.image_url) {
      window.open(item.image_url, '_blank');
    }
  };

  const handleDownload = (item: GalleryItemType) => {
    downloadModel(item.id);
  };

  const handleDelete = async (item: GalleryItemType) => {
    if (!confirm(t('confirmDeleteFull'))) return;
    
    try {
      const result = await deleteGalleryItem(item.id);
      if (result.success) {
        // Remove from local state
        setGalleryItems(items.filter(i => i.id !== item.id));
      } else {
        alert(`${t('deleteFailed')}: ${result.error}`);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unknown error';
      alert(`${t('errorDeleting')}: ${message}`);
    }
  };

  if (items.length === 0) {
    return (
      <div className={styles.empty}>
        <p>{t('emptyStateTitle')}</p>
      </div>
    );
  }

  return (
    <div className={styles.list}>
      {items.map((item) => (
        <GalleryItem
          key={item.id}
          item={item}
          isActive={currentModelId === item.id}
          onSelect={() => onSelectModel(item)}
          onPreview={() => handlePreview(item)}
          onDownload={() => handleDownload(item)}
          onDelete={() => handleDelete(item)}
        />
      ))}
    </div>
  );
}
