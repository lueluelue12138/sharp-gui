export type GalleryModelFormat = 'ply' | 'spz' | 'splat' | 'rad';

// Gallery item from API
export interface GalleryItem {
  id: string;
  name: string;
  image_url?: string | null;
  thumb_url?: string | null;
  thumb_version?: number | null;
  model_url: string;
  model_format?: GalleryModelFormat;
  available_formats?: GalleryModelFormat[];
  spz_url?: string | null;
  size?: number;
  spz_size?: number | null;
  source_media_type?: 'video' | 'image' | string | null;
  source_media_id?: string | null;
  source_name?: string | null;
  source_video_url?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

// Model format preference
export type ModelFormat = 'ply' | 'spz';

// API response for gallery list
export interface GalleryListResponse {
  items: GalleryItem[];
}
