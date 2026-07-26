import * as THREE from 'three';

import type {
  CurrentModelDescriptor,
  ViewerOrientationMode,
} from '@/types';

interface ViewerRotation {
  rotationX: number;
  rotationY: number;
  rotationZ: number;
}

interface ViewerLoadGuardInput<TContext> {
  cancelled: boolean;
  generation: number;
  activeGeneration: number;
  context: TContext;
  activeContext: TContext | null;
}

const yFrontOrientationQuaternion = new THREE.Quaternion()
  .setFromAxisAngle(new THREE.Vector3(1, 0, 0), Math.PI / 2);

export function composeViewerModelQuaternion(
  rotation: ViewerRotation,
  orientationMode: ViewerOrientationMode,
): THREE.Quaternion {
  const userQuaternion = new THREE.Quaternion().setFromEuler(
    new THREE.Euler(rotation.rotationX, rotation.rotationY, rotation.rotationZ),
  );

  if (orientationMode === 'y-front') {
    userQuaternion.premultiply(yFrontOrientationQuaternion);
  }

  return userQuaternion;
}

export function isViewerLoadCurrent<TContext>({
  cancelled,
  generation,
  activeGeneration,
  context,
  activeContext,
}: ViewerLoadGuardInput<TContext>): boolean {
  return (
    !cancelled
    && generation === activeGeneration
    && context === activeContext
  );
}

export function getViewerModelLoadKey(
  descriptor: CurrentModelDescriptor | null,
): string | null {
  if (!descriptor) return null;

  return JSON.stringify([
    descriptor.id,
    descriptor.url,
    descriptor.format,
    descriptor.size,
    descriptor.source,
    descriptor.sourceMediaType,
    descriptor.viewerOrientation,
  ]);
}
