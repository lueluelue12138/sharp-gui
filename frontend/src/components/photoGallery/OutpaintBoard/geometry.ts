export const sides = ['left', 'right', 'top', 'bottom'] as const;
export const aspectRatios = ['free', 'original', '1:1', '2:3', '3:2', '3:4', '4:3', '5:7', '9:16', '16:9', '21:9', '1:2', '2:1'];
export type Side = typeof sides[number];
export type Pads = [number, number, number, number];
export type ImageSize = { width: number; height: number };
export type OutpaintLayout = {
  pads: Pads;
  ratio: string;
  unit: 'percent' | 'pixels';
  outputEdge: number;
  multiple: number;
  color: string;
  translated?: boolean;
};

export const initialLayout: OutpaintLayout = {
  pads: [0, 0, 0, 0], ratio: 'free', unit: 'percent', outputEdge: 5120, multiple: 0, color: '#808080',
};

export const clamp = (value: number, min: number, max: number) => Math.max(min, Math.min(max, value));
export const edgeBase = (size: ImageSize, index: number) => index < 2 ? size.width : size.height;
export const canvasPixelLimit = 8192 ** 2;

function gcd(a: number, b: number): number {
  return b === 0 ? a : gcd(b, a % b);
}

export function constrainPads(pads: Pads, size: ImageSize, ratio: string, edges: number[] = [], symmetric = false): Pads {
  const result: Pads = [...pads];
  for (const start of [0, 2]) {
    const end = start + 1;
    const base = edgeBase(size, start);
    if (symmetric) {
      if (edges.includes(start)) result[end] = result[start];
      else if (edges.includes(end)) result[start] = result[end];
    }
    const firstCrop = Math.max(0, -result[start]);
    const secondCrop = Math.max(0, -result[end]);
    const budget = base - Math.ceil(base * 0.1);
    if (firstCrop + secondCrop > budget) {
      const croppedFirst = Math.round(budget * firstCrop / (firstCrop + secondCrop));
      if (firstCrop) result[start] = -croppedFirst;
      if (secondCrop) result[end] = -(budget - croppedFirst);
    }
  }
  if (ratio === 'free') return result;
  const [w, h] = ratio === 'original' ? [size.width, size.height] : ratio.split(':').map(Number);
  const common = gcd(w, h);
  const rw = w / common, rh = h / common;
  const widthFactor = (size.width + result[0] + result[1]) / rw;
  const heightFactor = (size.height + result[2] + result[3]) / rh;
  const horizontal = edges.some((side) => side < 2);
  const vertical = edges.some((side) => side >= 2);
  const desired = horizontal && !vertical ? widthFactor : vertical && !horizontal ? heightFactor : Math.max(widthFactor, heightFactor);
  const minimum = (start: number, moving: boolean) => {
    const base = edgeBase(size, start);
    if (!edges.length) return base + Math.min(0, result[start]) + Math.min(0, result[start + 1]);
    const opposite = edges.includes(start) ? result[start + 1] : result[start];
    return Math.ceil(base * 0.1) + (moving && !symmetric ? Math.max(0, opposite) : 0);
  };
  let factor = Math.max(minimum(0, horizontal) / rw, minimum(2, vertical) / rh, desired);
  if (ratio !== 'original') {
    factor = Math.ceil(factor);
    const even = (n: number) => (n * rw - size.width) % 2 === 0 && (n * rh - size.height) % 2 === 0;
    if (symmetric && !even(factor) && even(factor + 1)) factor += 1;
  }
  const totals = [Math.round(factor * rw) - size.width, Math.round(factor * rh) - size.height];
  for (const start of [0, 2]) {
    const end = start + 1, total = totals[start / 2];
    const a = result[start], b = result[end];
    const firstCrop = Math.min(0, a), secondCrop = Math.min(0, b);
    const positive = Math.max(0, a) + Math.max(0, b);
    const extra = total - firstCrop - secondCrop;
    let first;
    if (symmetric) first = Math.floor(total / 2);
    else if (edges.includes(start)) first = total - b;
    else if (edges.includes(end)) first = a;
    else if (edges.length && total < a + b) first = Math.round((total + a - b) / 2);
    else first = firstCrop + (positive ? Math.round(extra * Math.max(0, a) / positive) : Math.floor(extra / 2));
    const base = edgeBase(size, start), budget = base - Math.ceil(base * 0.1);
    result[start] = edges.length ? clamp(first, -budget, total + budget) : clamp(first, firstCrop, total - secondCrop);
    result[end] = total - result[start];
  }
  return result;
}

export function boardGeometry(size: ImageSize, { pads, outputEdge, multiple }: OutpaintLayout) {
  const [left, right, top, bottom] = pads;
  const width = Math.max(1, size.width + left + right);
  const height = Math.max(1, size.height + top + bottom);
  const cropWidth = Math.max(0, Math.min(size.width, width - left) - Math.max(0, -left));
  const cropHeight = Math.max(0, Math.min(size.height, height - top) - Math.max(0, -top));
  const positiveLeft = clamp(left, 0, width), positiveTop = clamp(top, 0, height);
  const positive = [positiveLeft, width - positiveLeft - cropWidth, positiveTop, height - positiveTop - cropHeight];
  const longEdge = Math.max(width, height);
  let scale = outputEdge > 0 ? Math.min(1, outputEdge / longEdge) : 1;
  const horizontal = positive[0] + positive[1] > 0, vertical = positive[2] + positive[3] > 0;
  if (multiple && horizontal !== vertical) {
    const base = horizontal ? height : width;
    let target = Math.max(multiple, Math.round(base * scale / multiple) * multiple);
    if (outputEdge && target / base * longEdge > outputEdge) target = Math.floor(base * scale / multiple) * multiple;
    if (target > 0) scale = target / base;
  } else if (multiple && !horizontal && !vertical) {
    scale = Math.max(scale, multiple / Math.min(width, height));
  }
  const scaled = [Math.max(1, Math.round(width * scale)), Math.max(1, Math.round(height * scale))];
  const offset = [0, 0];
  const output = [...scaled];
  if (multiple) {
    for (const axis of [0, 1]) {
      const total = scaled[axis], original = axis === 0 ? width : height;
      const a = positive[axis * 2], b = positive[axis * 2 + 1];
      if (a + b) {
        const safeA = Math.floor(a * total / original), safeB = Math.floor(b * total / original);
        const minimum = Math.ceil((total - safeA - safeB) / multiple) * multiple;
        const target = Math.max(multiple, minimum, Math.round(total / multiple) * multiple);
        const delta = target - total;
        const amount = Math.round(Math.abs(delta) * a / (a + b));
        offset[axis] = delta < 0 ? -clamp(amount, Math.abs(delta) - safeB, safeA) : amount;
        output[axis] = target;
      } else if (!horizontal && !vertical) {
        const target = Math.max(multiple, Math.floor(total / multiple) * multiple);
        offset[axis] = Math.ceil((target - total) / 2);
        output[axis] = target;
      }
    }
  }
  const scaleX = scaled[0] / width, scaleY = scaled[1] / height;
  return {
    width, height, outputWidth: output[0], outputHeight: output[1], scaleX, scaleY,
    imageX: left * scaleX + offset[0], imageY: top * scaleY + offset[1],
  };
}
