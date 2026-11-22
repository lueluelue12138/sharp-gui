import { Euler, Matrix4, Vector3 } from 'three';

import type { PortraitCamera, PortraitModel, PortraitReferenceCrop } from '@/types/portrait';

type Point = [number, number, number];

export interface CameraView {
  target: Point;
  distance: number;
  yaw: number;
  pitch: number;
  roll: number;
  zoom: number;
  pivot?: Point;
}

interface SplatRenderer {
  maxSize: number;
  draw: (view: Float32Array, lens: number[], width: number, height: number) => void;
  capture: (view: Float32Array, lens: number[], width: number, height: number) => Uint8Array<ArrayBuffer>;
  setSplats: (data: Uint32Array, rows: number) => void;
  setOrder: (order: Uint32Array, visible: number) => void;
  dispose: () => void;
}

type WorkerResponse =
  | { type: 'loaded'; data: Uint32Array; rows: number; stats: { medianDepth: number } }
  | { type: 'sorted'; order: Uint32Array; visible: number }
  | { type: 'picked'; depth: number | null }
  | { type: 'error'; error: string };

const rendererRoot = '/api/portrait/renderer';
export const portraitRatios = ['source', '1:1', '4:3', '3:4', '3:2', '2:3', '16:9', '9:16'];
export const framingScale = 0.94;

export function blendViews(first: CameraView, last: CameraView, amount: number): CameraView {
  const mix = (a: number, b: number) => a + (b - a) * amount;
  const angle = (a: number, b: number) => a + Math.atan2(Math.sin(b - a), Math.cos(b - a)) * amount;
  return {
    target: first.target.map((value, index) => mix(value, last.target[index])) as Point,
    distance: mix(first.distance, last.distance), yaw: angle(first.yaw, last.yaw),
    pitch: mix(first.pitch, last.pitch), roll: angle(first.roll, last.roll), zoom: mix(first.zoom, last.zoom),
  };
}

function pose(view: CameraView) {
  const rotation = new Matrix4().makeRotationY(view.yaw)
    .multiply(new Matrix4().makeRotationX(view.pitch)).multiply(new Matrix4().makeRotationZ(view.roll));
  const position = new Vector3(0, 0, -view.distance).applyMatrix4(rotation).add(new Vector3(...view.target));
  return { rotation, position };
}

export function projectPivot(view: CameraView, intrinsics: number[][], ratio: string) {
  if (!view.pivot) return undefined;
  const { rotation, position } = pose(view);
  const point = new Vector3(...view.pivot).sub(position).applyMatrix4(rotation.transpose());
  if (point.z < 0.02) return undefined;
  const { width, height } = cameraFrame(intrinsics, ratio);
  const x = 0.5 + (point.x * intrinsics[0][0] * view.zoom) / (point.z * width);
  const y = 0.5 + (point.y * intrinsics[1][1] * view.zoom) / (point.z * height);
  return { x, y, depth: point.z };
}

export function shiftCamera(view: CameraView, x: number, y: number, z: number): CameraView {
  const offset = new Vector3(x, y, z).applyMatrix4(pose(view).rotation);
  return { ...view, target: new Vector3(...view.target).add(offset).toArray() };
}

export function turnCamera(view: CameraView, yaw: number, pitch: number, pivot = view.pivot): CameraView {
  const next = { ...view, yaw: view.yaw + yaw, pitch: Math.max(-1.55, Math.min(1.55, view.pitch + pitch)) };
  if (!pivot) return next;
  const before = pose(view);
  const after = pose(next);
  const center = before.position.sub(new Vector3(...pivot)).applyMatrix4(before.rotation.clone().transpose())
    .applyMatrix4(after.rotation).add(new Vector3(...pivot));
  return { ...next, target: center.add(new Vector3(0, 0, next.distance).applyMatrix4(after.rotation)).toArray() };
}

export function lookCamera(view: CameraView, yaw: number, pitch: number): CameraView {
  return { ...turnCamera(view, yaw, pitch, pose(view).position.toArray()), pivot: view.pivot };
}

export function moveCamera(view: CameraView, factor: number, baseDepth: number): CameraView {
  const minimum = baseDepth * 0.02;
  if (factor < 1 && view.distance <= minimum * 1.001) return shiftCamera(view, 0, 0, -Math.log(factor) * baseDepth);
  return { ...view, distance: Math.max(minimum, Math.min(baseDepth * 20, view.distance * factor)) };
}

export function frameDimensions(camera: PortraitCamera, edge: number): [number, number] {
  const scale = edge / Math.max(camera.width, camera.height);
  const align = (value: number) => Math.max(64, Math.round(value * scale / 32) * 32);
  return [align(camera.width), align(camera.height)];
}

export function cameraFrame(source: number[][], ratio: string) {
  let width = Math.round(2 * source[0][2]);
  let height = Math.round(2 * source[1][2]);
  if (ratio !== 'source') {
    const [rw, rh] = ratio.split(':').map(Number);
    if (width / height > rw / rh) width = Math.max(1, Math.round(height * rw / rh));
    else height = Math.max(1, Math.round(width * rh / rw));
  }
  return { width, height };
}

