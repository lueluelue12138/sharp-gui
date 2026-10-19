import { createRoot } from 'react-dom/client';

import { ShareViewer } from '@/share/ShareViewer';
import type { ShareManifest } from '@/share/types';
import '@/styles/variables.css';

const host = document.getElementById('share-root')!;
try {
  const manifest = JSON.parse(document.getElementById('share-manifest')?.textContent ?? '{}') as ShareManifest;
  if (manifest.version !== 1 || !['ply', 'spz', 'splat', 'rad'].includes(manifest.format)) throw new Error('Invalid share manifest');
  const raw = document.getElementById('model-data-raw');
  const encoded = raw?.textContent?.trim() ?? '';
  raw?.remove();
  const name = document.getElementById('share-model-name')?.textContent ?? '3D model';
  createRoot(host).render(<ShareViewer manifest={manifest} encoded={encoded} name={name} />);
} catch (error) {
  const notice = document.createElement('p');
  notice.textContent = `无法打开分享文件 / Cannot open shared model: ${error instanceof Error ? error.message : 'Invalid data'}`;
  host.replaceChildren(notice);
}
