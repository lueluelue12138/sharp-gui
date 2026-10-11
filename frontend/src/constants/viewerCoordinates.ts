import * as THREE from 'three';

import type { ViewerTransformState } from '@/types';

/** Existing PLY display basis. User edits must be baked back into file coordinates. */
export const DEFAULT_VIEWER_TRANSFORM: ViewerTransformState = {
  positionX: 0,
  positionY: 0,
  positionZ: 0,
  rotationX: Math.PI,
  rotationY: 0,
  rotationZ: 0,
  scale: 2,
};

export function getDefaultPlyDisplayMatrix(): THREE.Matrix4 {
  const value = DEFAULT_VIEWER_TRANSFORM;
  return new THREE.Matrix4().compose(
    new THREE.Vector3(value.positionX, value.positionY, value.positionZ),
    new THREE.Quaternion().setFromEuler(new THREE.Euler(value.rotationX, value.rotationY, value.rotationZ)),
    new THREE.Vector3(value.scale, value.scale, value.scale),
  );
}