export function restoreCaptureView(camera: PortraitCamera, model: PortraitModel): { view: CameraView; ratio: string } {
  const [a, b, c, d] = camera.w2c;
  const transform = new Matrix4().set(a[0], a[1], a[2], a[3], b[0], b[1], b[2], b[3],
    c[0], c[1], c[2], c[3], d[0], d[1], d[2], d[3]).invert();
  const rotation = new Euler().setFromRotationMatrix(transform, 'YXZ');
  // The original pivot and orbit distance were not exported. Any point along the same axis preserves the captured camera.
  const distance = 1;
  const target = new Vector3(0, 0, distance).applyMatrix4(transform).toArray();
  const ratio = portraitRatios.find((candidate) => {
    const frame = cameraFrame(model.intrinsics, candidate);
    return frame.width === camera.width && frame.height === camera.height;
  }) ?? 'source';
  return { view: { target, distance, yaw: rotation.y, pitch: rotation.x, roll: rotation.z,
    zoom: camera.K[0][0] / model.intrinsics[0][0] }, ratio };
}

function viewportLens(camera: PortraitCamera, width: number, height: number) {
  const scale = framingScale * Math.min(width / camera.width, height / camera.height);
  return [camera.K[0][0] * scale, camera.K[1][1] * scale, width / 2, height / 2];
}

export class PortraitRenderer {
  private worker: Worker;
  private pending = new Map<number, { resolve: (value: WorkerResponse) => void; reject: (reason: Error) => void }>();
  private nextId = 0;
  private disposed = false;
  private drawing = false;
  private latest: { view: CameraView; ratio: string } | null = null;
  depth = 1;

  private constructor(private canvas: HTMLCanvasElement, private renderer: SplatRenderer, private model: PortraitModel) {
    this.worker = new Worker(`${rendererRoot}/splat_worker.js`);
    this.worker.onmessage = ({ data }: MessageEvent<WorkerResponse & { id: number }>) => {
      const entry = this.pending.get(data.id);
      this.pending.delete(data.id);
      if (data.type === 'error') entry?.reject(new Error(data.error));
      else entry?.resolve(data);
    };
    this.worker.onerror = () => this.dispose();
  }

  static async load(canvas: HTMLCanvasElement, model: PortraitModel, signal: AbortSignal) {
    const url = `${rendererRoot}/splat_renderer.js`;
    const { SplatRenderer: Renderer } = await import(/* @vite-ignore */ url) as {
      SplatRenderer: new (element: HTMLCanvasElement) => SplatRenderer;
    };
    signal.throwIfAborted();
    const renderer = new PortraitRenderer(canvas, new Renderer(canvas), model);
    const abort = () => renderer.dispose();
    signal.addEventListener('abort', abort, { once: true });
    try {
      const data = await renderer.send({ type: 'load', url: new URL(model.url, location.href).href });
      if (data.type !== 'loaded') throw new Error('Gaussian model could not be opened.');
      renderer.renderer.setSplats(data.data, data.rows);
      renderer.depth = Math.max(0.05, data.stats.medianDepth);
      return renderer;
    } catch (error) {
      renderer.dispose();
      throw error;
    } finally {
      signal.removeEventListener('abort', abort);
    }
  }

  private send(data: object) {
    if (this.disposed) return Promise.reject(new Error('Gaussian preview is closed.'));
    const id = ++this.nextId;
    return new Promise<WorkerResponse>((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.worker.postMessage({ ...data, id });
    });
  }

  reset(): CameraView {
    return { target: [0, 0, this.depth], distance: this.depth, yaw: 0, pitch: 0, roll: 0, zoom: 1 };
  }

  camera(view: CameraView, ratio: string): PortraitCamera {
    const source = this.model.intrinsics;
    const { width, height } = cameraFrame(source, ratio);
    const { rotation, position } = pose(view);
    const transform = rotation.setPosition(position).invert().elements;
    const w2c = [0, 1, 2, 3].map(row => [0, 1, 2, 3].map(col => transform[col * 4 + row]));
    return { w2c, width, height, K: [[source[0][0] * view.zoom, 0, width / 2], [0, source[1][1] * view.zoom, height / 2], [0, 0, 1]] };
  }

  translationPerPixel(view: CameraView, ratio: string) {
    const { width, height } = this.canvas.getBoundingClientRect();
    const [focal] = viewportLens(this.camera(view, ratio), width, height);
    return view.distance / (focal || 1);
  }

  async pick(view: CameraView, ratio: string, x: number, y: number): Promise<Point | null> {
    const camera = this.camera(view, ratio);
    const bounds = this.canvas.getBoundingClientRect();
    if (!bounds.width || !bounds.height) return null;
    const [fx, fy, cx, cy] = viewportLens(camera, bounds.width, bounds.height);
    const rx = (x - bounds.left - cx) / fx;
    const ry = (y - bounds.top - cy) / fy;
    const response = await this.send({ type: 'pick', camera: camera.w2c, ray: [rx, ry], radius: [10 / fx, 10 / fy] });
    if (response.type !== 'picked' || response.depth === null || response.depth <= 0.02) return null;
    const { rotation, position } = pose(view);
    return new Vector3(rx, ry, 1).multiplyScalar(response.depth).applyMatrix4(rotation).add(position).toArray();
  }

