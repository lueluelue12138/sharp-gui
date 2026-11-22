interface DownloadOptions {
  fallbackFilename: string;
  filename?: string;
  mimeType?: string;
}

function readFilename(header: string | null) {
  const encoded = header?.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  if (encoded) {
    try {
      return decodeURIComponent(encoded);
    } catch {
      // Continue with the plain filename if the extended form is malformed.
    }
  }
  return header?.match(/filename="([^"]+)"/i)?.[1] ?? header?.match(/filename=([^;]+)/i)?.[1].trim();
}

export async function downloadFile(url: string, { fallbackFilename, filename, mimeType }: DownloadOptions) {
  const response = await fetch(url, { credentials: 'same-origin' });
  if (!response.ok) throw new Error(`Download failed (HTTP ${response.status})`);

  const blob = await response.blob();
  if (!blob.size || (mimeType && blob.type !== mimeType)) {
    throw new Error('The download response did not contain the requested file.');
  }

  const blobUrl = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = blobUrl;
  link.download = filename ?? readFilename(response.headers.get('Content-Disposition')) ?? fallbackFilename;
  document.body.appendChild(link);
  try {
    link.click();
  } finally {
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);
  }
}
