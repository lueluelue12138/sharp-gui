import * as THREE from 'three';

export const CAMERA_PATH_LAYER = 31;

/** Sample every segment, including each keyframe even when durations differ greatly. */
export function cameraPathSampleTimes(frames: readonly { seconds: number }[]): number[] {
  const segments = frames.length - 1;
  if (segments < 1) return frames.length ? [0] : [];
  const steps = Math.floor(Math.min(2048, Math.max(64, frames.length * 32)) / segments);
  const times = [0];
  let start = 0;
  for (let index = 1; index < frames.length; index += 1) {
    for (let sample = 1; sample <= steps; sample += 1) {
      times.push(start + (sample === steps ? frames[index].seconds : frames[index].seconds * sample / steps));
    }
    start += frames[index].seconds;
  }
  return times;
}

/** Display-length frustum: exact angle/aspect, deliberately not the far clip plane. */
export function cameraFrustumVertices(length: number, fov: number, aspect: number): number[] {
  const height = length * Math.tan(THREE.MathUtils.degToRad(fov) / 2);
  const width = height * aspect;
  const corners = [[-width, -height, -length], [width, -height, -length],
    [width, height, -length], [-width, height, -length]];
  const vertices: number[] = [];
  for (let i = 0; i < 4; i += 1) {
    vertices.push(0, 0, 0, ...corners[i], ...corners[i], ...corners[(i + 1) % 4]);
  }
  // Top notch makes roll and camera-up visible in the overview.
  vertices.push(-width * 0.3, height, -length, 0, height * 1.35, -length,
    0, height * 1.35, -length, width * 0.3, height, -length,
    0, 0, 0, 0, 0, -length * 1.25);
  return vertices;
}

export function isolateCameraPath(object: THREE.Object3D) {
  object.traverse(child => { child.layers.set(CAMERA_PATH_LAYER); child.renderOrder = 1000; });
}

export function disposeCameraPath(object: THREE.Object3D) {
  object.traverse(child => {
    if (child instanceof THREE.Mesh || child instanceof THREE.Line || child instanceof THREE.Sprite) {
      if (child instanceof THREE.Mesh || child instanceof THREE.Line) child.geometry.dispose();
      const materials = Array.isArray(child.material) ? child.material : [child.material];
      for (const material of materials) {
        if ('map' in material && material.map instanceof THREE.Texture) material.map.dispose();
        material.dispose();
      }
    }
  });
  object.removeFromParent();
  object.clear();
}
