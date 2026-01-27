import { useTranslation } from 'react-i18next';
import { EyeIcon, DownloadIcon, DeleteIcon } from '@/components/common/Icons';
import { formatFileSize } from '@/utils';
import type { GalleryItem as GalleryItemType } from '@/types';
import styles from './GalleryItem.module.css';

interface GalleryItemProps {
  item: GalleryItemType;
  isActive: boolean;
  onSelect: () => void;
  onPreview: () => void;
  onDownload: () => void;
  onDelete: () => void;
}

export function GalleryItem({
  item,
  isActive,
  onSelect,
  onPreview,
  onDownload,
  onDelete,
}: GalleryItemProps) {
  const { t } = useTranslation();
  
  const handleButtonClick = (e: React.MouseEvent, action: () => void) => {
    e.stopPropagation();
    action();
  };

  return (
    <div 
      className={`${styles.item} ${isActive ? styles.active : ''}`}
      onClick={onSelect}
    >
      <img 
        src={item.thumb_url || item.image_url} 
        alt={item.name}
        className={styles.thumb}
        loading="lazy"
        onError={(e) => {
          (e.target as HTMLImageElement).style.background = '#eee';
        }}
      />
      
      <div className={styles.info}>
        <div className={styles.name}>{item.name}</div>
        <div className={styles.meta}>
          {item.size ? formatFileSize(item.size) : t('ready')}
        </div>
      </div>

      {/* Action buttons */}
      {item.image_url && (
        <button 
          className={styles.actionBtn}
          onClick={(e) => handleButtonClick(e, onPreview)}
          title={t('viewOriginal')}
        >
          <EyeIcon width={14} height={14} />
        </button>
      )}
      
      <button 
        className={styles.actionBtn}
        onClick={(e) => handleButtonClick(e, onDownload)}
        title={t('download')}
      >
        <DownloadIcon width={14} height={14} />
      </button>
      
      <button 
        className={`${styles.actionBtn} ${styles.deleteBtn}`}
        onClick={(e) => handleButtonClick(e, onDelete)}
        title={t('delete')}
      >
        <DeleteIcon width={14} height={14} />
      </button>
    </div>
  );
}
