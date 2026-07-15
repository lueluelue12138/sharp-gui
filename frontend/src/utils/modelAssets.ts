import type { ViewerModelFormat } from '@/constants/spark';
import type { ModelAsset, ModelAssetFile, ModelAssetFormat, ModelFormat } from '@/types';

const MODEL_ASSET_FORMAT_FALLBACKS: ModelAssetFormat[] = ['spz', 'ply', 'splat', 'rad'];

export interface ResolvedModelAssetSource {
  file: ModelAssetFile | null;
  format: ViewerModelFormat;
  url: string | null;
  size: number;
}

function getFormatPriority(preferredFormat: ModelFormat): ModelAssetFormat[] {
  return [
    preferredFormat,
    ...MODEL_ASSET_FORMAT_FALLBACKS.filter((format) => format !== preferredFormat),
  ];
}

export function resolveModelAssetSource(
  asset: ModelAsset,
  preferredFormat: ModelFormat,
): ResolvedModelAssetSource {
  const fileByFormat = new Map<ModelAssetFormat, ModelAssetFile>();
  (asset.files ?? []).forEach((file) => {
    fileByFormat.set(file.format, file);
  });

  for (const format of getFormatPriority(preferredFormat)) {
    const file = fileByFormat.get(format);
    if (file?.url) {
      return {
        file,
        format,
        url: file.url,
        size: file.size,
      };
    }
  }

  const defaultFormat = asset.default_open_format;
  const defaultUrl = asset.default_open_url ?? null;
  const defaultFile = defaultFormat ? fileByFormat.get(defaultFormat) ?? null : null;
  const fallbackFormat = defaultFormat ?? asset.primary_format ?? asset.formats[0] ?? null;

  return {
    file: defaultFile,
    format: fallbackFormat,
    url: defaultFile?.url ?? defaultUrl,
    size: defaultFile?.size ?? asset.primary_size ?? asset.size ?? 0,
  };
}
