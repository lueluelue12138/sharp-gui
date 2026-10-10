import assert from 'node:assert/strict';
import { it } from 'node:test';
import * as THREE from 'three';

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
} from './modelEditor.js';

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
