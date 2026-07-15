import type { TFunction } from 'i18next';

const modelAssetErrorKeys: Record<string, string> = {
  unsupported_format: 'modelAssetErrorUnsupportedFormat',
  too_many_files: 'modelAssetErrorTooManyFiles',
  file_too_large: 'modelAssetErrorFileTooLarge',
  batch_too_large: 'modelAssetErrorBatchTooLarge',
  import_request_too_large: 'modelAssetErrorRequestTooLarge',
  invalid_filename: 'modelAssetErrorInvalidFilename',
  invalid_target: 'modelAssetErrorInvalidTarget',
  save_failed: 'modelAssetErrorSaveFailed',
  model_asset_import_root_invalid: 'modelAssetErrorStorageUnavailable',
  model_asset_import_root_unavailable: 'modelAssetErrorStorageUnavailable',
  model_asset_index_corrupt: 'modelAssetErrorIndexCorrupt',
  model_asset_index_schema_invalid: 'modelAssetErrorIndexCorrupt',
  model_asset_index_unavailable: 'modelAssetErrorIndexUnavailable',
  model_asset_index_write_failed: 'modelAssetErrorIndexWriteFailed',
  model_asset_delete_failed: 'modelAssetErrorDeleteFailed',
  model_asset_path_invalid: 'modelAssetErrorPathInvalid',
  invalid_cover_target: 'modelAssetErrorPathInvalid',
  invalid_cover_image: 'modelAssetErrorInvalidCover',
  unsupported_cover_type: 'modelAssetErrorInvalidCover',
  cover_too_large: 'modelAssetErrorCoverTooLarge',
  cover_write_failed: 'modelAssetErrorCoverWriteFailed',
  model_asset_not_found: 'modelAssetErrorNotFound',
  model_asset_file_not_found: 'modelAssetOpenUnavailable',
  OWNER_REQUIRED: 'ownerOnlyAction',
  AUTH_REQUIRED: 'modelAssetErrorAuthRequired',
};

export function localizeModelAssetError(
  t: TFunction,
  code?: string | null,
  fallback?: string | null,
): string {
  const key = code ? modelAssetErrorKeys[code] : null;
  if (key) {
    return t(key);
  }
  return fallback || t('modelAssetGenericError');
}
