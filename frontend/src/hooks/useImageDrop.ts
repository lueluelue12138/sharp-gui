import { useEffect, useState } from 'react';
import type { DragEvent } from 'react';

export const standardPhotoAccept = 'image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp';
export const workbenchPhotoAccept = `${standardPhotoAccept},image/bmp,image/heic,image/heif,.bmp,.heic,.heif`;

interface ImageDropOptions {
  accept?: string;
  enabled?: boolean;
  passthrough?: boolean;
}

export const useImageDrop = (onImages: (files: File[]) => void, {
  accept = workbenchPhotoAccept, enabled = true, passthrough = false,
}: ImageDropOptions = {}) => {
  const [active, setActive] = useState(false);
  const formats = accept.split(',');

  useEffect(() => {
    if (!active) return;
    const reset = () => setActive(false);
    window.addEventListener('dragend', reset);
    window.addEventListener('drop', reset);
    return () => {
      window.removeEventListener('dragend', reset);
      window.removeEventListener('drop', reset);
    };
  }, [active]);

  const dropProps = {
    'data-image-drop-active': enabled && active,
    onDragOver(event: DragEvent<HTMLElement>) {
      const transfer = event.dataTransfer;
      if (!transfer.types.includes('Files')) return;
      const items = Array.from(transfer.items);
      const possible = !items.length || items.some((item) => item.kind === 'file'
        && (!item.type || item.type === 'application/octet-stream' || formats.includes(item.type)));
      if (passthrough && !possible) return;
      event.preventDefault();
      event.stopPropagation();
      transfer.dropEffect = enabled && possible ? 'copy' : 'none';
      setActive(enabled && possible);
    },
    onDragLeave(event: DragEvent<HTMLElement>) {
      if (event.relatedTarget instanceof Node && event.currentTarget.contains(event.relatedTarget)) return;
      setActive(false);
    },
    onDrop(event: DragEvent<HTMLElement>) {
      if (!event.dataTransfer.types.includes('Files')) return;
      setActive(false);
      const files = Array.from(event.dataTransfer.files).filter((file) =>
        formats.some((format) => format.startsWith('.') ? file.name.toLowerCase().endsWith(format) : file.type === format),
      );
      if (passthrough && !files.length) return;
      event.preventDefault();
      event.stopPropagation();
      if (enabled && files.length) onImages(files);
    },
  };
  return dropProps;
};
