import type { PhotoAlbum } from '@/types/photoGallery';

export function isPhotoAlbumAvailable(album: PhotoAlbum | null | undefined): boolean {
  return Boolean(album && album.enabled && album.available !== false);
}

export function getPhotoAlbumErrorKey(code?: string | null): string {
  switch (code) {
    case 'photo_album_path_missing':
      return 'photoAlbumPathMissing';
    case 'photo_album_media_missing':
      return 'photoAlbumMediaMissing';
    case 'photo_album_permission_denied':
      return 'photoAlbumPermissionDenied';
    case 'photo_album_storage_changed':
      return 'photoAlbumStorageDisconnected';
    case 'photo_album_disabled':
      return 'photoAlbumDisabled';
    default:
      return 'photoAlbumUnavailable';
  }
}
