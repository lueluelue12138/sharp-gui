import type { EditorRegion, EditorSelectionMode } from '@/types/modelEditor';

/** Store the six symmetric covariance entries, including the renderer's visible support. */
export function writeSplatCovariance(
  target: Float32Array, index: number,
  scales: { x: number; y: number; z: number },
  q: { x: number; y: number; z: number; w: number }, support: number,
) {
  const { x, y, z, w } = q;
  const rows = [
    [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
    [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
    [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
  ];
  const variance = [scales.x ** 2, scales.y ** 2, scales.z ** 2];
  let offset = index * 6;
  for (const [a, b] of [[0, 0], [0, 1], [0, 2], [1, 1], [1, 2], [2, 2]]) {
    target[offset++] = rows[a].reduce((sum, entry, axis) => sum + entry * rows[b][axis] * variance[axis], 0) * support ** 2;
  }
}

function covarianceProduct(c: Float32Array, offset: number, a: readonly number[], b = a) {
  return a[0] * (c[offset] * b[0] + c[offset + 1] * b[1] + c[offset + 2] * b[2])
    + a[1] * (c[offset + 1] * b[0] + c[offset + 3] * b[1] + c[offset + 4] * b[2])
    + a[2] * (c[offset + 2] * b[0] + c[offset + 4] * b[1] + c[offset + 5] * b[2]);
}

/** Test the projected anisotropic ellipse, including edges whose center is outside the drag. */
export function splatInScreenRectangle(
  x: number, y: number, z: number, covariance: Float32Array, index: number,
  matrix: readonly number[], rect: ScreenRectangle, mode: EditorSelectionMode,
  pixelPadding: readonly number[] = [0, 0],
): boolean {
  if (mode === 'center') return inScreenRectangle(x, y, z, matrix, rect);
  const w = matrix[3] * x + matrix[7] * y + matrix[11] * z + matrix[15];
  if (w <= 0) return false;
  const depth = (matrix[2] * x + matrix[6] * y + matrix[10] * z + matrix[14]) / w;
  if (depth < -1 || depth > 1) return false;
  const nx = (matrix[0] * x + matrix[4] * y + matrix[8] * z + matrix[12]) / w;
  const ny = (matrix[1] * x + matrix[5] * y + matrix[9] * z + matrix[13]) / w;
  const sx = (nx + 1) / 2, sy = (1 - ny) / 2;
  const gx = [matrix[0] - nx * matrix[3], matrix[4] - nx * matrix[7], matrix[8] - nx * matrix[11]].map((v) => v / (2 * w));
  const gy = [matrix[1] - ny * matrix[3], matrix[5] - ny * matrix[7], matrix[9] - ny * matrix[11]].map((v) => -v / (2 * w));
  const a = Math.max(0, covarianceProduct(covariance, index * 6, gx)) + pixelPadding[0] ** 2;
  const b = covarianceProduct(covariance, index * 6, gx, gy);
  const d = Math.max(0, covarianceProduct(covariance, index * 6, gy)) + pixelPadding[1] ** 2;
  const rx = Math.sqrt(a), ry = Math.sqrt(d);
  if (mode === 'contain') return sx - rx >= rect.left && sx + rx <= rect.right && sy - ry >= rect.top && sy + ry <= rect.bottom;
  if (sx + rx < rect.left || sx - rx > rect.right || sy + ry < rect.top || sy - ry > rect.bottom) return false;
  if (sx >= rect.left && sx <= rect.right && sy >= rect.top && sy <= rect.bottom) return true;
  const determinant = a * d - b * b;
  if (determinant <= 1e-30) return false;
  const clamp = (v: number, low: number, high: number) => Math.min(high, Math.max(low, v));
  const quadratic = (dx: number, dy: number) => (d * dx * dx - 2 * b * dx * dy + a * dy * dy) / determinant;
  // Minimum Mahalanobis distance lies on an edge when the ellipse center is outside.
  for (const edge of [rect.left, rect.right]) {
    const dx = edge - sx;
    if (quadratic(dx, clamp(b * dx / Math.max(a, 1e-30), rect.top - sy, rect.bottom - sy)) <= 1) return true;
  }
  for (const edge of [rect.top, rect.bottom]) {
    const dy = edge - sy;
    if (quadratic(clamp(b * dy / Math.max(d, 1e-30), rect.left - sx, rect.right - sx), dy) <= 1) return true;
  }
  return false;
}

/** Volume tools use conservative world bounds; containment excludes every crossing boundary. */
export function splatInRegion(
  x: number, y: number, z: number, covariance: Float32Array, index: number,
  matrix: readonly number[], region: EditorRegion, sphere: boolean, mode: EditorSelectionMode,
): boolean {
  if (mode === 'center') return inRegion(x, y, z, matrix, region, sphere);
  const delta = [
    matrix[0] * x + matrix[4] * y + matrix[8] * z + matrix[12] - region.center[0],
    matrix[1] * x + matrix[5] * y + matrix[9] * z + matrix[13] - region.center[1],
    matrix[2] * x + matrix[6] * y + matrix[10] * z + matrix[14] - region.center[2],
  ];
  const extents = [0, 1, 2].map((axis) => Math.sqrt(Math.max(0,
    covarianceProduct(covariance, index * 6, [matrix[axis], matrix[axis + 4], matrix[axis + 8]]))));
  if (!sphere) return delta.every((v, axis) => mode === 'contain'
    ? Math.abs(v) + extents[axis] <= region.size[axis] / 2
    : Math.abs(v) <= region.size[axis] / 2 + extents[axis]);
  return mode === 'contain'
    ? Math.hypot(...delta.map((v, axis) => Math.abs(v) + extents[axis])) <= region.radius
    : Math.hypot(...delta.map((v, axis) => Math.max(0, Math.abs(v) - extents[axis]))) <= region.radius;
}

export function maskBit(mask: Uint8Array, index: number): boolean {
  return (mask[index >> 3] & (1 << (index & 7))) !== 0;
}

export function setMaskBit(mask: Uint8Array, index: number, value = true): void {
  const bit = 1 << (index & 7);
  if (value) mask[index >> 3] |= bit;
  else mask[index >> 3] &= ~bit;
}

export function countMask(mask: Uint8Array): number {
  let count = 0;
  for (let byte of mask) {
    while (byte) {
      byte &= byte - 1;
      count++;
    }
  }
  return count;
}

export function encodeMask(mask: Uint8Array): string {
  let raw = '';
  for (let start = 0; start < mask.length; start += 8192) {
    raw += String.fromCharCode(...mask.subarray(start, start + 8192));
  }
  return btoa(raw);
}

export function combineSelection(
  current: Uint8Array,
  incoming: Uint8Array,
  mode: 'replace' | 'add' | 'subtract',
) {
  if (mode === 'replace') return incoming;
  const result = current.slice();
  for (let i = 0; i < result.length; i++) {
    if (mode === 'add') result[i] |= incoming[i];
    else result[i] &= ~incoming[i];
  }
  return result;
}

export interface ScreenRectangle {
  left: number;
  right: number;
  top: number;
  bottom: number;
}

/** Keep drag previews to one immutable update per frame, and cancel them on release. */
export function createRectanglePreview(
  publish: (rectangle: ScreenRectangle | null) => void,
  requestFrame = requestAnimationFrame,
  cancelFrame = cancelAnimationFrame,
) {
  let frame: number | null = null;
  let pending: ScreenRectangle | null = null;
  return {
    update(rectangle: ScreenRectangle) {
      pending = { ...rectangle };
      if (frame !== null) return;
      frame = requestFrame(() => {
        frame = null;
        const next = pending;
        pending = null;
        if (next) publish(next);
      });
    },
    clear() {
      if (frame !== null) cancelFrame(frame);
      frame = null;
      pending = null;
      publish(null);
    },
  };
}

/** Projection includes the model transform. Behind-camera and clipped points are excluded. */
export function inScreenRectangle(
  x: number,
  y: number,
  z: number,
  matrix: readonly number[],
  rect: ScreenRectangle,
): boolean {
  const w = matrix[3] * x + matrix[7] * y + matrix[11] * z + matrix[15];
  if (w <= 0) return false;
  const depth = (matrix[2] * x + matrix[6] * y + matrix[10] * z + matrix[14]) / w;
  if (depth < -1 || depth > 1) return false;
  const sx = ((matrix[0] * x + matrix[4] * y + matrix[8] * z + matrix[12]) / w + 1) / 2;
  const sy = (1 - (matrix[1] * x + matrix[5] * y + matrix[9] * z + matrix[13]) / w) / 2;
  return sx >= rect.left && sx <= rect.right && sy >= rect.top && sy <= rect.bottom;
}

export function inRegion(
  x: number,
  y: number,
  z: number,
  matrix: readonly number[],
  region: EditorRegion,
  sphere: boolean,
): boolean {
  const dx = matrix[0] * x + matrix[4] * y + matrix[8] * z + matrix[12] - region.center[0];
  const dy = matrix[1] * x + matrix[5] * y + matrix[9] * z + matrix[13] - region.center[1];
  const dz = matrix[2] * x + matrix[6] * y + matrix[10] * z + matrix[14] - region.center[2];
  return sphere
    ? dx * dx + dy * dy + dz * dz <= region.radius ** 2
    : Math.abs(dx) <= region.size[0] / 2 &&
        Math.abs(dy) <= region.size[1] / 2 &&
        Math.abs(dz) <= region.size[2] / 2;
}

/** Yield between chunks so a large model can be cancelled and the interface stays responsive. */
export async function selectPoints(
  positions: Float32Array,
  deleted: Uint8Array,
  predicate: (x: number, y: number, z: number, index: number) => boolean,
  cancelled: () => boolean,
) {
  const count = positions.length / 3;
  const selected = new Uint8Array(Math.ceil(count / 8));
  for (let start = 0; start < count; start += 32768) {
    if (cancelled()) return null;
    const end = Math.min(count, start + 32768);
    for (let i = start; i < end; i++) {
      if (
        !maskBit(deleted, i) &&
        predicate(positions[i * 3], positions[i * 3 + 1], positions[i * 3 + 2], i)
      )
        setMaskBit(selected, i);
    }
    await new Promise<void>((resolve) => setTimeout(resolve, 0));
  }
  return cancelled() ? null : selected;
}
