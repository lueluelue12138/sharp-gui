import type { EditorRegion } from '@/types/modelEditor';

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
  predicate: (x: number, y: number, z: number) => boolean,
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
        predicate(positions[i * 3], positions[i * 3 + 1], positions[i * 3 + 2])
      )
        setMaskBit(selected, i);
    }
    await new Promise<void>((resolve) => setTimeout(resolve, 0));
  }
  return cancelled() ? null : selected;
}