  private async sort(camera: PortraitCamera) {
    const response = await this.send({ type: 'sort', row: camera.w2c[2] });
    if (response.type !== 'sorted' || this.disposed) throw new Error('Gaussian preview is closed.');
    this.renderer.setOrder(response.order, response.visible);
    return Float32Array.from(camera.w2c[0].flatMap((_, col) => camera.w2c.map(row => row[col])));
  }

  draw(view: CameraView, ratio: string) {
    this.latest = { view, ratio };
    if (this.drawing || this.disposed) return;
    this.drawing = true;
    void this.drawLatest().finally(() => { this.drawing = false; });
  }

  private async drawLatest() {
    try {
      while (this.latest && !this.disposed) {
        const { view, ratio } = this.latest;
        this.latest = null;
        const camera = this.camera(view, ratio);
        const bounds = this.canvas.getBoundingClientRect();
        if (bounds.width < 2 || bounds.height < 2) continue;
        const density = Math.min(window.devicePixelRatio || 1, 1.5, 2048 / Math.max(bounds.width, bounds.height));
        const width = Math.round(bounds.width * density);
        const height = Math.round(bounds.height * density);
        const matrix = await this.sort(camera);
        if (this.canvas.width !== width) this.canvas.width = width;
        if (this.canvas.height !== height) this.canvas.height = height;
        this.renderer.draw(matrix, viewportLens(camera, width, height), width, height);
      }
    } catch (error) {
      if (!this.disposed) console.warn('Portrait preview failed', error);
    }
  }

  private lens(camera: PortraitCamera, width: number, height: number) {
    return [camera.K[0][0] * width / camera.width, camera.K[1][1] * height / camera.height, width / 2, height / 2];
  }

  async closeupReference(view: CameraView, camera: PortraitCamera): Promise<PortraitReferenceCrop | undefined> {
    // When a camera orbits far around the subject, the full original remains enough context.
    if (camera.w2c[2][2] < Math.cos(0.62)) return;
    const fx = camera.K[0][0], fy = camera.K[1][1];
    const hit = await this.send({ type: 'pick', camera: camera.w2c, ray: [0, 0], radius: [24 / fx, 24 / fy] });
    if (hit.type !== 'picked' || hit.depth === null) return;
    const depth = hit.depth;
    const { rotation, position } = pose(view);
    const original = this.model.intrinsics;
    const width = Math.round(2 * original[0][2]), height = Math.round(2 * original[1][2]);
    function project(x: number, y: number) {
      const point = new Vector3(x * camera.width / fx, y * camera.height / fy, 1)
        .multiplyScalar(depth).applyMatrix4(rotation).add(position);
      if (point.z <= 0.02) return new Vector3(NaN, NaN, NaN);
      return new Vector3(original[0][0] * point.x / point.z, original[1][1] * point.y / point.z, 0);
    }
    // Estimate the crop around the surface at center using the local projection scale.
    const cx = 0.5 + project(0, 0).x / width, cy = 0.5 + project(0, 0).y / height;
    if (!(cx > 0 && cx < 1 && cy > 0 && cy < 1)) return;
    const fractionX = 10 * project(-0.05, 0).distanceTo(project(0.05, 0)) / width;
    const fractionY = 10 * project(0, -0.05).distanceTo(project(0, 0.05)) / height;
    if (!(fractionX < 0.82 && fractionY < 0.82)) return;
    const spanX = Math.max(0.25, fractionX), spanY = Math.max(0.25, fractionY);
    const left = Math.max(0, Math.min(1 - spanX, cx - spanX / 2));
    const top = Math.max(0, Math.min(1 - spanY, cy - spanY / 2));
    return { width, height, bounds: [left, top, Math.min(1, left + spanX), Math.min(1, top + spanY)] };
  }

  async capture(view: CameraView, ratio: string, edge: number) {
    const camera = this.camera(view, ratio);
    const [width, height] = frameDimensions(camera, edge);
    if (Math.max(width, height) > this.renderer.maxSize) throw new Error('The selected size exceeds the browser rendering limit.');
    const matrix = await this.sort(camera);
    const pixels = this.renderer.capture(matrix, this.lens(camera, width, height), width, height);
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext('2d');
    if (!context) throw new Error('Could not save the camera capture.');
    context.putImageData(new ImageData(new Uint8ClampedArray(pixels.buffer), width, height), 0, 0);
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/png'));
    canvas.width = canvas.height = 1;
    if (!blob) throw new Error('Could not save the camera capture.');
    return { camera, blob };
  }

  dispose() {
    if (this.disposed) return;
    this.disposed = true;
    this.worker.terminate();
    this.pending.forEach(({ reject }) => reject(new Error('Gaussian preview is closed.')));
    this.pending.clear();
    this.renderer.dispose();
  }
}
