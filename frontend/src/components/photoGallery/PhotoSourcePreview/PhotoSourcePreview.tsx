import { useState } from 'react';

import { Download, LoaderCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/common/Button';
import type { PhotoItem } from '@/types/photoGallery';
import type { PortraitUpload } from '@/types/portrait';
import { downloadFile } from '@/utils/fileDownload';

import styles from '@/components/photoGallery/PhotoSourcePreview/PhotoSourcePreview.module.css';

interface PhotoSourcePreviewProps {
  src: string;
  name?: string;
  width?: number | null;
  height?: number | null;
  large?: boolean;
}

export function PhotoSourcePreview({ src, name, width, height, large }: PhotoSourcePreviewProps) {
  const { t } = useTranslation();
  const [size, setSize] = useState<{ src: string; width: number; height: number }>();
  const dimensions = size?.src === src ? size : { width, height };

  return <div className={styles.preview} data-large={large}>
    <img src={src} alt="" draggable={false} onLoad={(event) => {
      const { naturalWidth, naturalHeight } = event.currentTarget;
      if (naturalWidth && naturalHeight) setSize({ src, width: naturalWidth, height: naturalHeight });
    }} />
    <div className={styles.metadata}>
      {name && <span className={styles.name} title={name}>{name}</span>}
      {dimensions.width && dimensions.height ? <span className={styles.dimensions}>
        {t('photoTools.sourceResolution', { width: dimensions.width, height: dimensions.height })}
      </span> : null}
    </div>
  </div>;
}

export function PhotoSourceDownload({ photo, source, name }: { photo?: PhotoItem; source?: PortraitUpload; name?: string }) {
  const { t } = useTranslation();
  const [downloading, setDownloading] = useState(false);
  const [failed, setFailed] = useState(false);
  const originalUrl = photo?.download_url || source?.download_url;
  const url = originalUrl || source?.url;
  if (!url) return null;

  async function download(sourceUrl: string) {
    if (downloading) return;
    setDownloading(true);
    setFailed(false);
    try {
      const target = new URL(sourceUrl, window.location.href);
      target.searchParams.set('download', '1');
      const pngName = `${name?.replace(/\.[^.]+$/, '') || 'original'}.png`;
      await downloadFile(target.href, {
        fallbackFilename: originalUrl ? name || 'original.png' : pngName,
        filename: originalUrl ? undefined : pngName,
        mimeType: originalUrl ? undefined : 'image/png',
      });
    } catch {
      setFailed(true);
    } finally {
      setDownloading(false);
    }
  }

  return <>
    <Button variant="ghost" size="sm" type="button" disabled={downloading}
      icon={downloading ? <LoaderCircle size={16} className="spin" /> : <Download size={16} />}
      title={originalUrl ? undefined : t('photoTools.downloadInputPng')}
      onClick={() => void download(url)}>{t(downloading ? 'downloading' : 'photoTools.downloadOriginal')}</Button>
    {failed && <span className={styles.downloadError} role="alert">{t('photoDownloadFailed')}</span>}
  </>;
}
