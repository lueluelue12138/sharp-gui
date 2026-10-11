import assert from 'node:assert/strict';
import { it } from 'node:test';
import * as THREE from 'three';

import type { ViewerCameraHint } from '@/types/modelPreview';
import { createAlignedExport, resolveEditorOrigin, rotateModelAtOrigin } from './modelAlignment.js';
import { projectResizeDirection, resizeBoxFace } from './regionResize.js';
import {
  combineSelection,
  countMask,
  createRectanglePreview,
  encodeMask,
  inRegion,
  inScreenRectangle,
  maskBit,
  selectPoints,
  setMaskBit,
  splatInScreenRectangle,
  splatInRegion,
  writeSplatCovariance,
} from './modelEditor.js';

const displayBasis = new THREE.Matrix4().makeRotationX(Math.PI).scale(new THREE.Vector3(2, 2, 2));

it('dragging any box face preserves the opposite boundary and other two dimensions', () => {
  const region = { center: [1, 2, 3] as [number, number, number], size: [4, 6, 8] as [number, number, number], radius: 2 };
  for (let axis = 0; axis < 3; axis++) for (const sign of [-1, 1]) {
    const before = region.center[axis] - sign * region.size[axis] / 2;
    const next = resizeBoxFace(region, axis, sign, 2.5);
    assert.equal(next.center[axis] - sign * next.size[axis] / 2, before);
    assert.equal(next.size[axis], region.size[axis] + 2.5);
    for (const other of [0, 1, 2].filter((value) => value !== axis)) {
      assert.equal(next.center[other], region.center[other]);
      assert.equal(next.size[other], region.size[other]);
    }
  }
  assert.deepEqual(region.center, [1, 2, 3]);
});

it('box face cannot cross its opposite, and can be dragged outward again after reaching the limit', () => {
  const region = { center: [0, 0, 0] as [number, number, number], size: [2, 2, 2] as [number, number, number], radius: 1 };
  const small = resizeBoxFace(region, 0, 1, -100);
  assert.ok(small.size[0] > 0 && small.size[0] < 0.00002);
  assert.ok(Math.abs(small.center[0] - small.size[0] / 2 + 1) < 1e-12);
  const expanded = resizeBoxFace(small, 0, 1, 0.5);
  assert.ok(Math.abs(expanded.size[0] - 0.50001) < 1e-12);
  assert.ok(Math.abs(expanded.center[0] - expanded.size[0] / 2 + 1) < 1e-12);
});

it('boundary screen directions match perspective projection across camera angles and aspect ratios', () => {
  const camera = new THREE.PerspectiveCamera(55, 1.6, 0.01, 1000);
  camera.position.set(5, 4, 7);
  camera.lookAt(0, 0, 0);
  camera.updateMatrixWorld(true);
  const point = new THREE.Vector3(1, .5, -.5);
  for (const size of [[800, 500], [1440, 900]]) {
    for (const direction of [new THREE.Vector3(1, 0, 0), new THREE.Vector3(0, -1, 0), new THREE.Vector3(0, 0, 1)]) {
      const axis = projectResizeDirection(camera, point, direction, size[0], size[1]);
      assert.ok(axis);
      const a = point.clone().project(camera), b = point.clone().addScaledVector(direction, 1e-6).project(camera);
      assert.ok(Math.abs(axis.x - (b.x - a.x) * size[0] / 2e-6) < 1e-4);
      assert.ok(Math.abs(axis.y + (b.y - a.y) * size[1] / 2e-6) < 1e-4);
    }
  }
  assert.equal(projectResizeDirection(camera, camera.position.clone(), new THREE.Vector3(1, 0, 0), 800, 500), null);
  camera.position.set(0, 0, 10);
  camera.lookAt(0, 0, 0);
  camera.updateMatrixWorld(true);
  assert.equal(projectResizeDirection(camera, new THREE.Vector3(1, 1, 0), new THREE.Vector3(0, 0, 1), 800, 500), null);
});

it('file origin is always the transformed zero, independent of viewing and selection centers', () => {
  const model = new THREE.Matrix4().compose(new THREE.Vector3(1, 2, 3),
    new THREE.Quaternion().setFromEuler(new THREE.Euler(Math.PI, .3, -.1)), new THREE.Vector3(2, 2, 2));
  const before = model.toArray();
  const origin = resolveEditorOrigin(model);
  assert.deepEqual(origin.toArray(), [1, 2, 3]);
  origin.x = 10;
  assert.deepEqual(model.toArray(), before);
});

