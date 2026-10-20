import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { SparkRenderer, SplatMesh } from '@sparkjsdev/spark';

import { getSplatFileTypeFromFormat } from '@/constants/spark';
import { DEFAULT_VIEWER_TRANSFORM } from '@/constants/viewerCoordinates';
import { DEFAULT_CAMERA_CONFIG } from '@/utils/camera';
import { getShareBoundsView } from '@/utils/shareFraming';
import { composeViewerModelQuaternion, getReconstructionCameraView } from '@/utils/viewerRuntime';
import { resolveViewerOrientation } from '@/utils/viewerOrientation';
import type { ShareManifest, ShareStage } from '@/share/types';

export interface ShareScene {
  ready: Promise<number>;
  reset: () => void;
  fit: () => void;
  setAutoRotate: (enabled: boolean) => void;
  move: (x: number, y: number) => void;
  dispose: () => void;
}

type View = { position: THREE.Vector3; target: THREE.Vector3; up: THREE.Vector3; fov: number };

async function decodeModel(encoded: string, cancelled: () => boolean, progress: (value: number) => void) {
  if (!encoded || encoded.length % 4 !== 0) throw new Error('Invalid embedded model data');
  const padding = encoded.endsWith('==') ? 2 : encoded.endsWith('=') ? 1 : 0;
  const bytes = new Uint8Array(encoded.length / 4 * 3 - padding);
  const chunkSize = 4 * 131072;
  for (let offset = 0; offset < encoded.length; offset += chunkSize) {
    if (cancelled()) throw new DOMException('Cancelled', 'AbortError');
    const decoded = atob(encoded.slice(offset, offset + chunkSize));
    const targetOffset = offset / 4 * 3;
    for (let index = 0; index < decoded.length; index++) bytes[targetOffset + index] = decoded.charCodeAt(index);
    progress(Math.min(1, (offset + chunkSize) / encoded.length));
    await new Promise<void>((resolve) => setTimeout(resolve, 0));
  }
  return bytes;
}

