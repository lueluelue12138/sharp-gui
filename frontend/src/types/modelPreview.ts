import type { ViewerModelFormat } from '@/constants/spark';

export type ViewerOrientationHint = 'default' | 'y-front' | 'unknown';

export type ViewerOrientationMode = Exclude<ViewerOrientationHint, 'unknown'>;

export type ViewerOrientationReason =
  | 'explicit-default'
  | 'explicit-y-front'
  | 'source-image'
  | 'source-video'
  | 'legacy-video'
  | 'unknown-fallback';

export type CurrentModelSource =
  | 'gallery'
  | 'model-asset-generated'
  | 'model-asset-imported'
  | 'temporary';

export interface ViewerCameraHint {
  position: [number, number, number];
  target: [number, number, number];
  up: [number, number, number];
  fov_y_degrees: number;
  aspect: number;
}

export interface CurrentModelDescriptor {
  id: string;
  url: string;
  format: ViewerModelFormat;
  size: number | null;
  source: CurrentModelSource;
  sourceMediaType: string | null;
  viewerOrientation: ViewerOrientationHint | null;
  viewerCamera?: ViewerCameraHint | null;
}

export interface ViewerOrientationInput {
  viewerOrientation?: unknown;
  sourceMediaType?: unknown;
  legacyVideo?: boolean;
}

export interface ResolvedViewerOrientation {
  mode: ViewerOrientationMode;
  reason: ViewerOrientationReason;
}