it('a reconstruction with an off-center viewing target does not pretend its file origin is centered', () => {
  const model = new THREE.Matrix4().compose(new THREE.Vector3(),
    new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), -Math.PI / 2),
    new THREE.Vector3(2, 2, 2));
  const target = new THREE.Vector3(-.5249638860014039, -.014037666847877883, -2.288947146742124).applyMatrix4(model);
  assert.ok(target.distanceTo(new THREE.Vector3(-1.0499277720028077, -4.577894293484248, .028075333695755766)) < 1e-12);
  assert.deepEqual(resolveEditorOrigin(model).toArray(), [0, 0, 0]);
  assert.ok(target.distanceTo(resolveEditorOrigin(model)) > 4);
});

it('calibrates around the chosen origin, retaining the entry orientation and scale', () => {
  const origin = new THREE.Vector3(1.2, -.7, 2);
  const baseline = new THREE.Quaternion().setFromEuler(new THREE.Euler(Math.PI, .3, -.2));
  const model = new THREE.Matrix4().compose(new THREE.Vector3(.4, 2, -1), baseline, new THREE.Vector3(2, 2, 2));
  const originInModel = origin.clone().applyMatrix4(model.clone().invert());
  const rotation = new THREE.Quaternion().setFromEuler(new THREE.Euler(.25, -.1, .6));
  const calibrated = rotateModelAtOrigin(model, origin, new THREE.Quaternion(), rotation);
  assert.ok(originInModel.applyMatrix4(calibrated).distanceTo(origin) < 1e-12);
  const position = new THREE.Vector3(), orientation = new THREE.Quaternion(), scale = new THREE.Vector3();
  calibrated.decompose(position, orientation, scale);
  assert.ok(orientation.angleTo(rotation.clone().multiply(baseline)) < 1e-7);
  assert.ok(scale.distanceTo(new THREE.Vector3(2, 2, 2)) < 1e-12);
  assert.ok(rotateModelAtOrigin(calibrated, origin, rotation, new THREE.Quaternion())
    .elements.every((value, i) => Math.abs(value - model.elements[i]) < 1e-12));
});

it('numeric angles and a world-space rotation handle apply the same pivot transform', () => {
  const origin = new THREE.Vector3(-2, 3, 1);
  const previous = new THREE.Quaternion().setFromEuler(new THREE.Euler(.3, .5, -.2));
  const delta = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 0, 1), .4);
  const next = delta.clone().multiply(previous);
  const model = new THREE.Matrix4().compose(new THREE.Vector3(7, 2, -1), previous, new THREE.Vector3(1, 1, 1));
  const handleStart = new THREE.Matrix4().compose(origin, previous, new THREE.Vector3(1, 1, 1));
  const handleEnd = new THREE.Matrix4().compose(origin, next, new THREE.Vector3(1, 1, 1));
  const fromHandle = handleEnd.multiply(handleStart.invert()).multiply(model);
  const fromNumbers = rotateModelAtOrigin(model, origin, previous, next);
  assert.ok(fromNumbers.elements.every((value, i) => Math.abs(value - fromHandle.elements[i]) < 1e-12));
});

it('changing pivot midway keeps the current geometry still, and resetting restores only orientation', () => {
  const model = new THREE.Matrix4().makeTranslation(1, 2, 3);
  const rotation = new THREE.Quaternion().setFromEuler(new THREE.Euler(.4, -.2, .1));
  const calibrated = rotateModelAtOrigin(model, new THREE.Vector3(), new THREE.Quaternion(), rotation);
  const beforeOriginChange = calibrated.toArray();
  const origin = new THREE.Vector3(5, -2, 1);
  createAlignedExport(calibrated, origin, {
    position: [0, 0, 10], target: [0, 0, 0], up: [0, 1, 0], fov_y_degrees: 50, aspect: 1,
  }, displayBasis);
  assert.deepEqual(calibrated.toArray(), beforeOriginChange);
  const restored = rotateModelAtOrigin(calibrated, origin, rotation, new THREE.Quaternion());
  const orientation = new THREE.Quaternion().setFromRotationMatrix(restored);
  assert.ok(orientation.angleTo(new THREE.Quaternion()) < 1e-7);
  assert.deepEqual(origin.toArray(), [5, -2, 1]);
});

