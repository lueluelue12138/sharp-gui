import type { ViewerCameraHint, ViewerOrientationHint } from '@/types/modelPreview';
import type { ViewerTransformState } from '@/types/viewerQuickControls';

export interface ShareManifest {
  version: 1;
  format: 'ply' | 'spz' | 'splat' | 'rad';
  sourceMediaType: 'image' | 'video' | null;
  viewerOrientation: ViewerOrientationHint;
  viewerTransform: ViewerTransformState | null;
  viewerCamera: ViewerCameraHint | null;
}

export type ShareStage = 'preparing' | 'decoding' | 'rendering' | 'ready';