export function createShareScene(
  container: HTMLElement, manifest: ShareManifest, encoded: string,
  progress: (stage: ShareStage, value: number) => void,
  onContextLost: () => void,
  onAutoRotateStop: () => void,
): ShareScene {
  let disposed = false;
  let initialized = false;
  let framing: 'initial' | 'fit' | 'manual' = 'initial';
  let mesh: SplatMesh | null = null;
  let bounds: THREE.Box3 | null = null;
  let initialView: () => View;
  let transition: { from: View; to: View; start: number } | null = null;
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(DEFAULT_CAMERA_CONFIG.fov, container.clientWidth / Math.max(1, container.clientHeight), 0.01, 1000);
  const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: false });
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
  renderer.setClearColor(0x000000, 0);
  renderer.setSize(container.clientWidth, container.clientHeight);
  renderer.domElement.setAttribute('aria-label', '3D model');
  renderer.domElement.tabIndex = 0;
  container.appendChild(renderer.domElement);
  const transform = manifest.viewerTransform ?? DEFAULT_VIEWER_TRANSFORM;
  const orientation = resolveViewerOrientation(manifest).mode;
  const previewMatrix = new THREE.Matrix4().compose(
    new THREE.Vector3(transform.positionX, transform.positionY, transform.positionZ),
    composeViewerModelQuaternion(transform, orientation),
    new THREE.Vector3().setScalar(Math.min(20, Math.max(0.05, transform.scale))),
  );
  const startingCamera = getReconstructionCameraView(manifest.viewerCamera, previewMatrix, camera.aspect);
  if (startingCamera) camera.up.copy(startingCamera.up);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.05;
  controls.autoRotateSpeed = 1.5; // Approximately 40 seconds per orbit; deltaTime keeps it refresh-rate independent.
  controls.mouseButtons = { LEFT: THREE.MOUSE.ROTATE, MIDDLE: THREE.MOUSE.DOLLY, RIGHT: THREE.MOUSE.PAN };
  controls.touches = { ONE: THREE.TOUCH.ROTATE, TWO: THREE.TOUCH.DOLLY_PAN };
  let spark: SparkRenderer;
  try { spark = new SparkRenderer({ renderer, lodSplatScale: 1 }); }
  catch (error) { controls.dispose(); renderer.dispose(); renderer.domElement.remove(); throw error; }
  scene.add(spark);
  const keys = new Set<string>();
  const stick = new THREE.Vector2();
  const listeners = new AbortController();
  const options = { signal: listeners.signal };
  const captureView = (): View => ({ position: camera.position.clone(), target: controls.target.clone(), up: camera.up.clone(), fov: camera.fov });
  const configureDistance = () => {
    const distance = Math.max(camera.position.distanceTo(controls.target), 0.001);
    const extent = bounds?.getSize(new THREE.Vector3()).length() ?? distance;
    controls.minDistance = Math.max(1e-5, Math.min(distance * 0.01, extent * 0.001));
    controls.maxDistance = Math.max(distance * 100, extent * 100, 10);
    camera.near = Math.max(1e-6, Math.min(distance * 0.001, extent * 0.001));
    camera.far = Math.max(distance + extent * 4, controls.maxDistance * 2, 1000);
    camera.updateProjectionMatrix();
  };
  const applyView = (view: View) => {
    camera.position.copy(view.position);
    camera.up.copy(view.up).normalize();
    camera.fov = view.fov;
    controls.target.copy(view.target);
    configureDistance();
    controls.update();
  };
  const goTo = (view: View, mode: typeof framing = 'manual') => {
    if (!initialized || disposed) return;
    framing = mode;
    controls.autoRotate = false; onAutoRotateStop();
    if (matchMedia('(prefers-reduced-motion: reduce)').matches) applyView(view);
    else transition = { from: captureView(), to: view, start: performance.now() };
  };
  const fit = () => {
    if (!bounds) return;
    const view = getShareBoundsView(bounds, camera.aspect, DEFAULT_CAMERA_CONFIG.fov,
      camera.position.clone().sub(controls.target), camera.up);
    if (view) goTo(view, 'fit');
  };
  controls.addEventListener('start', () => { transition = null; framing = 'manual'; });
  const clearMotion = () => { keys.clear(); stick.set(0, 0); };
  window.addEventListener('blur', clearMotion, options);
  document.addEventListener('visibilitychange', () => { if (document.hidden) clearMotion(); }, options);
  document.addEventListener('keydown', (event) => {
    if ((event.target as HTMLElement)?.closest('button,input,textarea,select,[contenteditable="true"]') || event.ctrlKey || event.metaKey) return;
    const key = event.key.toLowerCase();
    if ('wasdqe'.includes(key) && key.length === 1 || key === 'shift' || key === 'alt') {
      event.preventDefault(); keys.add(key); transition = null; framing = 'manual';
    }
    if (key === 'r' && initialized) goTo(initialView(), 'initial');
  }, options);
  document.addEventListener('keyup', (event) => keys.delete(event.key.toLowerCase()), options);
  renderer.domElement.addEventListener('wheel', (event) => {
    controls.zoomSpeed = event.shiftKey ? 3 : event.altKey ? 0.3 : 1;
  }, { ...options, passive: true });
  renderer.domElement.addEventListener('webglcontextlost', (event) => {
    event.preventDefault(); clearMotion(); renderer.setAnimationLoop(null); onContextLost();
  }, options);
  const pointers = new Set<number>();
  let pointerStart = { id: -1, x: 0, y: 0, multi: false };
  renderer.domElement.addEventListener('pointerdown', (event) => {
    pointers.add(event.pointerId);
    if (pointers.size === 1) pointerStart = { id: event.pointerId, x: event.clientX, y: event.clientY, multi: false };
    else pointerStart.multi = true;
  }, options);
  renderer.domElement.addEventListener('pointercancel', (event) => { pointers.delete(event.pointerId); pointerStart.multi = true; }, options);
  renderer.domElement.addEventListener('pointerup', (event) => {
    pointers.delete(event.pointerId);
    if (!initialized || !mesh || event.button !== 0 || pointerStart.multi || pointerStart.id !== event.pointerId
      || Math.hypot(event.clientX - pointerStart.x, event.clientY - pointerStart.y) > 4) return;
    const rect = renderer.domElement.getBoundingClientRect();
    const ray = new THREE.Raycaster();
    ray.setFromCamera(new THREE.Vector2((event.clientX - rect.left) / rect.width * 2 - 1, 1 - (event.clientY - rect.top) / rect.height * 2), camera);
    const hit = ray.intersectObject(mesh)[0];
    if (hit) {
      const view = captureView(); view.target.copy(hit.point); goTo(view);
      const ring = document.createElement('span'); ring.className = 'share-focus-ring';
      ring.style.left = `${event.clientX - rect.left}px`; ring.style.top = `${event.clientY - rect.top}px`;
      container.appendChild(ring); ring.addEventListener('animationend', () => ring.remove(), { once: true });
    }
  }, options);

  const resize = new ResizeObserver(() => {
    const width = container.clientWidth, height = Math.max(1, container.clientHeight);
    camera.aspect = width / height;
    if (initialized && framing === 'initial') applyView(initialView());
    else if (initialized && framing === 'fit' && bounds) {
      const view = getShareBoundsView(bounds, camera.aspect, DEFAULT_CAMERA_CONFIG.fov,
        camera.position.clone().sub(controls.target), camera.up);
      if (view) applyView(view);
    }
    camera.updateProjectionMatrix(); renderer.setSize(width, height);
  });
  resize.observe(container);

  let lastTime = performance.now();
  const ready = (async () => {
    progress('decoding', 5);
    let bytes: Uint8Array | undefined = await decodeModel(encoded, () => disposed, (ratio) => progress('decoding', 5 + ratio * 35));
    if (disposed) throw new DOMException('Cancelled', 'AbortError');
    progress('rendering', 45);
    mesh = new SplatMesh({ fileBytes: bytes, fileType: getSplatFileTypeFromFormat(manifest.format), lod: false });
    try { await mesh.initialized; }
    catch (error) { mesh.dispose(); mesh = null; throw error; }
    bytes = undefined;
    if (disposed) { mesh.dispose(); throw new DOMException('Cancelled', 'AbortError'); }
    mesh.position.set(transform.positionX, transform.positionY, transform.positionZ);
    mesh.quaternion.copy(composeViewerModelQuaternion(transform, orientation));
    mesh.scale.setScalar(Math.min(20, Math.max(0.05, transform.scale)));
    scene.add(mesh); mesh.updateMatrixWorld(true);
    try {
      const localBounds = mesh.getBoundingBox(true).clone().applyMatrix4(mesh.matrixWorld);
      if (!localBounds.isEmpty() && localBounds.min.toArray().concat(localBounds.max.toArray()).every(Number.isFinite)) bounds = localBounds;
    } catch { /* Streamed formats may not expose a finite full-model bound. */ }
    initialView = () => {
      const saved = getReconstructionCameraView(manifest.viewerCamera, mesh!.matrixWorld, camera.aspect);
      if (saved) return saved;
      const base = { position: new THREE.Vector3(0, 0, 1), target: new THREE.Vector3(0, 0, -9), up: new THREE.Vector3(0, 1, 0), fov: DEFAULT_CAMERA_CONFIG.fov };
      if (!bounds) return base;
      const center = bounds.getCenter(new THREE.Vector3());
      const size = bounds.getSize(new THREE.Vector3());
      if (orientation === 'y-front' || Math.hypot(center.x, center.y) > Math.max(0.2, Math.max(size.x, size.y, size.z) * 0.25)) {
        return getShareBoundsView(bounds, camera.aspect, base.fov) ?? base;
      }
      const distance = Math.max(0.1, base.position.z - bounds.max.z);
      base.target.set(0, 0, 1 - distance - 0.08 * distance ** 2);
      return base;
    };
    applyView(initialView()); initialized = true;
    progress('ready', 100);
    renderer.setAnimationLoop(() => {
      if (disposed || document.hidden) return;
      const now = performance.now(), delta = Math.min((now - lastTime) / 1000, 0.05); lastTime = now;
      const forward = new THREE.Vector3(); camera.getWorldDirection(forward);
      const right = new THREE.Vector3().crossVectors(forward, camera.up).normalize();
      const speed = Math.max(0.001, camera.position.distanceTo(controls.target)) * delta * (keys.has('shift') ? 1.5 : keys.has('alt') ? 0.08 : 0.4);
      const movement = forward.multiplyScalar(Number(keys.has('w')) - Number(keys.has('s')) - stick.y)
        .addScaledVector(right, Number(keys.has('d')) - Number(keys.has('a')) + stick.x)
        .addScaledVector(camera.up, Number(keys.has('e')) - Number(keys.has('q'))).multiplyScalar(speed);
      if (movement.lengthSq()) { framing = 'manual'; transition = null; camera.position.add(movement); controls.target.add(movement); }
      if (transition) {
        const ratio = Math.min((now - transition.start) / 450, 1), eased = 1 - (1 - ratio) ** 3;
        camera.position.lerpVectors(transition.from.position, transition.to.position, eased);
        controls.target.lerpVectors(transition.from.target, transition.to.target, eased);
        camera.up.lerpVectors(transition.from.up, transition.to.up, eased).normalize();
        camera.fov = THREE.MathUtils.lerp(transition.from.fov, transition.to.fov, eased);
        configureDistance(); if (ratio === 1) transition = null;
      }
      controls.update(delta); renderer.render(scene, camera);
    });
    return mesh.numSplats;
  })();

  return {
    ready, reset: () => { if (initialized) goTo(initialView(), 'initial'); }, fit,
    setAutoRotate: (enabled) => { if (enabled) framing = 'manual'; controls.autoRotate = enabled; transition = null; },
    move: (x, y) => { stick.set(x, y).clampLength(0, 1); },
    dispose: () => {
      if (disposed) return;
      disposed = true; clearMotion(); listeners.abort(); resize.disconnect();
      renderer.setAnimationLoop(null); controls.dispose();
      if (initialized) mesh?.dispose();
      spark.dispose(); renderer.dispose(); renderer.forceContextLoss(); renderer.domElement.remove();
      container.querySelectorAll('.share-focus-ring').forEach((ring) => ring.remove());
    },
  };
}