it('exports the chosen origin as zero and rebases the saved camera without changing composition', () => {
  const origin = new THREE.Vector3(2, -.5, 3);
  const model = new THREE.Matrix4().compose(new THREE.Vector3(.2, .3, .4),
    new THREE.Quaternion().setFromEuler(new THREE.Euler(.1, .2, .3)), new THREE.Vector3(2, 2, 2));
  const hint: ViewerCameraHint = { position: [4, 2, 12], target: [1, 0, 1], up: [0, 1, 0], fov_y_degrees: 55, aspect: 1.5 };
  const modelBefore = model.toArray(), hintBefore = structuredClone(hint);
  const exported = createAlignedExport(model, origin, hint, displayBasis);
  const exportMatrix = new THREE.Matrix4().fromArray(exported.matrix);
  const localOrigin = origin.clone().applyMatrix4(model.clone().invert());
  assert.ok(localOrigin.applyMatrix4(exportMatrix).length() < 1e-12);
  const makeCamera = (cameraHint: typeof hint) => {
    const camera = new THREE.PerspectiveCamera(cameraHint.fov_y_degrees, cameraHint.aspect, .01, 100);
    camera.position.fromArray(cameraHint.position);
    camera.up.fromArray(cameraHint.up);
    camera.lookAt(new THREE.Vector3().fromArray(cameraHint.target));
    camera.updateMatrixWorld(true);
    return camera;
  };
  const point = new THREE.Vector3(.5, .8, -.3);
  const before = point.clone().applyMatrix4(model).project(makeCamera(hint));
  const reopenedCamera = {
    ...exported.camera,
    position: new THREE.Vector3().fromArray(exported.camera.position).applyMatrix4(displayBasis).toArray() as [number, number, number],
    target: new THREE.Vector3().fromArray(exported.camera.target).applyMatrix4(displayBasis).toArray() as [number, number, number],
    up: new THREE.Vector3().fromArray(exported.camera.up).transformDirection(displayBasis).toArray() as [number, number, number],
  };
  const after = point.clone().applyMatrix4(exportMatrix).applyMatrix4(displayBasis).project(makeCamera(reopenedCamera));
  assert.ok(before.distanceTo(after) < 1e-12);
  assert.deepEqual(model.toArray(), modelBefore);
  assert.deepEqual(hint, hintBefore);
});

it('saving without edits preserves ordinary PLY coordinates and scales without a private display override', () => {
  const sourceMatrix = displayBasis.clone();
  const camera: ViewerCameraHint = { position: [2, 3, 8], target: [0, 0, 0], up: [0, 1, 0], fov_y_degrees: 50, aspect: 1 };
  const exported = createAlignedExport(sourceMatrix, resolveEditorOrigin(sourceMatrix), camera, displayBasis);
  assert.ok(exported.matrix.every((value, i) => Math.abs(value - new THREE.Matrix4().elements[i]) < 1e-12));
});

it('converts video alignment, chosen origin and Gaussian orientation back to PLY space for generic reimport', () => {
  const videoBasis = new THREE.Matrix4().makeRotationX(-Math.PI / 2).scale(new THREE.Vector3(2, 2, 2));
  const origin = new THREE.Vector3(-1.05, -4.58, .028);
  const calibrated = rotateModelAtOrigin(videoBasis, origin, new THREE.Quaternion(),
    new THREE.Quaternion().setFromEuler(new THREE.Euler(.2, -.3, .4)));
  const camera: ViewerCameraHint = { position: [2, 3, 8], target: origin.toArray(), up: [0, 1, 0], fov_y_degrees: 50, aspect: 1 };
  const exported = createAlignedExport(calibrated, origin, camera, displayBasis);
  const fileMatrix = new THREE.Matrix4().fromArray(exported.matrix);
  const rawOrigin = origin.clone().applyMatrix4(calibrated.clone().invert());
  assert.ok(rawOrigin.clone().applyMatrix4(fileMatrix).length() < 1e-12);
  const point = new THREE.Vector3(.5, -.3, -2);
  assert.ok(point.clone().applyMatrix4(fileMatrix).applyMatrix4(displayBasis)
    .distanceTo(point.clone().applyMatrix4(calibrated).sub(origin)) < 1e-12);
  const filePosition = new THREE.Vector3(), fileRotation = new THREE.Quaternion(), fileScale = new THREE.Vector3();
  fileMatrix.decompose(filePosition, fileRotation, fileScale);
  assert.ok(fileScale.distanceTo(new THREE.Vector3(1, 1, 1)) < 1e-12);
  const beforeRotation = new THREE.Quaternion().setFromRotationMatrix(calibrated.clone().scale(new THREE.Vector3(.5, .5, .5)));
  const reopenedRotation = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), Math.PI).multiply(fileRotation);
  assert.ok(beforeRotation.angleTo(reopenedRotation) < 1e-7);
});

