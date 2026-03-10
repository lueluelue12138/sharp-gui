import { useEffect, useRef, useCallback, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { SparkRenderer, SplatMesh, SplatFileType } from '@sparkjsdev/spark';
import type { SplatMeshOptions } from '@sparkjsdev/spark';
import { useAppStore } from '@/store/useAppStore';
import { DEFAULT_CAMERA_CONFIG } from '@/utils/camera';
import { useKeyboard } from './useKeyboard';
import { useGyroscope } from './useGyroscope';
import { useJoystick } from './useJoystick';
import { useXR } from './useXR';

// Inject focus-ring CSS animation once
let focusRingStyleInjected = false;
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
}

export const useViewer = (containerRef: React.RefObject<HTMLDivElement | null>) => {
  const viewerRef = useRef<ViewerContext | null>(null);
  const {
    currentModelUrl,
    currentModelFormat,
    setLoading,
    setLoadingProgress,
    isLimitsOn,
  } = useAppStore();
  const [isViewerReady, setIsViewerReady] = useState(false);

  // ── Reset Camera (defined early so child hooks can reference it) ────
  const resetCamera = useCallback(() => {
    const ctx = viewerRef.current;
    if (!ctx) return;

    const c = ctx.controls;

    const targetPos = new THREE.Vector3(...DEFAULT_CAMERA_CONFIG.initialPosition);
    let targetLookAt = new THREE.Vector3(0, 0, 0);
    const targetUp = new THREE.Vector3(...DEFAULT_CAMERA_CONFIG.cameraUp);

    // Dynamic intersection point algorithm: Calculate where the front face of the bounding box starts
    // and push the focus point inward proportionally (a quadratic curve modeled from sample data)
    let dynamicOffset = DEFAULT_CAMERA_CONFIG.orbitTargetOffset || 1.5;

    if (ctx.splatMesh && typeof ctx.splatMesh.getBoundingBox === 'function') {
      if (!ctx.renderer.xr.isPresenting) {
        ctx.splatMesh.updateMatrixWorld(true);
        const bbox = ctx.splatMesh.getBoundingBox().clone();
        bbox.applyMatrix4(ctx.splatMesh.matrixWorld);

        if (!bbox.isEmpty()) {
          // Camera is positioned at targetPos 
          // Since camera initially looks down -Z, the frontest point of the model is max.z
          const frontZ = bbox.max.z;
          // DF (Distance to Front): Distance from camera to the frontest visible surface
          const distToFront = Math.max(0.1, targetPos.z - frontZ);

          // Best-fit curve from user samples: Offset = DF + 0.08 * DF^2
          dynamicOffset = distToFront + 0.08 * Math.pow(distToFront, 2);
        }
      }
    }

    // Compute pivot along the viewing direction
    const forwardDir = new THREE.Vector3(0, 0, -1);
    targetLookAt.copy(targetPos).add(forwardDir.multiplyScalar(dynamicOffset));
    const startPos = c.object.position.clone();
    const startLookAt = c.target.clone();
    const startUp = c.object.up.clone();

    const startTime = performance.now();
    const duration = DEFAULT_CAMERA_CONFIG.resetAnimationDuration;

    function animate() {
      const now = performance.now();
      const progress = Math.min((now - startTime) / duration, 1);
      const ease = 1 - Math.pow(1 - progress, 3);

      c.object.position.lerpVectors(startPos, targetPos, ease);
      c.target.lerpVectors(startLookAt, targetLookAt, ease);
      c.object.up.lerpVectors(startUp, targetUp, ease);
      c.update();

      if (progress < 1) {
        requestAnimationFrame(animate);
      }
    }

    requestAnimationFrame(animate);
  }, []);

  // Child hooks — they read viewerRef.current.camera / .controls
  const { speedMode } = useKeyboard(viewerRef, resetCamera);
  const { handleToggle: toggleGyro, isSupported: isGyroSupported, indicatorBallRef } = useGyroscope({ viewerRef });
  const joystick = useJoystick({ viewerRef });
  const xr = useXR({ viewerRef });

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
          ...(isHighFidelity ? { blurAmount: 0, preBlurAmount: 0 } : {})
        });
        scene.add(sparkRenderer);

        // Render loop
        renderer.setAnimationLoop(() => {
          controls.update();
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

        viewerRef.current = { camera, controls, renderer, scene, sparkRenderer, splatMesh: null };
        setIsViewerReady(true);
      } catch (error) {
        console.error('[Viewer] Failed to initialize:', error);
      }
    };

    // Resize handler — ResizeObserver catches sidebar collapse, window resize, fullscreen, etc.
    const resizeObserver = new ResizeObserver(() => {
      const ctx = viewerRef.current;
      if (!ctx) return;
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

    // Initial viewer setup
    initViewer();

    return () => {
      isDisposed = true;
      unsubscribeHF();
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
    };
  }, []);

  // ── Load Model ──────────────────────────────────────────────────────
  useEffect(() => {
    const ctx = viewerRef.current;
    if (!ctx || !currentModelUrl) return;

    let cancelled = false;

    const load = async () => {
      setLoading(true, 'Loading Scene...');
      setLoadingProgress(0);

      try {
        // Remove previous splatMesh if any
        if (ctx.splatMesh) {
          ctx.scene.remove(ctx.splatMesh);
          ctx.splatMesh.dispose();
          ctx.splatMesh = null;
        }

        // Determine file type for blob URLs that lack extensions
        let fileType: SplatFileType | undefined;
        if (currentModelFormat === 'ply') fileType = SplatFileType.PLY;
        else if (currentModelFormat === 'splat') fileType = SplatFileType.SPLAT;
        else if (currentModelFormat === 'spz') fileType = SplatFileType.SPZ;

        // Spark 2.0: SplatMesh handles loading directly
        const isLodEnabled = useAppStore.getState().isLodEnabled;
        const splatMesh = new SplatMesh({
          url: currentModelUrl,
          fileType,
          // Forward to Spark — currently silently ignored in v2.0.0-preview,
          // but reserved for future LOD support in the stable release.
          ...(isLodEnabled ? { lod: true } : {}),
        } as SplatMeshOptions & { lod?: boolean });
        await splatMesh.initialized;

        if (cancelled) {
          splatMesh.dispose();
          return;
        }

        splatMesh.scale.setScalar(DEFAULT_CAMERA_CONFIG.modelScale);
        // Gaussian Splats are trained in OpenCV/COLMAP convention (Y-down, Z-forward).
        // Three.js uses Y-up, Z-toward-viewer. Rotating 180° around X corrects both axes.
        splatMesh.rotation.x = Math.PI;
        ctx.scene.add(splatMesh);
        ctx.splatMesh = splatMesh;

        // Spark 2.0 dynamic focal viewport completely initialized.


        setLoading(false);

        // Apply limits and reset camera after model loads
        applyLimits();
        resetCamera();
      } catch (error) {
        if (!cancelled) {
          console.error('[Viewer] Error loading model:', error);
          setLoading(false);
        }
      }
    };

    load();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentModelUrl, currentModelFormat, isViewerReady]); // Added isViewerReady to dependencies to ensure model loads after viewer re-init

  // ── Apply Angle / Distance Limits ───────────────────────────────────
  const applyLimits = useCallback(() => {
    const ctx = viewerRef.current;
    if (!ctx) return;

    const c = ctx.controls;
    const config = isLimitsOn ? DEFAULT_CAMERA_CONFIG.limits : DEFAULT_CAMERA_CONFIG.freeMode;

    c.minAzimuthAngle = config.minAzimuth;
    c.maxAzimuthAngle = config.maxAzimuth;
    c.minPolarAngle = config.minPolar;
    c.maxPolarAngle = config.maxPolar;
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
  };
};
