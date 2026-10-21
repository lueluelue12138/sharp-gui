import type { ViewerModelFormat } from '@/constants/spark';
import type { ViewerTransformState } from '@/types/viewerQuickControls';

export type ViewerOrientationHint = 'default' | 'y-front' | 'unknown';

export type ViewerOrientationMode = Exclude<ViewerOrientationHint, 'unknown'>;

export type ViewerOrientationReason =
  | 'explicit-default'
  | 'explicit-y-front'
  | 'source-image'
  | 'source-video'
  | 'legacy-video'
  | 'external-fallback'
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
  viewerTransform?: ViewerTransformState | null;
}

export interface ViewerOrientationInput {
  source?: CurrentModelSource;
  viewerOrientation?: unknown;
  sourceMediaType?: unknown;
  legacyVideo?: boolean;
}

export interface ResolvedViewerOrientation {
  mode: ViewerOrientationMode;
  reason: ViewerOrientationReason;
}
