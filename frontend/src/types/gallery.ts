// Gallery item from API
export interface GalleryItem {
  id: string;
  name: string;
  image_url: string;
  thumb_url?: string;
  model_url: string;
  size?: number;
  created_at?: string;
}

// API response for gallery list
export interface GalleryListResponse {
  items: GalleryItem[];
}