it('selects a visible ellipse crossing the rectangle even when its center is outside', () => {
  const covariance = new Float32Array(6);
  writeSplatCovariance(covariance, 0, {x: .2, y: .1, z: .01}, {x: 0, y: 0, z: 0, w: 1}, 3);
  const matrix = new THREE.Matrix4().elements;
  const rect = {left: .4, right: .6, top: .4, bottom: .6};
  assert.equal(splatInScreenRectangle(.7, 0, 0, covariance, 0, matrix, rect, 'center'), false);
  assert.equal(splatInScreenRectangle(.7, 0, 0, covariance, 0, matrix, rect, 'intersect'), true);
  assert.equal(splatInScreenRectangle(.7, 0, 0, covariance, 0, matrix, rect, 'contain'), false);
  assert.equal(splatInScreenRectangle(0, 0, 0, covariance, 0, matrix, rect, 'contain'), false);
  assert.equal(splatInScreenRectangle(0, 0, 0, covariance, 0, matrix, {left: 0, right: 1, top: 0, bottom: 1}, 'contain'), true);
});

it('ellipse intersection rejects empty corners of its bounding rectangle and honors rotation', () => {
  const covariance = new Float32Array(6);
  writeSplatCovariance(covariance, 0, {x: .2, y: .2, z: .01}, {x: 0, y: 0, z: 0, w: 1}, 1);
  const matrix = new THREE.Matrix4().elements;
  assert.equal(splatInScreenRectangle(0, 0, 0, covariance, 0, matrix, {left: .58, right: .6, top: .58, bottom: .6}, 'intersect'), false);
  const q = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 0, 1), Math.PI / 2);
  writeSplatCovariance(covariance, 0, {x: .4, y: .01, z: .01}, q, 1);
  assert.equal(splatInScreenRectangle(0, 0, 0, covariance, 0, matrix, {left: .49, right: .51, top: .65, bottom: .7}, 'intersect'), true);
  assert.equal(splatInScreenRectangle(0, 0, 0, covariance, 0, matrix, {left: .65, right: .7, top: .49, bottom: .51}, 'intersect'), false);
});

it('volume extent selection catches crossing splats and containment rejects protruding tails', () => {
  const covariance = new Float32Array(6);
  writeSplatCovariance(covariance, 0, {x: .2, y: .01, z: .01}, {x: 0, y: 0, z: 0, w: 1}, 3);
  const matrix = new THREE.Matrix4().makeScale(2, 2, 2).elements;
  const region = {center: [0, 0, 0] as [number, number, number], size: [2, 2, 2] as [number, number, number], radius: 1};
  assert.equal(splatInRegion(.6, 0, 0, covariance, 0, matrix, region, false, 'center'), false);
  assert.equal(splatInRegion(.6, 0, 0, covariance, 0, matrix, region, false, 'intersect'), true);
  assert.equal(splatInRegion(0, 0, 0, covariance, 0, matrix, region, false, 'contain'), false);
  assert.equal(splatInRegion(.6, 0, 0, covariance, 0, matrix, region, true, 'intersect'), true);
});

it('visible ellipse selection respects perspective, transformed models and clip planes', () => {
  const covariance = new Float32Array(6);
  writeSplatCovariance(covariance, 0, {x: .3, y: .01, z: .01}, {x: 0, y: 0, z: 0, w: 1}, 1);
  const camera = new THREE.PerspectiveCamera(60, 1, .1, 100);
  const projection = camera.projectionMatrix;
  const rectangle = {left: .4, right: .6, top: .4, bottom: .6};
  assert.equal(splatInScreenRectangle(.4, 0, -2, covariance, 0, projection.elements, rectangle, 'center'), false);
  assert.equal(splatInScreenRectangle(.4, 0, -2, covariance, 0, projection.elements, rectangle, 'intersect'), true);
  assert.equal(splatInScreenRectangle(.4, 0, -8, covariance, 0, projection.elements, rectangle, 'contain'), true);
  for (const z of [2, -.05, -110]) {
    assert.equal(splatInScreenRectangle(0, 0, z, covariance, 0, projection.elements, rectangle, 'intersect'), false);
  }
  const transformed = projection.clone().multiply(new THREE.Matrix4().makeTranslation(-2, 0, 0));
  assert.equal(splatInScreenRectangle(2.4, 0, -2, covariance, 0, transformed.elements, rectangle, 'intersect'), true);
  assert.equal(splatInScreenRectangle(2.4, 0, -2, covariance, 0, projection.elements, rectangle, 'intersect'), false);
});

