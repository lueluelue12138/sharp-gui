import { useEffect, useState } from 'react';

import { useTranslation } from 'react-i18next';

import { fetchPhotoAlbumPhotos, fetchPhotoAlbums } from '@/api/photoGallery';
import { Button } from '@/components/common/Button';
import { Modal } from '@/components/common/Modal';
import { PhotoAlbumSelect } from '@/components/photoGallery/PhotoAlbumSelect';
import { useImageDrop } from '@/hooks/useImageDrop';
import { useAppStore } from '@/store';
import type { PhotoAlbum, PhotoItem } from '@/types/photoGallery';

import styles from '@/components/photoGallery/GalleryImagePicker/GalleryImagePicker.module.css';

interface GalleryImagePickerProps {
  onSelect: (photo: PhotoItem) => void;
  onClose: () => void;
  onDropFile?: (file: File) => void;
}

export function GalleryImagePicker({ onSelect, onClose, onDropFile }: GalleryImagePickerProps) {
  const { t } = useTranslation();
  const preferredAlbum = useAppStore((state) => state.currentPhotoAlbumId);
  const [albums, setAlbums] = useState<PhotoAlbum[]>();
  const [album, setAlbum] = useState('');
  const [failed, setFailed] = useState(false);
  const drop = useImageDrop(([file]) => onDropFile?.(file), { enabled: Boolean(onDropFile) });

  useEffect(() => {
    let active = true;
    void fetchPhotoAlbums().then(({ albums }) => {
      if (!active) return;
      const available = albums.filter((item) => item.available !== false && item.enabled);
      setAlbums(available);
      setAlbum(available.find(({ id }) => id === preferredAlbum)?.id ?? available[0]?.id ?? '');
    }).catch(() => { if (active) setFailed(true); });
    return () => { active = false; };
  }, [preferredAlbum]);

  return <Modal isOpen portal onClose={onClose} title={t('photoTools.choosePhoto')} size="lg">
    <div className={styles.dropArea} {...drop}>
      {failed ? <p role="alert">{t('photoTools.galleryUnavailable')}</p> : !albums ? <p role="status">{t('loading')}</p>
        : !albums.length ? <p>{t('photoTools.noAlbums')}</p> : <>
          <div className={styles.album}><PhotoAlbumSelect albums={albums} value={album} onChange={setAlbum} /></div>
          {album && <AlbumPhotos key={album} album={album} onSelect={onSelect} />}
        </>}
    </div>
  </Modal>;
}

function AlbumPhotos({ album, onSelect }: { album: string; onSelect: (photo: PhotoItem) => void }) {
  const { t } = useTranslation();
  const [items, setItems] = useState<PhotoItem[]>([]);
  const [page, setPage] = useState<{ cursor: string | null; snapshot?: string | null }>({ cursor: null });
  const [next, setNext] = useState<typeof page>();
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let active = true;
    void fetchPhotoAlbumPhotos(album, page.cursor, 36, 'mtime_desc', 'image', page.snapshot).then((result) => {
      if (!active) return;
      if (result.available === false) throw new Error();
      setItems((existing) => page.cursor ? [...existing, ...result.items] : result.items);
      setNext(result.next_cursor ? { cursor: result.next_cursor, snapshot: result.snapshot } : undefined);
    }).catch(() => { if (active) setFailed(true); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [album, page]);

  return <>
    <div className={styles.grid}>
      {items.map((photo) => <button key={photo.id} type="button" onClick={() => onSelect(photo)} title={photo.name}>
        <img src={photo.thumb_url ?? photo.preview_url} alt="" loading="lazy" /><span>{photo.name}</span>
      </button>)}
    </div>
    {failed && <p role="alert">{t('photoTools.galleryUnavailable')}</p>}
    {loading ? <p role="status">{t('loading')}</p> : next
      ? <Button variant="secondary" type="button" onClick={() => { setFailed(false); setLoading(true); setPage(next); }}>{t('photoTools.morePhotos')}</Button>
      : !items.length && !failed && <p>{t('photoTools.noPhotos')}</p>}
  </>;
}
