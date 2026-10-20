import assert from 'node:assert/strict';
import { it } from 'node:test';
import * as THREE from 'three';
import { animationDuration, animationFrameCount, animationFrameTime, applyCameraPose, captureCameraPose, parseCameraAnimation, sampleCameraAnimation } from './cameraAnimation.js';
import type { CameraKeyframe } from './cameraAnimation.js';
import { createWebm, encodeAnimationVideo } from './webmVideo.js';
import { cameraFrustumVertices, CAMERA_PATH_LAYER, cameraPathSampleTimes, disposeCameraPath, isolateCameraPath } from './cameraPathGeometry.js';

const a: CameraKeyframe = { id: 'a', seconds: 3, position: [0, 0, 5], quaternion: [0, 0, 0, 1], target: [0, 0, 0], fov: 60 };
const b: CameraKeyframe = { ...a, id: 'b', seconds: 2, position: [10, 2, 5], target: [10, 2, 0], fov: 40 };
const project = { version: 1, frames: [a, b], easing: 'smooth', portrait: false };

it('duration ignores first frame and samples both exact endpoints', () => {
  assert.equal(animationDuration([a, b]), 2);
  assert.deepEqual(sampleCameraAnimation([a, b], -10, 'linear'), a);
  assert.deepEqual(sampleCameraAnimation([a, b], 5, 'linear'), b);
  assert.equal(sampleCameraAnimation([], 0, 'linear'), null);
});
it('linear and eased segments interpolate position, target and lens consistently', () => {
  assert.deepEqual(sampleCameraAnimation([a, b], 1, 'linear')?.position, [5, 1, 5]);
  assert.equal(sampleCameraAnimation([a, b], 1, 'linear')?.fov, 50);
  assert.equal(sampleCameraAnimation([a, b], 0.5, 'smooth')?.position[0], 1.5625);
});
it('quaternion interpolation takes shortest rotation across ±180°', () => {
  const axis = new THREE.Vector3(0, 1, 0);
  const left = { ...a, quaternion: new THREE.Quaternion().setFromAxisAngle(axis, THREE.MathUtils.degToRad(179)).toArray() };
  const right = { ...b, quaternion: new THREE.Quaternion().setFromAxisAngle(axis, THREE.MathUtils.degToRad(-179)).toArray() };
  const q = new THREE.Quaternion().fromArray(sampleCameraAnimation([left, right], 1, 'linear')!.quaternion);
  assert.ok(q.angleTo(new THREE.Quaternion().setFromAxisAngle(axis, Math.PI)) < 1e-8);
});
it('camera capture/apply preserves tilted up and roll without touching model data', () => {
  const camera = new THREE.PerspectiveCamera(65);
  camera.position.set(2, 3, 8); camera.rotation.set(0.2, 0.3, 0.4);
  const pose = captureCameraPose(camera, new THREE.Vector3(1, 2, 3));
  const restored = new THREE.PerspectiveCamera(); const target = new THREE.Vector3();
  applyCameraPose(restored, target, pose);
  assert.ok(restored.quaternion.angleTo(camera.quaternion) < 1e-8);
  assert.deepEqual(target.toArray(), pose.target);
  assert.ok(restored.up.distanceTo(new THREE.Vector3(0, 1, 0).applyQuaternion(camera.quaternion)) < 1e-9);
});
it('continuous glide keeps position and angular velocity through unevenly timed interior frames', () => {
  const axis = new THREE.Vector3(0, 1, 0);
  const frames = [0, 0.4, 1, 1.3].map((angle, i) => ({ ...a, id: String(i), seconds: [3, 1, 3, 2][i],
    position: [i * 2, i % 2, 5] as [number, number, number],
    quaternion: new THREE.Quaternion().setFromAxisAngle(axis, angle).toArray() }));
  const h = 1e-4;
  for (const time of [1, 4]) {
    const left = sampleCameraAnimation(frames, time - h, 'cinematic')!;
    const center = sampleCameraAnimation(frames, time, 'cinematic')!;
    const right = sampleCameraAnimation(frames, time + h, 'cinematic')!;
    const v1 = new THREE.Vector3().fromArray(center.position).sub(new THREE.Vector3().fromArray(left.position)).divideScalar(h);
    const v2 = new THREE.Vector3().fromArray(right.position).sub(new THREE.Vector3().fromArray(center.position)).divideScalar(h);
    assert.ok(v1.distanceTo(v2) < 0.002); assert.ok(v1.length() > 0.2);
    const q = new THREE.Quaternion().fromArray(center.quaternion);
    const before = q.angleTo(new THREE.Quaternion().fromArray(left.quaternion)) / h;
    const after = q.angleTo(new THREE.Quaternion().fromArray(right.quaternion)) / h;
    assert.ok(Math.abs(before - after) < 0.002); assert.ok(before > 0.05);
  }
});
it('all curves preserve endpoints and normalized orientation; soft landing has gentle acceleration', () => {
  for (const curve of ['cinematic', 'smooth', 'sine', 'quintic', 'linear'] as const) {
    assert.deepEqual(sampleCameraAnimation([a, b], 0, curve), a);
    assert.deepEqual(sampleCameraAnimation([a, b], 3, curve), b);
    assert.ok(Math.abs(new THREE.Quaternion().fromArray(sampleCameraAnimation([a, b], 1, curve)!.quaternion).length() - 1) < 1e-10);
    assert.equal(parseCameraAnimation({ ...project, easing: curve }).easing, curve);
  }
  assert.ok(sampleCameraAnimation([a, b], 0.01, 'quintic')!.position[0] < sampleCameraAnimation([a, b], 0.01, 'smooth')!.position[0]);
});
it('sampling and validating do not mutate the input or preserve foreign fields', () => {
  const original = JSON.stringify(project);
  sampleCameraAnimation(project.frames, 0.4, 'smooth');
  const parsed = parseCameraAnimation({ ...project, secret: 'unused' });
  assert.equal(JSON.stringify(project), original);
  assert.equal('secret' in parsed, false);
  assert.notEqual(parsed.frames, project.frames);
});
it('invalid projects, non-finite coordinates and zero quaternions are rejected', () => {
  for (const value of [null, {}, { ...project, version: 2 }, { ...project, frames: [{ ...a, position: [NaN, 0, 0] }] },
    { ...project, frames: [{ ...a, quaternion: [0, 0, 0, 0] }] }, { ...project, frames: [{ ...a, seconds: 0 }] },
    { ...project, frames: [{ ...a, fov: Infinity }] }, { ...project, frames: [{ ...a, position: [1, 2] }] },
    { ...project, frames: Array.from({ length: 101 }, () => a) },
    { ...project, frames: [a, { ...b, seconds: 60 }, { ...b, seconds: 60 }, b] }]) {
    assert.throws(() => parseCameraAnimation(value), /animationInvalidProject/);
  }
});
it('export frame count has exact cadence, inclusive camera endpoints, and limits', () => {
  for (const fps of [24, 30, 60]) {
    const count = animationFrameCount(3, fps);
    assert.equal(count, 3 * fps);
    assert.equal(animationFrameTime(0, count, 3), 0);
    assert.equal(animationFrameTime(count - 1, count, 3), 3);
  }
  for (const seconds of [0, -1, NaN, Infinity, 121]) assert.throws(() => animationFrameCount(seconds, 30));
  assert.throws(() => animationFrameCount(3, 25));
});
it('WebM writes standard header, dimensions, codec, duration and multiple clusters', async () => {
  const blob = createWebm([
    { bytes: new Uint8Array([1, 2, 3]), timestamp: 0, key: true },
    { bytes: new Uint8Array([4, 5]), timestamp: 33333, key: false },
    { bytes: new Uint8Array([6]), timestamp: 2000000, key: true },
  ], 1920, 1080, 30, 'vp9');
  const bytes = new Uint8Array(await blob.arrayBuffer());
  assert.deepEqual([...bytes.slice(0, 4)], [0x1a, 0x45, 0xdf, 0xa3]);
  const text = new TextDecoder().decode(bytes);
  assert.ok(text.includes('webm')); assert.ok(text.includes('V_VP9'));
  assert.equal(blob.type, 'video/webm');
  assert.equal(bytes.filter((_, index) => bytes[index] === 0x1f && bytes[index + 1] === 0x43 && bytes[index + 2] === 0xb6 && bytes[index + 3] === 0x75).length, 2);
});
it('missing WebCodecs gives a stable capability error before attempting to render', async () => {
  if (typeof VideoEncoder !== 'undefined') return;
  await assert.rejects(encodeAnimationVideo({ width: 1920, height: 1080, fps: 30, frames: 30,
    signal: new AbortController().signal, onProgress: () => {},
    render: () => { throw new Error('must not render'); },
  }), /animationCodecUnavailable/);
});
it('overview frustum preserves the real field of view and aspect', () => {
  const length = 2; const aspect = 16 / 9;
  const vertices = cameraFrustumVertices(length, 60, aspect);
  assert.ok(Math.abs(vertices[3] / vertices[4] - aspect) < 1e-9);
  assert.ok(Math.abs(Math.abs(vertices[4]) / length - Math.tan(Math.PI / 6)) < 1e-9);
  assert.equal(vertices[5], -length);
  const q = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), Math.PI / 2);
  const forward = new THREE.Vector3(0, 0, -length).applyQuaternion(q);
  assert.ok(forward.distanceTo(new THREE.Vector3(-length, 0, 0)) < 1e-9);
});
it('overview path includes short segments and every exact keyframe within a bounded sample budget', () => {
  const frames = [{ ...a, seconds: 9 }, { ...b, seconds: 0.1 }, { ...a, id: 'c', seconds: 60 }];
  const times = cameraPathSampleTimes(frames);
  assert.equal(times[0], 0);
  assert.equal(times.at(-1), 60.1);
  assert.ok(times.includes(0.1));
  assert.ok(times.some(time => time > 0 && time < 0.1));
  for (let i = 1; i < times.length; i += 1) assert.ok(times[i] > times[i - 1]);
  const last = sampleCameraAnimation(frames, times.at(-1)!, 'cinematic');
  assert.deepEqual(last?.position, frames[2].position);
  assert.ok(cameraPathSampleTimes(Array.from({ length: 100 }, () => a)).length <= 2049);
  assert.deepEqual(cameraPathSampleTimes([]), []);
});
it('all overview children are invisible to ordinary export cameras', () => {
  const group = new THREE.Group();
  group.add(new THREE.Line(new THREE.BufferGeometry(), new THREE.LineBasicMaterial()), new THREE.Sprite());
  isolateCameraPath(group);
  const shotCamera = new THREE.PerspectiveCamera(); const overviewCamera = shotCamera.clone();
  overviewCamera.layers.enable(CAMERA_PATH_LAYER);
  group.traverse(child => {
    assert.equal(shotCamera.layers.test(child.layers), false);
    assert.equal(overviewCamera.layers.test(child.layers), true);
  });
  assert.equal(shotCamera.layers.mask, 1);
  disposeCameraPath(group);
});
it('overview cleanup releases owned texture/material/geometry without disposing shared sprite geometry', () => {
  const root = new THREE.Group(); const group = new THREE.Group(); root.add(group);
  const geometry = new THREE.BufferGeometry(); const material = new THREE.LineBasicMaterial();
  const texture = new THREE.Texture(); const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: texture }));
  group.add(new THREE.Line(geometry, material), sprite);
  let geometryCount = 0; let materialCount = 0; let textureCount = 0; let sharedCount = 0;
  geometry.addEventListener('dispose', () => { geometryCount += 1; });
  material.addEventListener('dispose', () => { materialCount += 1; });
  texture.addEventListener('dispose', () => { textureCount += 1; });
  const sharedListener = () => { sharedCount += 1; };
  sprite.geometry.addEventListener('dispose', sharedListener);
  disposeCameraPath(group);
  sprite.geometry.removeEventListener('dispose', sharedListener);
  assert.deepEqual([geometryCount, materialCount, textureCount, sharedCount], [1, 1, 1, 0]);
  assert.equal(root.children.length, 0); assert.equal(group.children.length, 0);
});
