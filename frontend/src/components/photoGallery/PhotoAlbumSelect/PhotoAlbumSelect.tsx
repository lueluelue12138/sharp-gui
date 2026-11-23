import { useTranslation } from 'react-i18next';

import { SelectMenu } from '@/components/common/SelectMenu';
import type { PhotoAlbum } from '@/types/photoGallery';

import styles from '@/components/photoGallery/PhotoAlbumSelect/PhotoAlbumSelect.module.css';

interface PhotoAlbumSelectProps {
  albums: PhotoAlbum[];
  value: string;
  onChange: (id: string) => void;
  disabled?: boolean;
}

export function PhotoAlbumSelect({ albums, value, onChange, disabled }: PhotoAlbumSelectProps) {
  const { t } = useTranslation();
  const label = t('photoTools.album');
  return <div className={styles.field}>
    <span>{label}</span>
    <SelectMenu portal value={value} ariaLabel={label} onChange={onChange} disabled={disabled}
      options={albums.map(({ id, name }) => ({ value: id, label: name }))}
      className={styles.select} menuClassName={styles.menu} />
  </div>;
}
