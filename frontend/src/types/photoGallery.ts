export type AppView = 'models' | 'photos';

export type PhotoAlbumScanStatus = 'idle' | 'scanning' | 'indexing' | 'needs_index' | 'stale' | 'error';
export type PhotoMediaType = 'all' | 'image' | 'video';
export type PhotoItemMediaType = 'image' | 'video';

export interface PhotoMediaCounts {
  all: number;
  image: number;
  photo: number;
  video: number;
}

export interface PhotoAlbum {
  id: string;
  name: string;
  cover_thumb_url: string | null;
  photo_count: number | null;
  media_count?: number | null;
  video_count?: number | null;
  recursive: boolean;
  enabled: boolean;
  scan_status: PhotoAlbumScanStatus;
  updated_at: string | null;
  last_scanned_at?: string | null;
  index_version?: number;
  error?: string | null;
}

export interface PhotoItem {
  id: string;
  album_id: string;
  name: string;
  media_type: PhotoItemMediaType;
  width: number | null;
  height: number | null;
  thumb_url: string | null;
  full_url?: string;
  poster_url?: string | null;
  preview_url: string;
  playback_url?: string;
  audio_stream_url?: string | null;
  download_url: string;
  duration?: number | null;
  mime_type?: string | null;
  video_codec?: string | null;
  audio_codec?: string | null;
  bitrate?: number | null;
  size?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface PhotoAlbumsResponse {
  albums: PhotoAlbum[];
  is_local?: boolean;
}

export interface PhotoGalleryCacheBucket {
  files: number;
  bytes: number;
}

export interface PhotoGalleryCacheStats {
  success: boolean;
  index_version: number;
  indexes: PhotoGalleryCacheBucket;
  thumbnails: PhotoGalleryCacheBucket;
  video_posters: PhotoGalleryCacheBucket;
  downloads: PhotoGalleryCacheBucket;
  total: PhotoGalleryCacheBucket;
}

export type PhotoGalleryCacheClearScope =
  | 'generated'
  | 'indexes'
  | 'thumbnails'
  | 'posters'
  | 'downloads'
  | 'all';

export interface PhotoGalleryCacheClearResponse {
  success: boolean;
  scope: PhotoGalleryCacheClearScope;
  removed: PhotoGalleryCacheBucket;
  stats: PhotoGalleryCacheStats;
  error?: string;
}

export interface AddPhotoAlbumRequest {
  path: string;
  name?: string;
  recursive?: boolean;
}

export interface AddPhotoAlbumResponse {
  success: boolean;
  album: PhotoAlbum;
  duplicate?: boolean;
  error?: string;
}

export interface PhotoListResponse {
  items: PhotoItem[];
  next_cursor: string | null;
  total: number;
  media_counts?: PhotoMediaCounts;
  scan_status: PhotoAlbumScanStatus;
  snapshot?: string | null;
  index_version?: number;
  error?: string | null;
}

export interface PhotoConversionResponse {
  success: boolean;
  tasks?: import('./task').Task[];
  failed?: Array<{
    id: string;
    error: string;
  }>;
  error?: string;
}

export interface PhotoUploadResponse {
  success: boolean;
  uploaded: number;
  album: PhotoAlbum;
  failed?: Array<{
    name: string;
    error: string;
  }>;
  error?: string;
}