it('rectangle release cancels delayed previews and never reads a cleared drag origin', () => {
  let scheduled: FrameRequestCallback | null = null;
  const updates: Array<object | null> = [];
  const preview = createRectanglePreview(
    (rectangle) => updates.push(rectangle),
    (callback) => { scheduled = callback; return 1; },
    () => { scheduled = null; },
  );
  const origin = { left: .1, right: .2, top: .3, bottom: .4 };
  preview.update(origin);
  origin.left = .9;
  const runFrame = () => { const callback = scheduled as FrameRequestCallback | null; callback?.(0); };
  runFrame();
  assert.deepEqual(updates, [{ left: .1, right: .2, top: .3, bottom: .4 }]);
  for (let i = 0; i < 100; i++) preview.update({ left: 0, top: 0, right: i / 100, bottom: 1 });
  preview.clear();
  runFrame();
  assert.deepEqual(updates.at(-1), null);
  assert.equal(updates.length, 2);
  preview.update({ left: 0, top: 0, right: 1, bottom: 1 });
  runFrame();
  assert.deepEqual(updates.at(-1), { left: 0, top: 0, right: 1, bottom: 1 });
});

it('a million-point rectangle uses a compact bitmap and yields before completing', async () => {
  const count = 1_000_003;
  const positions = new Float32Array(count * 3);
  const deleted = new Uint8Array(Math.ceil(count / 8));
  const projection = new THREE.Matrix4().elements;
  const rectangle = { left: 0, right: 1, top: 0, bottom: 1 };
  setMaskBit(deleted, count - 2);
  let yielded = false;
  setTimeout(() => { yielded = true; }, 0);
  const result = await selectPoints(positions, deleted,
    (x, y, z) => inScreenRectangle(x, y, z, projection, rectangle), () => false);
  assert.ok(result);
  assert.equal(yielded, true);
  assert.equal(result.byteLength, Math.ceil(count / 8));
  assert.equal(countMask(result), count - 1);
  assert.equal(result.at(-1), 5);
});

it('packs deletion indices in source order and leaves padding unset', () => {
  const mask = new Uint8Array(2);
  for (const i of [0, 7, 8]) setMaskBit(mask, i);
  assert.deepEqual([...mask], [129, 1]);
  assert.equal(encodeMask(mask), 'gQE=');
  assert.equal(countMask(mask), 3);
  setMaskBit(mask, 7, false);
  assert.equal(maskBit(mask, 7), false);
});

it('rectangle selection respects perspective, clip planes and model transform', () => {
  const camera = new THREE.PerspectiveCamera(60, 1, 0.1, 100);
  camera.updateMatrixWorld(true);
  const projection = camera.projectionMatrix.elements;
  const rect = { left: 0.4, right: 0.6, top: 0.4, bottom: 0.6 };
  assert.equal(inScreenRectangle(0, 0, -2, projection, rect), true);
  assert.equal(inScreenRectangle(0, 0, 2, projection, rect), false);
  assert.equal(inScreenRectangle(0, 0, -0.05, projection, rect), false);
  assert.equal(inScreenRectangle(0, 0, -110, projection, rect), false);
  const translated = camera.projectionMatrix
    .clone()
    .multiply(new THREE.Matrix4().makeTranslation(-2, 0, 0));
  assert.equal(inScreenRectangle(2, 0, -3, translated.elements, rect), true);
  assert.equal(inScreenRectangle(0, 0, -3, translated.elements, rect), false);
});

it('volume selection uses world coordinates after model rotation and scale', () => {
  const matrix = new THREE.Matrix4().compose(
    new THREE.Vector3(3, 4, 5),
    new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 0, 1), Math.PI / 2),
    new THREE.Vector3(2, 2, 2),
  );
  const region = {
    center: [3, 6, 5] as [number, number, number],
    radius: 0.3,
    size: [0.6, 0.6, 0.6] as [number, number, number],
  };
  assert.equal(inRegion(1, 0, 0, matrix.elements, region, true), true);
  assert.equal(inRegion(0, 0, 0, matrix.elements, region, false), false);
});

it('add and subtract selection do not mutate the current bitmap', () => {
  const current = new Uint8Array([5]);
  assert.deepEqual([...combineSelection(current, new Uint8Array([3]), 'add')], [7]);
  assert.deepEqual([...combineSelection(current, new Uint8Array([3]), 'subtract')], [4]);
  assert.deepEqual([...current], [5]);
});

it('selection skips deleted points and cancellation never commits a partial result', async () => {
  const positions = new Float32Array([0, 0, 0, 1, 0, 0, 2, 0, 0]);
  const deleted = new Uint8Array([2]);
  const result = await selectPoints(
    positions,
    deleted,
    () => true,
    () => false,
  );
  assert.deepEqual([...(result ?? [])], [5]);
  const cancelled = await selectPoints(
    positions,
    deleted,
    () => true,
    () => true,
  );
  assert.equal(cancelled, null);
});
