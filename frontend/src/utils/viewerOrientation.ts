import type {
  ResolvedViewerOrientation,
  ViewerOrientationInput,
} from '@/types/modelPreview';

export function resolveViewerOrientation(
  input: ViewerOrientationInput,
): ResolvedViewerOrientation {
  if (input.viewerOrientation === 'default') {
    return {
      mode: 'default',
      reason: 'explicit-default',
    };
  }

  if (input.viewerOrientation === 'y-front') {
    return {
      mode: 'y-front',
      reason: 'explicit-y-front',
    };
  }

  if (input.sourceMediaType === 'image') {
    return {
      mode: 'default',
      reason: 'source-image',
    };
  }

  if (input.sourceMediaType === 'video') {
    return {
      mode: 'y-front',
      reason: 'source-video',
    };
  }

  if (input.legacyVideo === true) {
    return {
      mode: 'y-front',
      reason: 'legacy-video',
    };
  }

  return {
    mode: 'default',
    reason: 'unknown-fallback',
  };
}
