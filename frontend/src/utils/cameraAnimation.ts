import * as THREE from 'three';

export interface CameraPose {
  position: [number, number, number];
  quaternion: [number, number, number, number];
  target: [number, number, number];
  fov: number;
}

export interface CameraKeyframe extends CameraPose {
  id: string;
  seconds: number;
}

export interface CameraAnimationProject {
  version: 1;
  frames: CameraKeyframe[];
  easing: CameraAnimationCurve;
  portrait: boolean;
}

export const CAMERA_ANIMATION_CURVES = ['cinematic', 'smooth', 'sine', 'quintic', 'linear'] as const;
export type CameraAnimationCurve = typeof CAMERA_ANIMATION_CURVES[number];

export const MAX_KEYFRAMES = 100;
export const MAX_ANIMATION_SECONDS = 120;

export function animationDuration(frames: CameraKeyframe[]): number {
  return frames.slice(1).reduce((sum, frame) => sum + frame.seconds, 0);
}

export function captureCameraPose(camera: THREE.PerspectiveCamera, target: THREE.Vector3): CameraPose {
  return {
    position: camera.position.toArray(), quaternion: camera.quaternion.toArray(),
    target: target.toArray(), fov: camera.fov,
  };
}

export function applyCameraPose(camera: THREE.PerspectiveCamera, target: THREE.Vector3, pose: CameraPose) {
  camera.position.fromArray(pose.position);
  camera.quaternion.fromArray(pose.quaternion).normalize();
  camera.up.set(0, 1, 0).applyQuaternion(camera.quaternion);
  target.fromArray(pose.target);
  camera.fov = pose.fov;
  camera.updateProjectionMatrix();
  camera.updateMatrixWorld(true);
}

function easingValue(t: number, curve: CameraAnimationCurve) {
  if (curve === 'smooth') return t * t * (3 - 2 * t);
  if (curve === 'sine') return (1 - Math.cos(Math.PI * t)) / 2;
  if (curve === 'quintic') return t * t * t * (t * (t * 6 - 15) + 10);
  return t;
}

function smoothVector(frames: CameraKeyframe[], index: number, key: 'position' | 'target', t: number) {
  const vector = (i: number) => new THREE.Vector3().fromArray(frames[i][key]);
  const tangent = (i: number) => i === 0 || i === frames.length - 1 ? new THREE.Vector3()
    : vector(i + 1).sub(vector(i - 1)).divideScalar(frames[i].seconds + frames[i + 1].seconds);
  const seconds = frames[index + 1].seconds;
  return vector(index).multiplyScalar(2 * t ** 3 - 3 * t * t + 1)
    .addScaledVector(tangent(index), (t ** 3 - 2 * t * t + t) * seconds)
    .addScaledVector(vector(index + 1), -2 * t ** 3 + 3 * t * t)
    .addScaledVector(tangent(index + 1), (t ** 3 - t * t) * seconds).toArray();
}

function smoothFov(frames: CameraKeyframe[], index: number, t: number) {
  const tangent = (i: number) => i === 0 || i === frames.length - 1 ? 0
    : (frames[i + 1].fov - frames[i - 1].fov) / (frames[i].seconds + frames[i + 1].seconds);
  const seconds = frames[index + 1].seconds;
  return THREE.MathUtils.clamp(frames[index].fov * (2 * t ** 3 - 3 * t * t + 1)
    + tangent(index) * (t ** 3 - 2 * t * t + t) * seconds
    + frames[index + 1].fov * (-2 * t ** 3 + 3 * t * t)
    + tangent(index + 1) * (t ** 3 - t * t) * seconds, 1, 170);
}

function quaternionLog(q: THREE.Quaternion) {
  // Always use the shortest rotation, including equivalent antipodal encodings.
  if (q.w < 0) q.set(-q.x, -q.y, -q.z, -q.w);
  const length = Math.hypot(q.x, q.y, q.z);
  return length < 1e-12 ? new THREE.Vector3() : new THREE.Vector3(q.x, q.y, q.z).multiplyScalar(Math.atan2(length, q.w) / length);
}
function quaternionExp(v: THREE.Vector3) {
  const length = v.length();
  if (length < 1e-12) return new THREE.Quaternion();
  const scale = Math.sin(length) / length;
  return new THREE.Quaternion(v.x * scale, v.y * scale, v.z * scale, Math.cos(length));
}

