import { useEffect, useRef, useCallback, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { SparkRenderer, SplatMesh, SplatFileType } from '@sparkjsdev/spark';
import { useAppStore } from '@/store/useAppStore';
import {
  applyLodPresetToMesh,
  applyLodPresetToRenderer,
  deriveRadUrl,
  getLodPresetConfig,
  getSplatFileTypeFromFormat,
  hasLodComparisonData,
} from '@/constants/spark';
import { DEFAULT_CAMERA_CONFIG } from '@/utils/camera';
import {
  applyRevealEffectToMesh,
  createRevealEffectRuntime,
  isRevealEffectEnabled,
  syncRevealEffectSelection,
  type RevealEffectId,
  updateRevealEffectPlayback,
} from '@/utils/viewerRevealEffects';
import { useKeyboard } from './useKeyboard';
import { useGyroscope } from './useGyroscope';
import { useJoystick } from './useJoystick';
import { useXR } from './useXR';

// Inject focus-ring CSS animation once
let focusRingStyleInjected = false;
const missingRadCache = new Set<string>();
const CAMERA_RESET_CENTER_LATERAL_RATIO = 0.25;
const CAMERA_RESET_CENTER_MIN_OFFSET = 0.2;
const CAMERA_RESET_FIT_PADDING = 1.15;
const CAMERA_RESET_Y_FRONT_DEPTH_RATIO = 0.65;
const DEBUG_UPDATE_INTERVAL_MS = 250;

type ViewerResetMode =
  | 'default'
  | 'bounds-centered'
  | 'bounds-y-front'
  | 'bounds-default'
  | 'bounds-unavailable';

type VectorTuple = [number, number, number];

type ControlsLimitConfig = typeof DEFAULT_CAMERA_CONFIG.limits;
type ViewerOrientationMode = 'default' | 'y-front';

const Y_FRONT_ORIENTATION_QUATERNION = new THREE.Quaternion()
  .setFromAxisAngle(new THREE.Vector3(1, 0, 0), Math.PI / 2);

export interface ViewerDebugInfo {
  resetMode: ViewerResetMode;
  camera: {
    position: VectorTuple;
    rotationDeg: VectorTuple;
    up: VectorTuple;
    forward: VectorTuple;
  };
  controls: {
    target: VectorTuple;
    distance: number;
    orbitAzimuthDeg: number;
    orbitPolarDeg: number;
  };
  model: {
    position: VectorTuple | null;
    rotationDeg: VectorTuple | null;
    scale: VectorTuple | null;
    right: VectorTuple | null;
    up: VectorTuple | null;
    forward: VectorTuple | null;
  };
  bounds: {
    center: VectorTuple;
    size: VectorTuple;
    targetDelta: VectorTuple;
    targetDistance: number;
  } | null;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function isNotFoundError(error: unknown): boolean {
  if (!(error instanceof Error)) return false;
  return /\b404\b/i.test(error.message) || /\bnot found\b/i.test(error.message);
}

function toVectorTuple(vector: THREE.Vector3): VectorTuple {
  return [vector.x, vector.y, vector.z];
}

function toEulerDegreesTuple(euler: THREE.Euler): VectorTuple {
  return [
    THREE.MathUtils.radToDeg(euler.x),
    THREE.MathUtils.radToDeg(euler.y),
    THREE.MathUtils.radToDeg(euler.z),
  ];
}

function isFiniteBox(box: THREE.Box3): boolean {
  return [
    box.min.x,
    box.min.y,
    box.min.z,
    box.max.x,
    box.max.y,
    box.max.z,
  ].every(Number.isFinite);
}

function getSplatWorldBoundingBox(splatMesh: SplatMesh): THREE.Box3 | null {
  if (typeof splatMesh.getBoundingBox !== 'function') {
    return null;
  }

  if (!splatMesh.packedSplats && !splatMesh.extSplats) {
    return null;
  }

  const bbox = splatMesh.getBoundingBox(true).clone();
  splatMesh.updateMatrixWorld(true);
  bbox.applyMatrix4(splatMesh.matrixWorld);

  if (bbox.isEmpty() || !isFiniteBox(bbox)) {
    return null;
  }

  return bbox;
}

function shouldCenterResetOnBounds(box: THREE.Box3, defaultLookAt: THREE.Vector3): boolean {
  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());
  const maxAxis = Math.max(size.x, size.y, size.z, 0.001);
  const lateralOffset = Math.hypot(center.x - defaultLookAt.x, center.y - defaultLookAt.y);

  return lateralOffset > Math.max(
    CAMERA_RESET_CENTER_MIN_OFFSET,
    maxAxis * CAMERA_RESET_CENTER_LATERAL_RATIO,
  );
}

function shouldUseYFrontResetOnBounds(box: THREE.Box3): boolean {
  const size = box.getSize(new THREE.Vector3());
  const wideAxis = Math.max(size.x, size.y, 0.001);

  return (
    size.x > 0.001
    && size.y > 0.001
    && size.z > 0.001
    && size.z / wideAxis < CAMERA_RESET_Y_FRONT_DEPTH_RATIO
    && size.y > size.z
  );
}

function shouldUseCurrentModelVideoOrientation(): boolean {
  const state = useAppStore.getState();
  if (!state.currentModelId) {
    return false;
  }

  const currentItem = state.galleryItems.find((item) => item.id === state.currentModelId);
  return currentItem?.source_media_type === 'video' || Boolean(currentItem?.source_video_url);
}

async function resolveCurrentModelVideoOrientation(signal?: AbortSignal): Promise<boolean> {
  const state = useAppStore.getState();
  if (!state.currentModelId || state.currentModelUrl?.startsWith('blob:')) {
    return false;
  }

  if (shouldUseCurrentModelVideoOrientation()) {
    return true;
  }

  const currentItem = state.galleryItems.find((item) => item.id === state.currentModelId);
  if (!currentItem || currentItem.image_url) {
    return false;
  }

  try {
    const response = await fetch(
      `/api/gallery/${encodeURIComponent(state.currentModelId)}/source-video`,
      { method: 'HEAD', signal },
    );
    return response.ok;
  } catch {
    return false;
  }
}

function getBoundsCenteredCameraPosition(
  camera: THREE.PerspectiveCamera,
  box: THREE.Box3,
  target: THREE.Vector3,
): THREE.Vector3 {
  const size = box.getSize(new THREE.Vector3());
  const fov = THREE.MathUtils.degToRad(camera.fov);
  const halfFovTangent = Math.tan(fov / 2);
  const aspect = Math.max(camera.aspect || 1, 0.001);
  const fitHeightDistance = size.y / (2 * halfFovTangent);
  const fitWidthDistance = size.x / (2 * halfFovTangent * aspect);
  const fitDepthDistance = size.z + DEFAULT_CAMERA_CONFIG.minDistance;
  const distance = Math.max(
    DEFAULT_CAMERA_CONFIG.minDistance,
    fitHeightDistance,
    fitWidthDistance,
    fitDepthDistance,
  ) * CAMERA_RESET_FIT_PADDING;

  return target.clone().add(new THREE.Vector3(0, 0, distance));
}

function getControlsLimitConfig(
  limitsEnabled: boolean,
): ControlsLimitConfig {
  return limitsEnabled ? DEFAULT_CAMERA_CONFIG.limits : DEFAULT_CAMERA_CONFIG.freeMode;
}

function applyControlLimits(
  controls: OrbitControls,
  limitsEnabled: boolean,
): void {
  const config = getControlsLimitConfig(limitsEnabled);

  controls.minAzimuthAngle = config.minAzimuth;
  controls.maxAzimuthAngle = config.maxAzimuth;
  controls.minPolarAngle = config.minPolar;
  controls.maxPolarAngle = config.maxPolar;
}

function applySplatTransform(
  splatMesh: SplatMesh,
  transform: {
    positionX: number;
    positionY: number;
    positionZ: number;
    rotationX: number;
    rotationY: number;
    rotationZ: number;
    scale: number;
  },
  orientationMode: ViewerOrientationMode,
): void {
  splatMesh.position.set(
    transform.positionX,
    transform.positionY,
    transform.positionZ,
  );
  const userQuaternion = new THREE.Quaternion().setFromEuler(
    new THREE.Euler(transform.rotationX, transform.rotationY, transform.rotationZ),
  );
  if (orientationMode === 'y-front') {
    userQuaternion.premultiply(Y_FRONT_ORIENTATION_QUATERNION);
  }
  splatMesh.quaternion.copy(userQuaternion);
  splatMesh.scale.setScalar(Math.max(0.05, transform.scale));
  splatMesh.updateMatrixWorld(true);
}

function injectFocusRingStyle() {
  if (focusRingStyleInjected) return;
  focusRingStyleInjected = true;
  const style = document.createElement('style');
  style.textContent = `
    @keyframes spark-focus-ring {
      0%   { width: 0; height: 0; opacity: 0; border-width: 2.5px; }
      15%  { opacity: 0.95; }
      40%  { width: 36px; height: 36px; opacity: 0.8; border-width: 2px; }
      100% { width: 48px; height: 48px; opacity: 0; border-width: 1px; }
    }
    .spark-focus-ring {
      position: absolute;
      pointer-events: none;
      border: 2px solid rgba(255, 255, 255, 0.92);
      border-radius: 50%;
      transform: translate(-50%, -50%);
      box-shadow: 0 0 12px 2px rgba(255, 255, 255, 0.35),
                  0 0 4px rgba(255, 255, 255, 0.15);
      z-index: 50;
      animation: spark-focus-ring 500ms cubic-bezier(0.22, 1, 0.36, 1) forwards;
      will-change: width, height, opacity;
    }
  `;
  document.head.appendChild(style);
}

/** Show a focus ring indicator at the given position inside a container */
function showFocusRing(x: number, y: number, container: HTMLElement) {
  injectFocusRingStyle();
  const ring = document.createElement('div');
  ring.className = 'spark-focus-ring';
  ring.style.left = `${x}px`;
  ring.style.top = `${y}px`;
  container.appendChild(ring);
  ring.addEventListener('animationend', () => ring.remove(), { once: true });
}

/**
 * Viewer infrastructure exposed to child hooks via viewerRef.
 * Child hooks access: viewerRef.current.camera, .controls, .renderer, etc.
 */
export interface ViewerContext {
  camera: THREE.PerspectiveCamera;
  controls: OrbitControls;
  renderer: THREE.WebGLRenderer;
  scene: THREE.Scene;
  sparkRenderer: SparkRenderer;
  splatMesh: SplatMesh | null;
  debugBounds: THREE.Box3 | null;
  lastResetMode: ViewerResetMode;
  orientationMode: ViewerOrientationMode;
}

interface UseViewerOptions {
  revealEffect: RevealEffectId;
  replayToken: number;
}

export const useViewer = (
  containerRef: React.RefObject<HTMLDivElement | null>,
  { revealEffect, replayToken }: UseViewerOptions,
) => {
  const viewerRef = useRef<ViewerContext | null>(null);
  const revealEffectRuntimeRef = useRef(createRevealEffectRuntime());
  const lastDebugUpdateRef = useRef(0);
  const {
    currentModelUrl,
    currentModelFormat,
    currentModelSize,
    setLoading,
    resetLoadingProgress,
    setLoadingProgress,
    isLimitsOn,
    setCanCompareLod,
    setUsedRadLastLoad,
  } = useAppStore();
  const currentModelSourceSignature = useAppStore((state) => {
    const item = state.currentModelId
      ? state.galleryItems.find((candidate) => candidate.id === state.currentModelId)
      : null;

    return item
      ? [
        item.id,
        item.source_media_type ?? '',
        item.source_video_url ? 'source-video' : '',
      ].join('|')
      : '';
  });
  const [isViewerReady, setIsViewerReady] = useState(false);
  const [debugInfo, setDebugInfo] = useState<ViewerDebugInfo | null>(null);

  const refreshDebugBounds = useCallback((ctx: ViewerContext): THREE.Box3 | null => {
    if (!ctx.splatMesh) {
      ctx.debugBounds = null;
      return null;
    }

    ctx.debugBounds = getSplatWorldBoundingBox(ctx.splatMesh);
    return ctx.debugBounds;
  }, []);

  const getViewerDebugInfo = useCallback((ctx: ViewerContext): ViewerDebugInfo => {
    const cameraPosition = ctx.camera.position.clone();
    const cameraEuler = new THREE.Euler().setFromQuaternion(ctx.camera.quaternion, 'XYZ');
    const cameraForward = new THREE.Vector3();
    ctx.camera.getWorldDirection(cameraForward);

    const target = ctx.controls.target.clone();
    const cameraOffset = cameraPosition.clone().sub(target);
    const spherical = new THREE.Spherical().setFromVector3(cameraOffset);
    const bounds = ctx.debugBounds;
    const boundsCenter = bounds?.getCenter(new THREE.Vector3()) ?? null;
    const boundsSize = bounds?.getSize(new THREE.Vector3()) ?? null;
    const boundsTargetDelta = boundsCenter ? boundsCenter.clone().sub(target) : null;

    let modelPosition: THREE.Vector3 | null = null;
    let modelRotationDeg: VectorTuple | null = null;
    let modelScale: THREE.Vector3 | null = null;
    let modelRight: THREE.Vector3 | null = null;
    let modelUp: THREE.Vector3 | null = null;
    let modelForward: THREE.Vector3 | null = null;

    if (ctx.splatMesh) {
      ctx.splatMesh.updateMatrixWorld(true);
      const modelQuaternion = new THREE.Quaternion();
      modelPosition = ctx.splatMesh.getWorldPosition(new THREE.Vector3());
      modelScale = ctx.splatMesh.getWorldScale(new THREE.Vector3());
      ctx.splatMesh.getWorldQuaternion(modelQuaternion);
      modelRotationDeg = toEulerDegreesTuple(
        new THREE.Euler().setFromQuaternion(modelQuaternion, 'XYZ'),
      );
      modelRight = new THREE.Vector3(1, 0, 0).applyQuaternion(modelQuaternion).normalize();
      modelUp = new THREE.Vector3(0, 1, 0).applyQuaternion(modelQuaternion).normalize();
      modelForward = new THREE.Vector3(0, 0, -1).applyQuaternion(modelQuaternion).normalize();
    }

    return {
      resetMode: ctx.lastResetMode,
      camera: {
        position: toVectorTuple(cameraPosition),
        rotationDeg: toEulerDegreesTuple(cameraEuler),
        up: toVectorTuple(ctx.camera.up),
        forward: toVectorTuple(cameraForward),
      },
      controls: {
        target: toVectorTuple(target),
        distance: spherical.radius,
        orbitAzimuthDeg: THREE.MathUtils.radToDeg(ctx.controls.getAzimuthalAngle()),
        orbitPolarDeg: THREE.MathUtils.radToDeg(ctx.controls.getPolarAngle()),
      },
      model: {
        position: modelPosition ? toVectorTuple(modelPosition) : null,
        rotationDeg: modelRotationDeg,
        scale: modelScale ? toVectorTuple(modelScale) : null,
        right: modelRight ? toVectorTuple(modelRight) : null,
        up: modelUp ? toVectorTuple(modelUp) : null,
        forward: modelForward ? toVectorTuple(modelForward) : null,
      },
      bounds: bounds && boundsCenter && boundsSize && boundsTargetDelta
        ? {
          center: toVectorTuple(boundsCenter),
          size: toVectorTuple(boundsSize),
          targetDelta: toVectorTuple(boundsTargetDelta),
          targetDistance: boundsTargetDelta.length(),
        }
        : null,
    };
  }, []);

  const applyCurrentLodSettings = useCallback(() => {
    const ctx = viewerRef.current;
    if (!ctx) return;

    const state = useAppStore.getState();
    const preset = getLodPresetConfig(state.lodPreset);
    const quality = state.viewerQualityApplied;
    const lodEnabled = state.isLodEnabled && quality.lodEnabled;
    const effectivePreset = {
      ...preset,
      lodSplatScale: clamp(quality.lodScale, 0.2, 3.0),
      coneFoveate: clamp(quality.coneFoveate, 0, 1),
      behindFoveate: clamp(quality.behindFoveate, 0, 1),
    };

    ctx.sparkRenderer.enableLod = lodEnabled;
    applyLodPresetToRenderer(ctx.sparkRenderer, effectivePreset);

    if (ctx.splatMesh) {
      applyLodPresetToMesh(ctx.splatMesh, effectivePreset);
      ctx.splatMesh.enableLod = lodEnabled && state.lodCompareMode === 'lod';
    }

    ctx.sparkRenderer.sortDirty = true;
  }, []);

  const applyCurrentTransformSettings = useCallback(() => {
    const ctx = viewerRef.current;
    if (!ctx?.splatMesh) return;
    if (ctx.renderer.xr.isPresenting) return;

    const transform = useAppStore.getState().viewerTransformApplied;
    applySplatTransform(ctx.splatMesh, transform, ctx.orientationMode);
    refreshDebugBounds(ctx);
    ctx.sparkRenderer.sortDirty = true;
  }, [refreshDebugBounds]);

  const applyCurrentInteractionSettings = useCallback(() => {
    const ctx = viewerRef.current;
    if (!ctx) return;

    const interaction = useAppStore.getState().viewerInteractionApplied;
    const reverseDirection = interaction.reversePointerDirection ? -1 : 1;
    const reverseSlide = interaction.reversePointerSlide ? -1 : 1;
    const currentZoomMagnitude = Math.max(
      0.01,
      Math.abs(ctx.controls.zoomSpeed || DEFAULT_CAMERA_CONFIG.zoomSpeed),
    );

    ctx.controls.rotateSpeed = Math.abs(DEFAULT_CAMERA_CONFIG.rotateSpeed) * reverseDirection;
    ctx.controls.panSpeed = Math.abs(DEFAULT_CAMERA_CONFIG.panSpeed) * reverseSlide;
    ctx.controls.zoomSpeed = currentZoomMagnitude * reverseDirection;
  }, []);

  // ── Reset Camera (defined early so child hooks can reference it) ────
  const resetCamera = useCallback(() => {
    const ctx = viewerRef.current;
    if (!ctx) return;

    const activeCtx = ctx;
    const c = activeCtx.controls;

    let targetPos = new THREE.Vector3(...DEFAULT_CAMERA_CONFIG.initialPosition);
    const targetLookAt = new THREE.Vector3(0, 0, 0);
    const targetUp = new THREE.Vector3(...DEFAULT_CAMERA_CONFIG.cameraUp);

    // Dynamic intersection point algorithm: Calculate where the front face of the bounding box starts
    // and push the focus point inward proportionally (a quadratic curve modeled from sample data)
    let dynamicOffset = DEFAULT_CAMERA_CONFIG.orbitTargetOffset || 1.5;
    let splatBounds: THREE.Box3 | null = null;
    const shouldPreferVideoOrientation =
      activeCtx.orientationMode === 'y-front' || shouldUseCurrentModelVideoOrientation();
    ctx.lastResetMode = 'bounds-unavailable';

    if (
      activeCtx.splatMesh &&
      typeof activeCtx.splatMesh.getBoundingBox === 'function' &&
      !activeCtx.renderer.xr.isPresenting
    ) {
      try {
        splatBounds = refreshDebugBounds(activeCtx);

        if (splatBounds) {
          const shouldAdaptYFront =
            activeCtx.orientationMode === 'default'
            && (shouldPreferVideoOrientation || shouldUseYFrontResetOnBounds(splatBounds));

          if (shouldAdaptYFront) {
            activeCtx.orientationMode = 'y-front';
            applyCurrentTransformSettings();
            splatBounds = refreshDebugBounds(activeCtx) ?? splatBounds;
          }

          activeCtx.lastResetMode = 'bounds-default';
          // Camera is positioned at targetPos.
          // Since camera initially looks down -Z, the frontest point of the model is max.z.
          const frontZ = splatBounds.max.z;
          // DF (Distance to Front): Distance from camera to the frontest visible surface.
          const distToFront = Math.max(0.1, targetPos.z - frontZ);

          // Best-fit curve from user samples: Offset = DF + 0.08 * DF^2.
          dynamicOffset = distToFront + 0.08 * Math.pow(distToFront, 2);
        }
      } catch (error) {
        console.warn('[Viewer] Bounding box unavailable, using default reset offset:', error);
      }
    }

    // Compute pivot along the viewing direction
    const forwardDir = new THREE.Vector3(0, 0, -1);
    targetLookAt.copy(targetPos).add(forwardDir.multiplyScalar(dynamicOffset));

    if (
      splatBounds
      && (shouldPreferVideoOrientation || shouldCenterResetOnBounds(splatBounds, targetLookAt))
    ) {
      splatBounds.getCenter(targetLookAt);
      targetPos = getBoundsCenteredCameraPosition(activeCtx.camera, splatBounds, targetLookAt);
      activeCtx.lastResetMode = activeCtx.orientationMode === 'y-front'
        ? 'bounds-y-front'
        : 'bounds-centered';
    } else if (!splatBounds) {
      activeCtx.lastResetMode = 'default';
    }

    const startPos = c.object.position.clone();
    const startLookAt = c.target.clone();
    const startUp = c.object.up.clone();
    applyControlLimits(c, useAppStore.getState().isLimitsOn);

    const startTime = performance.now();
    const duration = DEFAULT_CAMERA_CONFIG.resetAnimationDuration;

    function animate() {
      const now = performance.now();
      const progress = Math.min((now - startTime) / duration, 1);
      const ease = 1 - Math.pow(1 - progress, 3);

      c.object.position.lerpVectors(startPos, targetPos, ease);
      c.target.lerpVectors(startLookAt, targetLookAt, ease);
      c.object.up.lerpVectors(startUp, targetUp, ease).normalize();
      c.update();
      setDebugInfo(getViewerDebugInfo(activeCtx));

      if (progress < 1) {
        requestAnimationFrame(animate);
      }
    }

    requestAnimationFrame(animate);
  }, [applyCurrentTransformSettings, getViewerDebugInfo, refreshDebugBounds]);

  // Child hooks — they read viewerRef.current.camera / .controls
  const { speedMode } = useKeyboard(viewerRef, resetCamera);
  const { handleToggle: toggleGyro, isSupported: isGyroSupported, indicatorBallRef } = useGyroscope({ viewerRef });
  const joystick = useJoystick({ viewerRef });
  const xr = useXR({ viewerRef });

  useEffect(() => {
    const runtime = revealEffectRuntimeRef.current;
    syncRevealEffectSelection(runtime, revealEffect, replayToken);

    const ctx = viewerRef.current;
    if (!ctx?.splatMesh) return;

    if (!isRevealEffectEnabled(revealEffect)) {
      if (ctx.splatMesh.objectModifiers?.includes(runtime.modifier)) {
        ctx.splatMesh.objectModifier = undefined;
        ctx.splatMesh.updateGenerator();
      }
    } else if (!ctx.splatMesh.objectModifiers?.includes(runtime.modifier)) {
      applyRevealEffectToMesh(runtime, ctx.splatMesh);
    }

    ctx.splatMesh.updateVersion();
    ctx.sparkRenderer.sortDirty = true;
  }, [replayToken, revealEffect]);

  // ── Initialize Three.js + Spark infrastructure ──────────────────────
  useEffect(() => {
    if (!containerRef.current) return;

    const container = containerRef.current;
    let isDisposed = false;

    const initViewer = () => {
      if (isDisposed) return; // Prevent re-initialization if already disposed
      if (!containerRef.current) return; // Ensure container still exists

      const state = useAppStore.getState();
      const isHighFidelity = state.isHighFidelity;
      const preset = getLodPresetConfig(state.lodPreset);
      const quality = state.viewerQualityApplied;
      const lodEnabled = state.isLodEnabled && quality.lodEnabled;
      const effectivePreset = {
        ...preset,
        lodSplatScale: clamp(quality.lodScale, 0.2, 3.0),
        coneFoveate: clamp(quality.coneFoveate, 0, 1),
        behindFoveate: clamp(quality.behindFoveate, 0, 1),
      };

      try {
        // Scene
        const scene = new THREE.Scene();

        // Camera
        const { fov, near, far } = DEFAULT_CAMERA_CONFIG;
        const aspect = container.clientWidth / container.clientHeight || 1;
        const camera = new THREE.PerspectiveCamera(fov, aspect, near, far);
        camera.up.set(...DEFAULT_CAMERA_CONFIG.cameraUp); // Corrected typo from cameraCameraUp
        camera.position.set(...DEFAULT_CAMERA_CONFIG.initialPosition);

        // Renderer — antialias: false per Spark recommendation (splats don't benefit)
        const renderer = new THREE.WebGLRenderer({ antialias: false, alpha: true });

        // If High Fidelity is ON, use native device pixel ratio without capping to unleash max sharpness
        renderer.setPixelRatio(isHighFidelity ? window.devicePixelRatio : Math.min(window.devicePixelRatio, 2));

        renderer.setSize(container.clientWidth, container.clientHeight);
        container.appendChild(renderer.domElement);

        // OrbitControls
        const controls = new OrbitControls(camera, renderer.domElement);
        // Apply settings directly
        controls.mouseButtons = {
          LEFT: THREE.MOUSE.ROTATE,
          MIDDLE: THREE.MOUSE.DOLLY,
          RIGHT: THREE.MOUSE.PAN,
        };
        controls.touches = {
          ONE: THREE.TOUCH.ROTATE,
          TWO: THREE.TOUCH.DOLLY_PAN,
        };
        controls.enableDamping = true;
        controls.dampingFactor = 0.05;
        controls.maxDistance = DEFAULT_CAMERA_CONFIG.maxDistance;
        controls.maxPolarAngle = 180 * THREE.MathUtils.DEG2RAD; // 180deg

        // SparkRenderer — must be explicitly added to scene (Spark 2.0)
        // When High Fidelity is ON, set blurAmount and preBlurAmount to 0 to remove forced anti-aliasing
        const sparkRenderer = new SparkRenderer({
          renderer,
          ...(isHighFidelity ? { blurAmount: 0, preBlurAmount: 0 } : {}),
          enableLod: lodEnabled,
          lodSplatScale: effectivePreset.lodSplatScale,
          lodRenderScale: effectivePreset.lodRenderScale,
          behindFoveate: effectivePreset.behindFoveate,
          coneFov0: effectivePreset.coneFov0,
          coneFov: effectivePreset.coneFov,
          coneFoveate: effectivePreset.coneFoveate,
        });
        scene.add(sparkRenderer);

        // Render loop
        renderer.setAnimationLoop(() => {
          const now = performance.now();
          const activeMesh = viewerRef.current?.splatMesh;
          if (
            activeMesh
            && isRevealEffectEnabled(revealEffectRuntimeRef.current.activeEffect)
          ) {
            const revealUpdated = updateRevealEffectPlayback(revealEffectRuntimeRef.current, now);
            if (revealUpdated) {
              activeMesh.updateVersion();
            }
          }
          controls.update();

          const activeContext = viewerRef.current;
          if (
            activeContext
            && useAppStore.getState().quickControlsOpen
            && now - lastDebugUpdateRef.current >= DEBUG_UPDATE_INTERVAL_MS
          ) {
            lastDebugUpdateRef.current = now;
            setDebugInfo(getViewerDebugInfo(activeContext));
          }

          renderer.render(scene, camera);
        });

        // ── Click-to-focus: raycast on click → orbit around hit point ──
        const raycaster = new THREE.Raycaster();
        const ndcCoord = new THREE.Vector2();
        let pointerDownPos = { x: 0, y: 0 };

        const onPointerDown = (e: PointerEvent) => {
          pointerDownPos = { x: e.clientX, y: e.clientY };
        };

        const onPointerUp = (e: PointerEvent) => {
          // Only treat as click if pointer didn't move (not drag)
          const dx = e.clientX - pointerDownPos.x;
          const dy = e.clientY - pointerDownPos.y;
          if (dx * dx + dy * dy > 9) return; // 3px threshold

          const ctx = viewerRef.current;
          if (!ctx?.splatMesh) return;

          const rect = renderer.domElement.getBoundingClientRect();
          ndcCoord.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
          ndcCoord.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

          raycaster.setFromCamera(ndcCoord, camera);
          const hits = raycaster.intersectObject(ctx.splatMesh);
          if (hits.length === 0) return;

          // Smooth animate controls.target to the hit point
          const hitPoint = hits[0].point.clone();
          const startTarget = controls.target.clone();
          const startTime = performance.now();
          const dist = startTarget.distanceTo(hitPoint);
          // Duration scales with distance: 300–600ms
          const duration = Math.min(600, Math.max(300, dist * 400));

          function animateFocus() {
            const elapsed = performance.now() - startTime;
            const t = Math.min(elapsed / duration, 1);
            // Exponential ease-out: fast start, very smooth deceleration
            const ease = 1 - Math.pow(1 - t, 4);
            controls.target.lerpVectors(startTarget, hitPoint, ease);
            controls.update();
            if (t < 1) requestAnimationFrame(animateFocus);
          }
          requestAnimationFrame(animateFocus);

          // Show focus ring indicator at click position
          showFocusRing(e.clientX - rect.left, e.clientY - rect.top, container);
        };

        renderer.domElement.addEventListener('pointerdown', onPointerDown);
        renderer.domElement.addEventListener('pointerup', onPointerUp);

        viewerRef.current = {
          camera,
          controls,
          renderer,
          scene,
          sparkRenderer,
          splatMesh: null,
          debugBounds: null,
          lastResetMode: 'default',
          orientationMode: 'default',
        };
        applyCurrentInteractionSettings();
        setIsViewerReady(true);
      } catch (error) {
        console.error('[Viewer] Failed to initialize:', error);
      }
    };

    // Resize handler — ResizeObserver catches sidebar collapse, window resize, fullscreen, etc.
    const resizeObserver = new ResizeObserver(() => {
      const ctx = viewerRef.current;
      if (!ctx) return;
      if (ctx.renderer.xr.isPresenting) return;
      requestAnimationFrame(() => {
        const w = container.clientWidth;
        const h = container.clientHeight;
        if (w === 0 || h === 0) return;
        ctx.camera.aspect = w / h;
        ctx.camera.updateProjectionMatrix();
        ctx.renderer.setSize(w, h);
      });
    });
    resizeObserver.observe(container);

    // Re-initialize if container ref changes or if high fidelity setting is toggled
    let lastHF = useAppStore.getState().isHighFidelity;
    const unsubscribeHF = useAppStore.subscribe((state) => {
      const newHF = state.isHighFidelity;
      if (newHF !== lastHF) {
        lastHF = newHF;
        // Hard tear-down and re-init to apply new pixelRatio properly
        if (viewerRef.current) {
          viewerRef.current.renderer.domElement.removeEventListener('pointerdown', () => { });
          viewerRef.current.renderer.domElement.removeEventListener('pointerup', () => { });
          viewerRef.current.renderer.setAnimationLoop(null);
          viewerRef.current.splatMesh?.dispose();
          viewerRef.current.scene.remove(viewerRef.current.sparkRenderer);
          viewerRef.current.sparkRenderer.geometry?.dispose();
          viewerRef.current.sparkRenderer.material?.dispose();
          viewerRef.current.controls.dispose();
          viewerRef.current.renderer.dispose();
          viewerRef.current.renderer.domElement.remove();
          viewerRef.current = null;
          setIsViewerReady(false);
          if (containerRef.current) containerRef.current.innerHTML = ''; // Clear container
        }
        initViewer();
        // Let the other useEffect reload the model since the canvas is fresh.
      }
    }
    );

    const getLodSignature = () => {
      const state = useAppStore.getState();
      return [
        state.isLodEnabled,
        state.lodPreset,
        state.lodCompareMode,
        state.viewerQualityApplied.lodEnabled,
        state.viewerQualityApplied.lodScale,
        state.viewerQualityApplied.coneFoveate,
        state.viewerQualityApplied.behindFoveate,
      ].join('|');
    };

    const getTransformSignature = () => {
      const state = useAppStore.getState();
      return [
        state.viewerTransformApplied.positionX,
        state.viewerTransformApplied.positionY,
        state.viewerTransformApplied.positionZ,
        state.viewerTransformApplied.rotationX,
        state.viewerTransformApplied.rotationY,
        state.viewerTransformApplied.rotationZ,
        state.viewerTransformApplied.scale,
      ].join('|');
    };

    const getInteractionSignature = () => {
      const state = useAppStore.getState();
      return [
        state.viewerInteractionApplied.reversePointerDirection,
        state.viewerInteractionApplied.reversePointerSlide,
      ].join('|');
    };

    let lodSignature = getLodSignature();
    let transformSignature = getTransformSignature();
    let interactionSignature = getInteractionSignature();

    const unsubscribeLod = useAppStore.subscribe(() => {
      const nextSignature = getLodSignature();
      if (nextSignature === lodSignature) return;
      lodSignature = nextSignature;
      applyCurrentLodSettings();
    });

    const unsubscribeTransform = useAppStore.subscribe(() => {
      const nextSignature = getTransformSignature();
      if (nextSignature === transformSignature) return;
      transformSignature = nextSignature;
      applyCurrentTransformSettings();
    });

    const unsubscribeInteraction = useAppStore.subscribe(() => {
      const nextSignature = getInteractionSignature();
      if (nextSignature === interactionSignature) return;
      interactionSignature = nextSignature;
      applyCurrentInteractionSettings();
    });

    // Initial viewer setup
    initViewer();

    return () => {
      isDisposed = true;
      unsubscribeHF();
      unsubscribeLod();
      unsubscribeTransform();
      unsubscribeInteraction();
      resizeObserver.disconnect();

      const ctx = viewerRef.current;
      if (ctx) {
        ctx.renderer.domElement.removeEventListener('pointerdown', () => { });
        ctx.renderer.domElement.removeEventListener('pointerup', () => { });
        ctx.renderer.setAnimationLoop(null);
        ctx.splatMesh?.dispose();
        ctx.scene.remove(ctx.sparkRenderer);
        ctx.sparkRenderer.geometry?.dispose();
        ctx.sparkRenderer.material?.dispose();
        ctx.controls.dispose();
        ctx.renderer.dispose();
        ctx.renderer.domElement.remove();
      }
      viewerRef.current = null;
      setIsViewerReady(false);
      setCanCompareLod(false);
      setUsedRadLastLoad(false);
      setDebugInfo(null);
    };
  }, [
    containerRef,
    applyCurrentInteractionSettings,
    applyCurrentLodSettings,
    applyCurrentTransformSettings,
    getViewerDebugInfo,
    setCanCompareLod,
    setUsedRadLastLoad,
  ]);

  // ── Load Model ──────────────────────────────────────────────────────
  useEffect(() => {
    const ctx = viewerRef.current;
    if (!ctx || !currentModelUrl) {
      setCanCompareLod(false);
      setUsedRadLastLoad(false);
      setDebugInfo(null);
      return;
    }

    let cancelled = false;
    const abortController = new AbortController();

    const load = async () => {
      resetLoadingProgress();
      setLoading(true, 'Loading Scene...');

      try {
        const useVideoOrientation = await resolveCurrentModelVideoOrientation(abortController.signal);
        if (cancelled) {
          return;
        }

        // Remove previous splatMesh if any
        if (ctx.splatMesh) {
          ctx.scene.remove(ctx.splatMesh);
          ctx.splatMesh.dispose();
          ctx.splatMesh = null;
          ctx.debugBounds = null;
          ctx.orientationMode = 'default';
        }

        const state = useAppStore.getState();
        const preset = getLodPresetConfig(state.lodPreset);
        const quality = state.viewerQualityApplied;
        const lodEnabled = state.isLodEnabled && quality.lodEnabled;
        const effectivePreset = {
          ...preset,
          lodSplatScale: clamp(quality.lodScale, 0.2, 3.0),
          coneFoveate: clamp(quality.coneFoveate, 0, 1),
          behindFoveate: clamp(quality.behindFoveate, 0, 1),
        };
        const fallbackFileType = getSplatFileTypeFromFormat(currentModelFormat);

        const createSplatMesh = async ({
          url,
          fileType,
          paged,
        }: {
          url: string;
          fileType?: SplatFileType;
          paged?: boolean;
        }) => {
          const handleProgress = (event: ProgressEvent) => {
            if (cancelled || !Number.isFinite(event.loaded) || event.loaded <= 0) {
              return;
            }

            const reportedTotal = Number.isFinite(event.total) && event.total > 0
              ? event.total
              : null;
            const knownSourceSize = url === currentModelUrl ? currentModelSize : null;
            const total = reportedTotal ?? knownSourceSize;
            if (!total || total <= 0) {
              return;
            }

            const ratio = Math.min(1, Math.max(0, event.loaded / total));
            setLoadingProgress(Math.min(95, ratio * 95));
          };

          // Prefer public 2.0 options and keep LoD toggles runtime-switchable.
          const mesh = new SplatMesh({
            url,
            fileType,
            ...(lodEnabled ? { lod: true, nonLod: true } : {}),
            enableLod: lodEnabled && state.lodCompareMode === 'lod',
            lodScale: effectivePreset.lodSplatScale,
            behindFoveate: effectivePreset.behindFoveate,
            coneFov0: effectivePreset.coneFov0,
            coneFov: effectivePreset.coneFov,
            coneFoveate: effectivePreset.coneFoveate,
            ...(paged !== undefined ? { paged } : {}),
            onProgress: handleProgress,
          });
          try {
            await mesh.initialized;
            return mesh;
          } catch (error) {
            // Failed RAD/streaming initialization may keep internal fetchers alive if not disposed.
            mesh.dispose();
            throw error;
          }
        };

        const looksLikeRad =
          currentModelFormat === 'rad' || /\.rad(?:\?|$)/i.test(currentModelUrl);
        const radCandidateUrl = state.radModeEnabled
          ? (looksLikeRad ? currentModelUrl : deriveRadUrl(currentModelUrl))
          : null;
        const shouldTryRad = Boolean(
          state.radModeEnabled &&
          radCandidateUrl &&
          !missingRadCache.has(radCandidateUrl),
        );

        let loadedWithRad = false;
        let splatMesh: SplatMesh | null = null;

        if (shouldTryRad && radCandidateUrl) {
          try {
            splatMesh = await createSplatMesh({
              url: radCandidateUrl,
              fileType: SplatFileType.RAD,
              paged: state.radPagedEnabled,
            });
            loadedWithRad = true;
          } catch (error) {
            if (!looksLikeRad && isNotFoundError(error)) {
              missingRadCache.add(radCandidateUrl);
            }
            console.warn('[Viewer] RAD load failed, fallback to default format:', error);
            if (looksLikeRad) throw error;
          }
        }

        if (!splatMesh) {
          splatMesh = await createSplatMesh({
            url: currentModelUrl,
            fileType: fallbackFileType,
          });
        }

        if (cancelled) {
          splatMesh.dispose();
          return;
        }

        ctx.scene.add(splatMesh);
        ctx.splatMesh = splatMesh;
        ctx.orientationMode = useVideoOrientation ? 'y-front' : 'default';
        applyRevealEffectToMesh(revealEffectRuntimeRef.current, splatMesh);
        applyCurrentTransformSettings();
        refreshDebugBounds(ctx);

        const hasComparison = lodEnabled && hasLodComparisonData(splatMesh);
        setCanCompareLod(hasComparison);
        setUsedRadLastLoad(loadedWithRad);
        applyCurrentLodSettings();

        setLoadingProgress(100);
        setLoading(false);

        // Apply limits and reset camera after model loads
        applyLimits();
        resetCamera();
      } catch (error) {
        if (!cancelled) {
          console.error('[Viewer] Error loading model:', error);
          setCanCompareLod(false);
          setUsedRadLastLoad(false);
          setLoading(false);
        }
      }
    };

    load();
    return () => {
      cancelled = true;
      abortController.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    currentModelUrl,
    currentModelFormat,
    currentModelSize,
    currentModelSourceSignature,
    isViewerReady,
    applyCurrentLodSettings,
    applyCurrentTransformSettings,
    refreshDebugBounds,
    setCanCompareLod,
    setLoading,
    resetLoadingProgress,
    setLoadingProgress,
    setUsedRadLastLoad,
    resetCamera,
  ]); // Added isViewerReady to dependencies to ensure model loads after viewer re-init

  // ── Apply Angle / Distance Limits ───────────────────────────────────
  const applyLimits = useCallback(() => {
    const ctx = viewerRef.current;
    if (!ctx) return;

    const c = ctx.controls;
    applyControlLimits(c, isLimitsOn);
    c.update();
  }, [isLimitsOn]);

  useEffect(() => {
    applyLimits();
  }, [isLimitsOn, applyLimits]);

  return {
    viewerRef,
    isViewerReady,
    speedMode,
    resetCamera,
    toggleGyro,
    isGyroSupported,
    indicatorBallRef,
    joystick,
    xr,
    debugInfo,
  };
};
