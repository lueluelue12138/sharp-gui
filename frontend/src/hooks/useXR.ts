import { useState, useEffect, useCallback, useRef, type RefObject } from 'react';
import * as THREE from 'three';
import type { ViewerContext } from './useViewer';
import { useAppStore } from '@/store/useAppStore';
import { DEFAULT_CAMERA_CONFIG } from '@/utils/camera';

type XRMode = 'vr' | 'ar';

interface UseXRProps {
  viewerRef: RefObject<ViewerContext | null>;
}

interface UseXRReturn {
  isVRSupported: boolean;
  isARSupported: boolean;
  isInXR: boolean;
  currentMode: XRMode | null;
  enterVR: () => Promise<void>;
  enterAR: () => Promise<void>;
  exitXR: () => Promise<void>;
  isCheckingSupport: boolean;
}

// Movement settings
const VR_MOVE_SPEED = 0.05;
const VR_TURN_SPEED = 0.03;
const DEADZONE = 0.15;

// Mobile AR touch orbit settings
const AR_TOUCH_ROTATE_SPEED = 0.004;
const AR_TOUCH_PINCH_SPEED = 0.01;

/**
 * Hook to manage WebXR sessions (VR + AR) with Camera Rig locomotion.
 *
 * Architecture: A `THREE.Group` ("rig") is created as the camera's parent.
 * Controller joystick input moves/rotates the rig, which in turn moves the
 * camera through the scene — the standard Three.js WebXR pattern.
 *
 * VR mode: Fully immersive, opaque scene background.
 * AR mode: Passthrough / see-through, transparent scene background.
 */
