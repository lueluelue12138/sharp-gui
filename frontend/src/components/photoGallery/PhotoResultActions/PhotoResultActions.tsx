import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';

import { FolderDown, LoaderCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { fetchPhotoAlbums } from '@/api/photoGallery';
import { savePortraitResult } from '@/api/portrait';
import { Button } from '@/components/common/Button';
import { Modal } from '@/components/common/Modal';
import { PhotoAlbumSelect } from '@/components/photoGallery/PhotoAlbumSelect';
import { PhotoToolMenu } from '@/components/photoGallery/PhotoToolMenu';
import { useAppStore } from '@/store';
import type { PhotoAlbum } from '@/types/photoGallery';
import type { PhotoTool } from '@/types/portrait';

import styles from '@/components/photoGallery/PhotoResultActions/PhotoResultActions.module.css';

interface PhotoResultActionsProps {
  image: string;
  tool: PhotoTool;
  canUseResult: boolean;
  onContinue: (tool: PhotoTool, image: string) => void;
}

export function PhotoResultActions({ image, tool, canUseResult, onContinue }: PhotoResultActionsProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [savedAlbum, setSavedAlbum] = useState('');
  return <>
    <Button variant="secondary" type="button" size="sm" icon={<FolderDown size={16} />}
      disabled={!canUseResult} onClick={() => setOpen(true)}>{t('photoTools.save')}</Button>
    <PhotoToolMenu current={tool} disabled={!canUseResult} onSelect={(target) => onContinue(target, image)} />
    {savedAlbum && <span className={styles.saved} role="status">{t('photoTools.saved', { album: savedAlbum })}</span>}
    {open && <SaveToAlbum image={image} onClose={() => setOpen(false)} onSaved={(album) => { setSavedAlbum(album); setOpen(false); }} />}
  </>;
}

function SaveToAlbum({ image, onClose, onSaved }: { image: string; onClose: () => void; onSaved: (name: string) => void }) {
  const { t } = useTranslation();
  const [albums, setAlbums] = useState<PhotoAlbum[]>();
  const [selected, setSelected] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  const saving = useRef(false);

  useEffect(() => {
    let active = true;
    void fetchPhotoAlbums().then(({ albums }) => {
      if (!active) return;
      const choices = albums.filter((album) => !album.system && album.enabled && album.available !== false);
      const current = useAppStore.getState().currentPhotoAlbumId;
      setAlbums(choices);
      setSelected(choices.find(({ id }) => id === current)?.id ?? choices[0]?.id ?? '');
    }).catch(() => { if (active) setError(true); });
    return () => { active = false; };
  }, []);

  async function save(event: FormEvent) {
    event.preventDefault();
    const album = albums?.find(({ id }) => id === selected);
    if (!album || saving.current) return;
    saving.current = true;
    setBusy(true);
    setError(false);
    try {
      await savePortraitResult(image, album.id);
      const store = useAppStore.getState();
      store.resetPhotoAlbumsLoaded();
      if (store.currentPhotoAlbumId === album.id) useAppStore.setState({ photoQueryKey: null });
      onSaved(album.name);
    } catch {
      setError(true);
    } finally {
      saving.current = false;
      setBusy(false);
    }
  }

  return <Modal isOpen portal onClose={() => { if (!saving.current) onClose(); }} title={t('photoTools.save')}>
    <form className={styles.form} onSubmit={(event) => void save(event)}>
      {albums?.length ? <PhotoAlbumSelect albums={albums} value={selected} onChange={setSelected} disabled={busy} />
        : <p>{albums ? t('photoTools.noAlbums') : error ? t('photoTools.galleryUnavailable') : t('loading')}</p>}
      {error && albums && <p role="alert">{t('photoTools.saveFailed')}</p>}
      <Button type="submit" disabled={!selected || busy} icon={busy ? <LoaderCircle size={17} className="spin" /> : <FolderDown size={17} />}>
        {t(busy ? 'photoTools.saving' : 'photoTools.save')}
      </Button>
    </form>
  </Modal>;
}
