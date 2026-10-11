import * as THREE from 'three';

import type { ViewerCameraHint } from '@/types/modelPreview';

/** Every file has a real zero point, independent of viewing and crop centers. */
export function resolveEditorOrigin(model: THREE.Matrix4): THREE.Vector3 {
  return new THREE.Vector3().applyMatrix4(model);
}

/** Apply a change of orientation around the chosen, fixed world-space origin. */
export function rotateModelAtOrigin(
  model: THREE.Matrix4,
  origin: THREE.Vector3,
  previous: THREE.Quaternion,
  next: THREE.Quaternion,
): THREE.Matrix4 {
  const delta = next.clone().multiply(previous.clone().invert()).normalize();
  return new THREE.Matrix4()
    .makeTranslation(origin.x, origin.y, origin.z)
    .multiply(new THREE.Matrix4().makeRotationFromQuaternion(delta))
    .multiply(new THREE.Matrix4().makeTranslation(-origin.x, -origin.y, -origin.z))
    .multiply(model);
}

/**
 * Map the edited world back to the ordinary PLY display basis, as OOOSplat does.
 * Geometry, Gaussian rotations and SH are then baked by the backend in file space.
 * Reimporting the PLY requires no viewer_transform or origin compatibility marker.
 */
export function createAlignedExport(
  model: THREE.Matrix4,
  origin: THREE.Vector3,
  camera: ViewerCameraHint,
  displayBasis: THREE.Matrix4,
): { matrix: number[]; camera: ViewerCameraHint } {
  const worldToFile = displayBasis.clone().invert()
    .multiply(new THREE.Matrix4().makeTranslation(-origin.x, -origin.y, -origin.z));
  return {
    matrix: worldToFile.clone().multiply(model).toArray(),
    camera: {
      ...camera,
      position: new THREE.Vector3().fromArray(camera.position).applyMatrix4(worldToFile).toArray(),
      target: new THREE.Vector3().fromArray(camera.target).applyMatrix4(worldToFile).toArray(),
      up: new THREE.Vector3().fromArray(camera.up).transformDirection(worldToFile).toArray(),
    },
  };
}
