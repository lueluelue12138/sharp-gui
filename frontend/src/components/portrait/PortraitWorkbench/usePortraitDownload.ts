import { useState } from 'react';

import { downloadFile } from '@/utils/fileDownload';

export function usePortraitDownload() {
  const [downloading, setDownloading] = useState<string | null>(null);
  const [downloadFailed, setDownloadFailed] = useState(false);

  async function download(url: string, fallbackFilename: string, mimeType = 'image/png') {
    if (downloading) return;
    setDownloading(url);
    setDownloadFailed(false);
    try {
      const target = new URL(url, window.location.href);
      target.searchParams.set('download', '1');
      await downloadFile(target.href, { fallbackFilename, mimeType });
    } catch {
      setDownloadFailed(true);
    } finally {
      setDownloading(null);
    }
  }

  return { download, downloading, downloadFailed };
}
