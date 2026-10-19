import * as THREE from 'three';

/** Fit all eight corners, including perspective depth and the camera's roll. */
export function getShareBoundsView(
  bounds: THREE.Box3, aspect: number, fov: number,
  direction = new THREE.Vector3(0, 0, 1), up = new THREE.Vector3(0, 1, 0),
) {
  if (bounds.isEmpty() || !bounds.min.toArray().concat(bounds.max.toArray()).every(Number.isFinite)) return null;
  if (!Number.isFinite(aspect) || aspect <= 0 || !Number.isFinite(fov) || fov <= 1 || fov >= 179) return null;
  const target = bounds.getCenter(new THREE.Vector3());
  const radius = Math.max(bounds.getSize(new THREE.Vector3()).length() / 2, 0.001);
  const back = direction.lengthSq() > 1e-12 ? direction.clone().normalize() : new THREE.Vector3(0, 0, 1);
  const right = up.clone().cross(back).normalize();
  if (right.lengthSq() < 1e-12) right.set(1, 0, 0).applyQuaternion(new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 0, 1), back));
  const vertical = back.clone().cross(right).normalize();
  const tangent = Math.tan(THREE.MathUtils.degToRad(fov) / 2);
  let distance = radius * 0.01;
  for (const x of [bounds.min.x, bounds.max.x]) for (const y of [bounds.min.y, bounds.max.y]) for (const z of [bounds.min.z, bounds.max.z]) {
    const offset = new THREE.Vector3(x, y, z).sub(target);
    distance = Math.max(distance, offset.dot(back) + Math.max(
      Math.abs(offset.dot(right)) / (tangent * aspect), Math.abs(offset.dot(vertical)) / tangent,
    ) * 1.15 + radius * 0.05);
  }
  return { position: target.clone().addScaledVector(back, distance), target, up: vertical, fov, radius };
}