/** Time-weighted quaternion Bezier; endpoint velocities match across segments. */
function smoothQuaternion(frames: CameraKeyframe[], index: number, t: number) {
  const quaternion = (i: number) => new THREE.Quaternion().fromArray(frames[i].quaternion).normalize();
  const velocity = (i: number) => {
    if (i === 0 || i === frames.length - 1) return new THREE.Vector3();
    const inverse = quaternion(i).invert();
    const before = frames[i].seconds; const after = frames[i + 1].seconds;
    const incoming = quaternionLog(inverse.clone().multiply(quaternion(i - 1))).multiplyScalar(-1 / before);
    const outgoing = quaternionLog(inverse.multiply(quaternion(i + 1))).divideScalar(after);
    return incoming.multiplyScalar(after / (before + after)).addScaledVector(outgoing, before / (before + after));
  };
  const a = quaternion(index); const b = quaternion(index + 1);
  const seconds = frames[index + 1].seconds;
  const c = a.clone().multiply(quaternionExp(velocity(index).multiplyScalar(seconds / 3)));
  const d = b.clone().multiply(quaternionExp(velocity(index + 1).multiplyScalar(-seconds / 3)));
  const ab = a.clone().slerp(c, t); const bc = c.clone().slerp(d, t); const cd = d.clone().slerp(b, t);
  return ab.slerp(bc, t).slerp(bc.slerp(cd, t), t).normalize().toArray();
}

/** Deterministic sampling; continuous mode preserves velocity through interior shots. */
export function sampleCameraAnimation(frames: CameraKeyframe[], seconds: number, easing: CameraAnimationCurve): CameraPose | null {
  if (!frames.length) return null;
  if (frames.length === 1 || seconds <= 0) return frames[0];
  let remaining = seconds;
  for (let index = 1; index < frames.length; index += 1) {
    const a = frames[index - 1];
    const b = frames[index];
    if (remaining <= b.seconds) {
      const raw = THREE.MathUtils.clamp(remaining / b.seconds, 0, 1);
      const t = easingValue(raw, easing);
      const continuous = easing === 'cinematic';
      return {
        position: continuous ? smoothVector(frames, index - 1, 'position', t) : new THREE.Vector3().fromArray(a.position).lerp(new THREE.Vector3().fromArray(b.position), t).toArray(),
        quaternion: continuous ? smoothQuaternion(frames, index - 1, t) : new THREE.Quaternion().fromArray(a.quaternion).slerp(new THREE.Quaternion().fromArray(b.quaternion), t).toArray(),
        target: continuous ? smoothVector(frames, index - 1, 'target', t) : new THREE.Vector3().fromArray(a.target).lerp(new THREE.Vector3().fromArray(b.target), t).toArray(),
        fov: continuous ? smoothFov(frames, index - 1, t) : THREE.MathUtils.lerp(a.fov, b.fov, t),
      };
    }
    remaining -= b.seconds;
  }
  return frames[frames.length - 1];
}

export function parseCameraAnimation(value: unknown): CameraAnimationProject {
  const fail = (): never => { throw new Error('animationInvalidProject'); };
  if (!value || typeof value !== 'object') return fail();
  const data = value as Record<string, unknown>;
  if (data.version !== 1 || !Array.isArray(data.frames) || data.frames.length > MAX_KEYFRAMES
    || !CAMERA_ANIMATION_CURVES.includes(data.easing as CameraAnimationCurve) || typeof data.portrait !== 'boolean') return fail();
  const vector = (v: unknown, length: number): number[] => {
    if (!Array.isArray(v) || v.length !== length || !v.every(n => typeof n === 'number' && Number.isFinite(n) && Math.abs(n) <= 1e9)) return fail();
    return [...v];
  };
  const frames = data.frames.map((entry: unknown, index) => {
    if (!entry || typeof entry !== 'object') return fail();
    const frame = entry as Record<string, unknown>;
    const q = new THREE.Quaternion().fromArray(vector(frame.quaternion, 4));
    if (q.length() < 0.001 || q.length() > 2 || typeof frame.fov !== 'number'
      || !Number.isFinite(frame.fov) || frame.fov < 1 || frame.fov > 170
      || typeof frame.seconds !== 'number' || !Number.isFinite(frame.seconds) || frame.seconds < 0.1 || frame.seconds > 60) return fail();
    return {
      id: `loaded-${index}`, position: vector(frame.position, 3) as CameraPose['position'],
      quaternion: q.normalize().toArray(), target: vector(frame.target, 3) as CameraPose['target'],
      fov: frame.fov, seconds: frame.seconds,
    };
  });
  if (animationDuration(frames) > MAX_ANIMATION_SECONDS) return fail();
  return { version: 1, frames, easing: data.easing as CameraAnimationProject['easing'], portrait: data.portrait };
}

export function animationFrameCount(duration: number, fps: number): number {
  if (!Number.isFinite(duration) || duration <= 0 || duration > MAX_ANIMATION_SECONDS || ![24, 30, 60].includes(fps)) throw new Error('animationLimits');
  return Math.max(2, Math.round(duration * fps));
}

export function animationFrameTime(index: number, count: number, duration: number): number {
  // Include both recorded endpoints; timestamps still use an exact constant rate.
  return duration * index / Math.max(1, count - 1);
}
