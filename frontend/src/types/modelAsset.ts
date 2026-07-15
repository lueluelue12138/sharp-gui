export type ModelAssetFormat = 'ply' | 'spz' | 'splat' | 'rad';

export type ModelAssetSourceType = 'generated' | 'imported' | 'video';

export type ModelAssetSourceFilter = 'all' | ModelAssetSourceType;

export type ModelAssetFormatFilter = 'all' | ModelAssetFormat;

export type ModelAssetSort =
  | 'modified_desc'
  | 'modified_asc'
  | 'created_desc'
  | 'created_asc'
  | 'name_asc'
  | 'name_desc'
  | 'size_desc'
  | 'size_asc';

export type ModelAssetDensity = 'comfortable' | 'compact' | 'expanded';

export type ModelAssetThumbnailState = 'ready' | 'missing' | 'pending' | 'error';

export interface ModelAssetFile {
  format: ModelAssetFormat;
  filename: string;
  size: number;
  url: string;
  download_url?: string | null;
  modified_at?: string | null;
  primary?: boolean;
}

export interface ModelAsset {
  id: string;
  name: string;
  source_type: ModelAssetSourceType;
  source_label?: string | null;
  primary_format: ModelAssetFormat | null;
  formats: ModelAssetFormat[];
  files?: ModelAssetFile[];
  size: number;
  primary_size?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
  default_open_url?: string | null;
  default_open_format?: ModelAssetFormat | null;
  download_url?: string | null;
  thumb_url?: string | null;
  thumb_version?: number | null;
  thumbnail_state?: ModelAssetThumbnailState | string | null;
  thumbnail_kind?: string | null;
  available: boolean;
  tags: string[];
  note?: string | null;
  is_generated?: boolean;
  is_imported?: boolean;
  source_media_type?: string | null;
  source_media_id?: string | null;
  source_name?: string | null;
  source_video_url?: string | null;
  image_url?: string | null;
  point_count?: number | string | null;
  bounding_box?: string | number[] | null;
  coordinate_system?: string | null;
  attributes?: string | string[] | null;
  compression?: string | null;
  version?: string | null;
  metadata?: Record<string, unknown>;
}

export interface ModelAssetListCounts {
  all: number;
  generated: number;
  imported: number;
  video: number;
}

export type ModelAssetFormatCounts = Record<ModelAssetFormat, number>;

export interface ModelAssetListResponse {
  items: ModelAsset[];
  total: number;
  total_size: number;
  next_cursor: string | null;
  cursor: string;
  limit: number;
  counts: ModelAssetListCounts;
  format_counts: ModelAssetFormatCounts;
  available_tags: string[];
  sort: ModelAssetSort;
  source: ModelAssetSourceFilter;
  format: ModelAssetFormatFilter;
  tag?: string | null;
}

export interface ModelAssetListParams {
  source?: ModelAssetSourceFilter;
  format?: ModelAssetFormatFilter;
  tag?: string | null;
  sort?: ModelAssetSort;
  cursor?: string | null;
  limit?: number;
  refresh?: boolean;
}

export interface ModelAssetImportFailure {
  filename: string;
  code: string;
  error: string;
}

export interface ModelAssetImportResult {
  success: boolean;
  error?: string;
  code?: string;
  assets: ModelAsset[];
  failed: ModelAssetImportFailure[];
}

export interface ModelAssetProfileInput {
  display_name?: string;
  name?: string;
  tags?: string[];
  note?: string;
}
