import { useEffect, useRef, useCallback, useState } from 'react';
import * as THREE from 'three';
import { Viewer } from '@mkkellogg/gaussian-splats-3d';
import { useAppStore } from '@/store/useAppStore';
import { DEFAULT_CAMERA_CONFIG } from '@/utils/camera';
import { useKeyboard } from './useKeyboard';
import { useGyroscope } from './useGyroscope';
import { useJoystick } from './useJoystick';
import { useVR } from './useVR';

export const useViewer = (containerRef: React.RefObject<HTMLDivElement | null>) => {
  const viewerRef = useRef<any>(null);
  const { 
    currentModelUrl,
    currentModelFormat,
    setLoading, 
    setLoadingProgress, 
    isLimitsOn,
  } = useAppStore();
  const [isViewerReady, setIsViewerReady] = useState(false);

  // Hooks
  const { speedMode } = useKeyboard(viewerRef);
  const { handleToggle: toggleGyro, isSupported: isGyroSupported, indicatorBallRef } = useGyroscope({ viewerRef });
  const joystick = useJoystick({ viewerRef });
  const vr = useVR({ viewerRef });

  // Initialize Viewer
  useEffect(() => {
    if (!containerRef.current || viewerRef.current) return;

    const init = async () => {
      try {
        const viewer = new Viewer({
          cameraUp: DEFAULT_CAMERA_CONFIG.cameraUp,
          initialCameraPosition: DEFAULT_CAMERA_CONFIG.initialPosition,
          rootElement: containerRef.current!,
          gpuAcceleratedSort: false,
          sharedMemoryForWorkers: false,
          useBuiltInControls: true,
          selfDrivenMode: true,
        });

        viewerRef.current = viewer;
        applyCameraSettings(viewer);
        setIsViewerReady(true);
        
      } catch (error) {
        console.error("Failed to initialize viewer:", error);
      }
    };

    init();


    // Resize handler
    const handleResize = () => {
        if (viewerRef.current) {
            requestAnimationFrame(() => {
                // viewer.resize() does not exist in this version.
                // The library likely handles window resize in selfDrivenMode, 
                // or we need to update renderer/camera manually if container changes size.
                // For now, ensuring controls are updated is a safe minimal step.
                const c = viewerRef.current.cameraControls || viewerRef.current.controls;
                if (c) c.update();
            });
        }
    };
    window.addEventListener('resize', handleResize);
    document.addEventListener('fullscreenchange', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      document.removeEventListener('fullscreenchange', handleResize);
      if (viewerRef.current) {
        try {
          viewerRef.current.dispose();
        } catch {
          // Ignore dispose errors
        }
        viewerRef.current = null;
        setIsViewerReady(false);
      }
    };
  }, [containerRef]);

  // Apply Camera Settings
  const applyCameraSettings = useCallback((viewer: any) => {
    if (!viewer) return;

    // We need to wait a bit for controls to be initialized sometimes, 
    // but typically they are available after constructor.
    // However, original code used setTimeout(100).
    setTimeout(() => {
      const c = viewer.cameraControls || viewer.controls;
      if (!c) return;

      // Mouse Buttons
      if (c.mouseButtons) {
        // Map string 'ROTATE', 'PAN', etc to Three.js constants if needed
        // But the library likely expects its own constants or Three.js ones.
        // For now, let's assume the library handles simple strings or we map them.
        // Checking original code: getMouseButton helper mapped strings to THREE.MOUSE.LEFT etc.
        c.mouseButtons.LEFT = THREE.MOUSE.LEFT;
        c.mouseButtons.MIDDLE = THREE.MOUSE.MIDDLE;
        c.mouseButtons.RIGHT = THREE.MOUSE.RIGHT;
      }

      // Touches
      if (c.touches) {
        c.touches.ONE = THREE.TOUCH.ROTATE;
        c.touches.TWO = THREE.TOUCH.DOLLY_PAN;
      }

      // Speed
      c.rotateSpeed = DEFAULT_CAMERA_CONFIG.rotateSpeed;
      c.panSpeed = DEFAULT_CAMERA_CONFIG.panSpeed;
      c.zoomSpeed = DEFAULT_CAMERA_CONFIG.zoomSpeed;
      if (c.keyPanSpeed !== undefined) c.keyPanSpeed = DEFAULT_CAMERA_CONFIG.keyPanSpeed;

      // Damping
      c.enableDamping = DEFAULT_CAMERA_CONFIG.enableDamping;
      c.dampingFactor = DEFAULT_CAMERA_CONFIG.dampingFactor;

      // Auto Rotate
      c.autoRotate = DEFAULT_CAMERA_CONFIG.autoRotate;
      c.autoRotateSpeed = DEFAULT_CAMERA_CONFIG.autoRotateSpeed;
      
      
      // Disable built-in keys if we want custom WASD
      if (c.enableKeys !== undefined) c.enableKeys = false;
      if (c.keys) c.keys = { LEFT: "", UP: "", RIGHT: "", BOTTOM: "" };
      
      // Safely disable key listening if supported
      if (typeof c.listenToKeyEvents === 'function') {
        try {
            // Some controls might throw if null is passed or if already disposed
            c.listenToKeyEvents(window); // Bind to window instead of null if we want to ensure it works, or just ignore.
            // Actually, if we want to DISABLE built-in keys, we usually do enableKeys = false.
            // If we pass null, it stops listening.
            c.listenToKeyEvents(null); 
        } catch (e) {
            // Ignore errors during key event listener removal
        }
      }

      c.minDistance = DEFAULT_CAMERA_CONFIG.minDistance;
      c.maxDistance = DEFAULT_CAMERA_CONFIG.maxDistance;

      c.update();
    }, 100);
  }, []);

  // Load Model
  useEffect(() => {
    if (!viewerRef.current || !currentModelUrl) return;

    const load = async () => {
      const viewer = viewerRef.current;
      // Use static text to avoid t() causing re-render loop
      setLoading(true, 'Loading Scene...');
      setLoadingProgress(0);

      try {
        // Clear previous scenes
        if (viewer.getSplatSceneCount && viewer.getSplatSceneCount() > 0) {
           // Some versions have removeSplatScene or clear
           // If simplistic, dispose and recreate might be safer as per original code
        }
        
        // Per original code: dispose and recreate viewer to avoid overlap issues
        // But React useEffect cleanup handles dispose. 
        // We might just need to recreate the viewer instance if the URL changes?
        // Or finding a way to clear. 
        // Let's try sticking to "one viewer instance" but effectively clearing it.
        // Actually original code said: "修复：回退到销毁重建模式，解决模型重叠问题"
        // So maybe we should reconstruct viewer when URL changes.
        // But useEffect dependency on `currentModelUrl` would trigger cleanup (dispose) and re-init if we put `currentModelUrl` in the init effect.
        
        // However, `init` effect currently only depends on `containerRef`.
        // Let's keep `init` separate and assume we can clear or we just rely on unmount/remount if we change key of component.
        // But `App.tsx` likely keeps `ViewerCanvas` mounted.
        
        // Let's implement the "Dispose and Recreate" strategy inside the load effect effectively
        // OR better: make ViewerCanvas accept `url` as key to force remount?
        // That's a valid React pattern. <ViewerCanvas key={url} />
        // Let's assume the parent does that OR we handle it here.
        
        // If we want to use `addSplatScene`, we should try to remove old ones.
        // Viewer has `removeSplatScene(index)`.
        
        // For now, let's just add. If we need to clear, we might need a reference to the scene index.
        // Pass format parameter for blob URLs (viewer can't detect format from blob URL)
        const sceneOptions: Record<string, unknown> = {
          showLoadingUI: false,
          position: [0, 0, 0],
          rotation: [0, 1, 0, 0],
          scale: DEFAULT_CAMERA_CONFIG.modelScale,
          onProgress: (percent: number) => {
             setLoadingProgress(percent);
          }
        };
        
        // Add format hint if available (needed for blob URLs)
        // SceneFormat enum: Splat=0, KSplat=1, Ply=2, Spz=3
        if (currentModelFormat) {
          sceneOptions.format = currentModelFormat === 'ply' ? 2 : 0;
        }
        
        await viewer.addSplatScene(currentModelUrl, sceneOptions);

        setLoading(false);
        viewer.start();
        
        // Apply limits and initial camera
        applyLimits();
        resetCamera();

      } catch (error) {
        console.error("Error loading model:", error);
        setLoading(false); // TODO: Set error state
      }
    };

    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentModelUrl, currentModelFormat]); // Include format to ensure it's available when loading
  // Note: We might want to "reload" viewer if URL changes. 
  // If we follow the "recreate viewer" strategy, we should probably do that by changing the key in the parent.

  // Apply Limits
  const applyLimits = useCallback(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;
    
    setTimeout(() => {
      const c = viewer.cameraControls || viewer.controls;
      if (!c) return;

      const config = isLimitsOn ? DEFAULT_CAMERA_CONFIG.limits : DEFAULT_CAMERA_CONFIG.freeMode;
      
      c.minAzimuthAngle = config.minAzimuth;
      c.maxAzimuthAngle = config.maxAzimuth;
      c.minPolarAngle = config.minPolar;
      c.maxPolarAngle = config.maxPolar;
      
      // Update camera metrics if needed
      c.update();
    }, 50);
  }, [isLimitsOn]);

  useEffect(() => {
    applyLimits();
  }, [isLimitsOn, applyLimits]);

  // Reset Camera
  const resetCamera = useCallback(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;

    const c = viewer.cameraControls || viewer.controls;
    if (!c) return;

    // Default target values
    const targetPos = new THREE.Vector3(...DEFAULT_CAMERA_CONFIG.initialPosition);
    const targetLookAt = new THREE.Vector3(0, 0, 0);
    const targetUp = new THREE.Vector3(...DEFAULT_CAMERA_CONFIG.cameraUp);

    // Current values
    const startPos = c.object.position.clone();
    const startLookAt = c.target.clone();
    const startUp = c.object.up.clone();

    const startTime = performance.now();
    const duration = DEFAULT_CAMERA_CONFIG.resetAnimationDuration;

    function animate() {
      const now = performance.now();
      const progress = Math.min((now - startTime) / duration, 1);
      
      // Easing: Cubic ease out
      // t => 1 - Math.pow(1 - t, 3)
      const ease = 1 - Math.pow(1 - progress, 3);

      // Interpolate
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

  return {
    viewerRef,
    isViewerReady,
    speedMode,
    resetCamera,
    toggleGyro,
    isGyroSupported,
    indicatorBallRef,
    joystick,
    vr
  };
};
