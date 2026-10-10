import * as THREE from 'three';

import type {
  CurrentModelDescriptor,
  ViewerCameraHint,
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

export function getReconstructionCameraView(
  hint: ViewerCameraHint | null | undefined,
  modelMatrixWorld: THREE.Matrix4,
  viewportAspect: number,
) {
  if (!hint || !Number.isFinite(viewportAspect) || viewportAspect <= 0) return null;
  const vectors = [hint.position, hint.target, hint.up];
  if (!vectors.every((vector) => Array.isArray(vector) && vector.length === 3
    && vector.every((value) => typeof value === 'number' && Number.isFinite(value)))) return null;
  if (!Number.isFinite(hint.fov_y_degrees) || hint.fov_y_degrees <= 1 || hint.fov_y_degrees >= 179
    || !Number.isFinite(hint.aspect) || hint.aspect <= 0.01 || hint.aspect >= 100) return null;

  const position = new THREE.Vector3(...hint.position).applyMatrix4(modelMatrixWorld);
  const target = new THREE.Vector3(...hint.target).applyMatrix4(modelMatrixWorld);
  const up = new THREE.Vector3(...hint.up).transformDirection(modelMatrixWorld);
  const forward = target.clone().sub(position);
  if (!position.toArray().concat(target.toArray(), up.toArray()).every(Number.isFinite)
    || forward.clone().cross(up).lengthSq() < 1e-12) return null;

  // Preserve the source camera's horizontal coverage in narrower viewer panels.
  const tangent = Math.tan(THREE.MathUtils.degToRad(hint.fov_y_degrees) / 2);
  const fov = THREE.MathUtils.clamp(THREE.MathUtils.radToDeg(
    2 * Math.atan(tangent * Math.max(1, hint.aspect / viewportAspect)),
  ), 1.01, 175);
  return { position, target, up, fov };
}

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
    descriptor.viewerCamera,
    descriptor.viewerTransform,
  ]);
}