export const useXR = ({ viewerRef }: UseXRProps): UseXRReturn => {
  const [isVRSupported, setIsVRSupported] = useState(false);
  const [isARSupported, setIsARSupported] = useState(false);
  const [isInXR, setIsInXR] = useState(false);
  const [currentMode, setCurrentMode] = useState<XRMode | null>(null);
  const [isCheckingSupport, setIsCheckingSupport] = useState(true);

  const sessionRef = useRef<XRSession | null>(null);
  const rigRef = useRef<THREE.Group | null>(null);
  const savedBackgroundRef = useRef<THREE.Color | THREE.Texture | null>(null);
  const arTouchCleanupRef = useRef<(() => void) | null>(null);
  // Store calibrated rig home position so reset goes back to calibrated state
  const rigHomeRef = useRef<{ y: number; z: number }>({ y: 0, z: 0 });

  // ── Check XR support on mount ───────────────────────────────────────
  useEffect(() => {
    const checkXRSupport = async () => {
      setIsCheckingSupport(true);
      try {
        if ('xr' in navigator && navigator.xr) {
          const [vrSupported, arSupported] = await Promise.all([
            navigator.xr.isSessionSupported('immersive-vr').catch(() => false),
            navigator.xr.isSessionSupported('immersive-ar').catch(() => false),
          ]);
          setIsVRSupported(vrSupported);
          setIsARSupported(arSupported);
          console.log('[XR] VR:', vrSupported ? '✅' : '❌', '| AR:', arSupported ? '✅' : '❌');
        } else {
          setIsVRSupported(false);
          setIsARSupported(false);
          console.log('[XR] WebXR API not available');
        }
      } catch (e) {
        console.warn('[XR] Support check failed:', e);
        setIsVRSupported(false);
        setIsARSupported(false);
      } finally {
        setIsCheckingSupport(false);
      }
    };

    checkXRSupport();
  }, []);

  // ── Process controller input — move the Camera Rig ──────────────────
  const processControllerInput = useCallback((session: XRSession, rig: THREE.Group) => {
    const ctx = viewerRef.current;
    if (!ctx) return;

    const xrCamera = ctx.renderer.xr.getCamera();
    const camera = xrCamera || ctx.camera;

    for (const inputSource of session.inputSources) {
      if (!inputSource.gamepad) continue;

      const { axes, buttons } = inputSource.gamepad;

      // ── A / X button (index 4) → Reset rig to calibrated home position ──
      if (buttons.length > 4 && buttons[4].pressed) {
        const home = rigHomeRef.current;
        rig.position.set(0, home.y, home.z);
        rig.rotation.set(0, 0, 0);
      }

      let moveX = 0;
      let moveY = 0;
      let turnX = 0;
      let turnY = 0;

      if (inputSource.handedness === 'left') {
        moveX = axes.length > 2 ? axes[2] : axes[0];
        moveY = axes.length > 3 ? axes[3] : axes[1];
      } else if (inputSource.handedness === 'right') {
        turnX = axes.length > 2 ? axes[2] : axes[0];
        turnY = axes.length > 3 ? axes[3] : axes[1];
      }

      // Apply deadzone
      if (Math.abs(moveX) < DEADZONE) moveX = 0;
      if (Math.abs(moveY) < DEADZONE) moveY = 0;
      if (Math.abs(turnX) < DEADZONE) turnX = 0;
      if (Math.abs(turnY) < DEADZONE) turnY = 0;

      // ── Movement (left stick) — 6DOF flight along view direction ────
      if (moveX !== 0 || moveY !== 0) {
        const forward = new THREE.Vector3(0, 0, -1).applyQuaternion(camera.quaternion).normalize();
        const right = new THREE.Vector3(1, 0, 0).applyQuaternion(camera.quaternion).normalize();

        const delta = new THREE.Vector3();
        delta.add(right.clone().multiplyScalar(moveX * VR_MOVE_SPEED));
        delta.add(forward.clone().multiplyScalar(-moveY * VR_MOVE_SPEED));

        rig.position.add(delta);
      }

      // ── Turning (right stick X) — rotate rig around Y axis ──────────
      if (turnX !== 0) {
        rig.rotation.y -= turnX * VR_TURN_SPEED;
      }

      // ── Vertical (right stick Y) — move rig up/down ────────────────
      if (turnY !== 0) {
        rig.position.y -= turnY * VR_MOVE_SPEED;
      }
    }
  }, [viewerRef]);

  // ── Enter XR session (shared logic for VR and AR) ───────────────────
  const enterSession = useCallback(async (mode: XRMode) => {
    const ctx = viewerRef.current;
    if (!ctx) {
      console.warn('[XR] Viewer not ready');
      return;
    }

    if (sessionRef.current) {
      console.warn('[XR] Session already active');
      return;
    }

    const { renderer, scene, camera, controls } = ctx;

    try {
      if (!navigator.xr) {
        console.warn('[XR] WebXR not available');
        return;
      }

      const sessionType = mode === 'ar' ? 'immersive-ar' : 'immersive-vr';
      console.log(`[XR] Entering ${mode.toUpperCase()} session...`);

      renderer.xr.enabled = true;

      // ── Freeze Spark's deferred GPU-readback sort during XR ─────────
      // SparkRenderer.autoUpdate=true triggers a setTimeout(1ms) sort pipeline
      // that runs OUTSIDE the XR frame callback. The async GPU readback in that
      // pipeline can produce corrupted sort data (activeSplats=0) when the GL
      // context is in XR compositor state, causing the model to vanish after
      // the first sort completes (~2-3 s). Disabling autoUpdate keeps the
      // pre-XR sort order frozen — minor alpha-blend artifacts but stable.
      ctx.sparkRenderer.autoUpdate = false;

      // Use native headset resolution — avoids rendering at desktop DPR which
      // causes severe frame drops and possible session termination.
      renderer.setPixelRatio(1);

      // ── AR-specific: save background, make scene transparent ────────
      if (mode === 'ar') {
        savedBackgroundRef.current = scene.background;
        scene.background = null;
        renderer.setClearColor(0x000000, 0);
      }

      const optionalFeatures = mode === 'ar'
        ? ['local-floor', 'hand-tracking']
        : ['local-floor', 'bounded-floor', 'hand-tracking'];

      const session = await navigator.xr.requestSession(sessionType, {
        optionalFeatures,
      });

      sessionRef.current = session;

      // Disable OrbitControls during XR (headset handles orientation)
      controls.enabled = false;

      // Create camera rig and parent the camera under it
      const rig = new THREE.Group();
      rig.name = 'xr-camera-rig';
      scene.add(rig);

      // Detach camera from scene root and attach to rig
      scene.remove(camera);
      rig.add(camera);
      rigRef.current = rig;

      await renderer.xr.setSession(session);

      // ── Height calibration: position rig so model appears at eye level ─
      // In local-floor reference, XR camera starts at head height (~1.6m).
      // Model is at origin (0,0,0). Without adjustment, it appears at foot level.
      // Fix: once head height is known, offset rig Y so origin = eye level,
      // and step rig back on Z to match the default camera distance.
      let heightCalibrated = false;

      // ── Mobile AR touch: orbit the RIG via touch drag ───────────────
      // On mobile AR (no controllers), let user drag to orbit around model
      // and pinch to scale. These listeners are on the canvas.
      if (mode === 'ar') {
        const canvas = renderer.domElement;
        let prevTouchX = 0;
        let prevTouchY = 0;
        let prevPinchDist = 0;
        let activeTouchId: number | null = null;

        const onTouchStart = (e: TouchEvent) => {
          if (e.touches.length === 1) {
            activeTouchId = e.touches[0].identifier;
            prevTouchX = e.touches[0].clientX;
            prevTouchY = e.touches[0].clientY;
          } else if (e.touches.length === 2) {
            activeTouchId = null;
            const dx = e.touches[1].clientX - e.touches[0].clientX;
            const dy = e.touches[1].clientY - e.touches[0].clientY;
            prevPinchDist = Math.sqrt(dx * dx + dy * dy);
          }
        };

        const onTouchMove = (e: TouchEvent) => {
          e.preventDefault();
          const currentRig = rigRef.current;
          if (!currentRig) return;

          if (e.touches.length === 1 && activeTouchId !== null) {
            // Single finger: orbit rig around origin (Y-axis rotation + X tilt)
            const touch = e.touches[0];
            const dx = touch.clientX - prevTouchX;
            const dy = touch.clientY - prevTouchY;
            prevTouchX = touch.clientX;
            prevTouchY = touch.clientY;

            // Rotate rig around Y axis (horizontal drag = orbit)
            currentRig.rotation.y += dx * AR_TOUCH_ROTATE_SPEED;
            // Move rig up/down (vertical drag = vertical offset)
            currentRig.position.y -= dy * AR_TOUCH_ROTATE_SPEED * 0.5;
          } else if (e.touches.length === 2) {
            // Pinch: scale the splat mesh
            const dx = e.touches[1].clientX - e.touches[0].clientX;
            const dy = e.touches[1].clientY - e.touches[0].clientY;
            const dist = Math.sqrt(dx * dx + dy * dy);

            if (prevPinchDist > 0) {
              const scale = 1 + (dist - prevPinchDist) * AR_TOUCH_PINCH_SPEED;
              const splatMesh = ctx.splatMesh;
              if (splatMesh) {
                const newScale = Math.max(0.2, Math.min(10, splatMesh.scale.x * scale));
                splatMesh.scale.setScalar(newScale);
              }
            }
            prevPinchDist = dist;
            activeTouchId = null;
          }
        };

        const onTouchEnd = (e: TouchEvent) => {
          if (e.touches.length === 0) {
            activeTouchId = null;
            prevPinchDist = 0;
          } else if (e.touches.length === 1) {
            activeTouchId = e.touches[0].identifier;
            prevTouchX = e.touches[0].clientX;
            prevTouchY = e.touches[0].clientY;
            prevPinchDist = 0;
          }
        };

        canvas.addEventListener('touchstart', onTouchStart, { passive: false });
        canvas.addEventListener('touchmove', onTouchMove, { passive: false });
        canvas.addEventListener('touchend', onTouchEnd, { passive: false });
        canvas.addEventListener('touchcancel', onTouchEnd, { passive: false });

        arTouchCleanupRef.current = () => {
          canvas.removeEventListener('touchstart', onTouchStart);
          canvas.removeEventListener('touchmove', onTouchMove);
          canvas.removeEventListener('touchend', onTouchEnd);
          canvas.removeEventListener('touchcancel', onTouchEnd);
        };
      }

      // Switch to XR animation loop
      renderer.setAnimationLoop(() => {
        if (!heightCalibrated) {
          const xrCam = renderer.xr.getCamera();
          if (xrCam && xrCam.position.y > 0) {
            // Offset rig so model at origin appears at eye level
            rig.position.y = -xrCam.position.y;
            // Step back 0.3m — model appears close and fills view naturally
            rig.position.z = 0;
            // Save as home position so reset returns here
            rigHomeRef.current = { y: rig.position.y, z: rig.position.z };
            heightCalibrated = true;
            console.log(`[XR] Height calibrated: rig.y = ${rig.position.y.toFixed(2)}m, rig.z = ${rig.position.z.toFixed(2)}m`);
          }
        }

        processControllerInput(session, rig);
        renderer.render(scene, camera);
      });

      setIsInXR(true);
      setCurrentMode(mode);

      console.log(`[XR] ✅ ${mode.toUpperCase()} session started`);
      if (mode === 'ar') {
        console.log('[XR] AR Passthrough active — scene overlays on real world');
      }
      console.log('[XR] Controls:');
      console.log('  - Left stick: Move in view direction (6DOF flight)');
      console.log('  - Right stick X: Turn left/right');
      console.log('  - Right stick Y: Move up/down');
      console.log('  - A/X button: Reset position');
      console.log('  - Head movement: Look around');

      // Listen for session end (user presses Oculus button, etc.)
      session.addEventListener('end', () => {
        console.log(`[XR] ${mode.toUpperCase()} session ended`);

        // Stop XR animation loop
        renderer.setAnimationLoop(null);
        renderer.xr.enabled = false;

        // Cleanup mobile AR touch listeners
        if (arTouchCleanupRef.current) {
          arTouchCleanupRef.current();
          arTouchCleanupRef.current = null;
        }

        // Remove rig: detach camera back to scene root, then dispose rig
        const currentRig = rigRef.current;
        if (currentRig) {
          currentRig.remove(camera);
          scene.add(camera);
          scene.remove(currentRig);
          rigRef.current = null;
        }

        // ── AR-specific: restore scene background & model scale ──────
        if (mode === 'ar') {
          scene.background = savedBackgroundRef.current;
          savedBackgroundRef.current = null;
          // Restore splatMesh scale in case pinch zoom changed it
          if (ctx.splatMesh) {
            ctx.splatMesh.scale.setScalar(DEFAULT_CAMERA_CONFIG.modelScale);
          }
        }

        // ── Re-enable Spark's auto-update & sort pipeline ──────────
        ctx.sparkRenderer.autoUpdate = true;

        // ── Fully restore camera & renderer to pre-XR state ───────────
        camera.position.set(...DEFAULT_CAMERA_CONFIG.initialPosition);
        camera.up.set(...DEFAULT_CAMERA_CONFIG.cameraUp);
        camera.rotation.set(0, 0, 0);
        camera.fov = DEFAULT_CAMERA_CONFIG.fov;
        camera.near = DEFAULT_CAMERA_CONFIG.near;
        camera.far = DEFAULT_CAMERA_CONFIG.far;

        // Restore viewport size and pixel ratio — respect High Fidelity setting
        const container = renderer.domElement.parentElement;
        if (container) {
          const w = container.clientWidth;
          const h = container.clientHeight;
          camera.aspect = w / h;
          renderer.setSize(w, h);
        }
        const { isHighFidelity } = useAppStore.getState();
        renderer.setPixelRatio(isHighFidelity ? window.devicePixelRatio : Math.min(window.devicePixelRatio, 2));
        camera.updateProjectionMatrix();

        // Reset OrbitControls — orbit around origin with default state
        controls.target.set(0, 0, 0);
        controls.enabled = true;
        controls.update();

        // Restart normal render loop
        renderer.setAnimationLoop(() => {
          controls.update();
          renderer.render(scene, camera);
        });

        sessionRef.current = null;
        setIsInXR(false);
        setCurrentMode(null);
      });
    } catch (e) {
      console.error(`[XR] ${mode.toUpperCase()} session error:`, e);
      // Restore AR background on error
      if (mode === 'ar' && savedBackgroundRef.current !== null) {
        scene.background = savedBackgroundRef.current;
        savedBackgroundRef.current = null;
      }
      sessionRef.current = null;
      setIsInXR(false);
      setCurrentMode(null);
    }
  }, [viewerRef, processControllerInput]);

  // ── Public methods ──────────────────────────────────────────────────
  const enterVR = useCallback(() => enterSession('vr'), [enterSession]);
  const enterAR = useCallback(() => enterSession('ar'), [enterSession]);

  const exitXR = useCallback(async () => {
    if (sessionRef.current) {
      console.log('[XR] Exiting session...');
      await sessionRef.current.end();
    }
  }, []);

  // ── Cleanup on unmount ──────────────────────────────────────────────
  useEffect(() => {
    return () => {
      if (sessionRef.current) {
        sessionRef.current.end().catch(() => {});
      }
    };
  }, []);

  return {
    isVRSupported,
    isARSupported,
    isInXR,
    currentMode,
    enterVR,
    enterAR,
    exitXR,
    isCheckingSupport,
  };
};
