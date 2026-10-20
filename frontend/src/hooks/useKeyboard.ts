import { useEffect, useRef, useCallback, useState } from 'react';
import * as THREE from 'three';
import { useAppStore } from '@/store';
import { DEFAULT_CAMERA_CONFIG } from '@/utils/camera';

export type SpeedMode = 'fast' | 'precision' | null;

interface KeyState {
  w: boolean;
  a: boolean;
  s: boolean;
  d: boolean;
  q: boolean;
  e: boolean;
  shift: boolean;
  ctrl: boolean;
  [key: string]: boolean;
}

interface KeyboardViewerControls {
  enabled?: boolean;
  target?: THREE.Vector3;
  update?: () => void;
  zoomSpeed: number;
}

interface KeyboardViewerRuntime {
  camera?: THREE.Camera;
  controls?: KeyboardViewerControls;
}

export const useKeyboard = (
  viewerRef: React.MutableRefObject<KeyboardViewerRuntime | null>,
  resetCameraFn?: () => void,
) => {
  const keyState = useRef<KeyState>({
    w: false, a: false, s: false, d: false, q: false, e: false,
    shift: false, ctrl: false
  });
  
  const animationFrameId = useRef<number | null>(null);
  const [speedMode, setSpeedMode] = useState<SpeedMode>(null);
  const resetCameraRef = useRef(resetCameraFn);

  // Keep resetCameraRef up to date
  useEffect(() => {
    resetCameraRef.current = resetCameraFn;
  }, [resetCameraFn]);

  const updateMovementRef = useRef<() => void>(undefined);

  const updateMovement = useCallback(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;

    const camera = viewer.camera;
    const controls = viewer.controls;
    
    if (!camera || !controls || controls.enabled === false) {
      animationFrameId.current = null;
      Object.keys(keyState.current).forEach(key => { keyState.current[key] = false; });
      return;
    }

    const keys = keyState.current;
    const hasMovement = keys.w || keys.a || keys.s || keys.d || keys.q || keys.e;

    if (hasMovement) {
      let speed = DEFAULT_CAMERA_CONFIG.keyboardMoveSpeed;
      if (keys.shift) {
        speed = DEFAULT_CAMERA_CONFIG.acceleratedMoveSpeed;
      } else if (keys.ctrl) {
        speed = DEFAULT_CAMERA_CONFIG.precisionMoveSpeed;
      }

      // Forward direction
      const forward = new THREE.Vector3();
      camera.getWorldDirection(forward);

      // Right direction
      const right = new THREE.Vector3();
      right.crossVectors(forward, camera.up).normalize();

      // Up direction (relative to camera view)
      const up = new THREE.Vector3();
      up.crossVectors(right, forward).normalize();

      const delta = new THREE.Vector3();

      if (keys.w) delta.add(forward.clone().multiplyScalar(speed));
      if (keys.s) delta.add(forward.clone().multiplyScalar(-speed));
      if (keys.a) delta.add(right.clone().multiplyScalar(-speed));
      if (keys.d) delta.add(right.clone().multiplyScalar(speed));
      if (keys.q) delta.add(up.clone().multiplyScalar(-speed));
      if (keys.e) delta.add(up.clone().multiplyScalar(speed));

      camera.position.add(delta);
      if (controls.target) {
        controls.target.add(delta);
      }

      if (controls.update) controls.update();

      if (updateMovementRef.current) {
          animationFrameId.current = requestAnimationFrame(updateMovementRef.current);
      }
    } else {
      animationFrameId.current = null;
    }
  }, [viewerRef]);

  // Keep ref updated
  useEffect(() => {
      updateMovementRef.current = updateMovement;
  }, [updateMovement]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const key = e.key.toLowerCase();
      
      // Prevent handling if typing in input
      if (e.target instanceof HTMLElement && e.target.closest('input, textarea, select, [contenteditable="true"]')) return;
      if (viewerRef.current?.controls?.enabled === false) return;

      if (['w', 'a', 's', 'd', 'q', 'e'].includes(key)) {
        // e.preventDefault(); // Optional: prevent scrolling if any
        keyState.current[key] = true;
        
        if (!animationFrameId.current && viewerRef.current) {
          animationFrameId.current = requestAnimationFrame(updateMovement);
        }
      }

      // R key → Reset camera (same as the Reset button)
      if (key === 'r') {
        e.preventDefault();
        resetCameraRef.current?.();
      }

      if (e.key === 'Shift') {
        keyState.current.shift = true;
        setSpeedMode('fast');
        updateZoomSpeed(true, false);
      }
      if (e.key === 'Alt') {
        keyState.current.ctrl = true;
        setSpeedMode('precision');
        updateZoomSpeed(false, true);
      }
    };

    const handleKeyUp = (e: KeyboardEvent) => {
      const key = e.key.toLowerCase();
      
      if (['w', 'a', 's', 'd', 'q', 'e'].includes(key)) {
        keyState.current[key] = false;
      }

      if (e.key === 'Shift') {
        keyState.current.shift = false;
        // If Alt is still held, switch to precision mode; otherwise hide
        if (keyState.current.ctrl) {
          setSpeedMode('precision');
        } else {
          setSpeedMode(null);
        }
        updateZoomSpeed(false, keyState.current.ctrl);
      }
      if (e.key === 'Alt') {
        keyState.current.ctrl = false;
        // If Shift is still held, switch to fast mode; otherwise hide
        if (keyState.current.shift) {
          setSpeedMode('fast');
        } else {
          setSpeedMode(null);
        }
        updateZoomSpeed(keyState.current.shift, false);
      }
    };

    const handleBlur = () => {
      Object.keys(keyState.current).forEach(k => keyState.current[k] = false);
      setSpeedMode(null);
      if (animationFrameId.current) {
        cancelAnimationFrame(animationFrameId.current);
        animationFrameId.current = null;
      }
    };

    const updateZoomSpeed = (shift: boolean, ctrl: boolean) => {
       const viewer = viewerRef.current;
       if (!viewer) return;
       const controls = viewer.controls;
       if (!controls) return;

       const reverseZoom = useAppStore.getState().viewerInteractionApplied.reversePointerDirection
         ? -1
         : 1;

       let baseZoomSpeed = DEFAULT_CAMERA_CONFIG.zoomSpeed;

       if (shift) {
         baseZoomSpeed = DEFAULT_CAMERA_CONFIG.acceleratedZoomSpeed;
       } else if (ctrl) {
         baseZoomSpeed = DEFAULT_CAMERA_CONFIG.precisionZoomSpeed;
       }

       controls.zoomSpeed = baseZoomSpeed * reverseZoom;
    };

    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keyup', handleKeyUp);
    window.addEventListener('blur', handleBlur);

    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('keyup', handleKeyUp);
      window.removeEventListener('blur', handleBlur);
      if (animationFrameId.current) {
        cancelAnimationFrame(animationFrameId.current);
      }
    };
  }, [viewerRef, updateMovement]);

  return { speedMode };
};
