import * as THREE from 'three';

// Camera configuration
export interface CameraConfig {
  // Initial position
  initialPosition: [number, number, number];
  cameraUp: [number, number, number];

  // Mouse button mapping
  mouseButtons: {
    LEFT: 'ROTATE' | 'PAN' | 'DOLLY';
    MIDDLE: 'ROTATE' | 'PAN' | 'DOLLY';
    RIGHT: 'ROTATE' | 'PAN' | 'DOLLY';
  };

  // Speed settings
  rotateSpeed: number;
  panSpeed: number;
  zoomSpeed: number;
  keyPanSpeed: number;

  // Shift accelerated mode
  acceleratedZoomSpeed: number;
  acceleratedMoveSpeed: number;

  // Alt precision mode
  precisionZoomSpeed: number;
  precisionMoveSpeed: number;

  // Keyboard move speed
  keyboardMoveSpeed: number;

  // Distance limits
  minDistance: number;
  maxDistance: number;

  // Angle limits (Front View mode)
  limits: {
    minAzimuth: number;
    maxAzimuth: number;
    minPolar: number;
    maxPolar: number;
    minDist: number;
    maxDist: number;
  };

  // Free mode
  freeMode: {
    minAzimuth: number;
    maxAzimuth: number;
    minPolar: number;
    maxPolar: number;
    minDist: number;
    maxDist: number;
  };

  // Animation
  resetAnimationDuration: number;

  // Damping
  enableDamping: boolean;
  dampingFactor: number;

  // Auto rotate
  autoRotate: boolean;
  autoRotateSpeed: number;

  // Touch
  touches: {
    ONE: 'ROTATE' | 'PAN' | 'DOLLY_PAN' | 'DOLLY_ROTATE';
    TWO: 'DOLLY_PAN' | 'DOLLY_ROTATE' | 'PAN' | 'ROTATE';
  };

  // Camera
  fov: number;
  near: number;
  far: number;

  // Model
  modelScale: [number, number, number];
  modelRotation: [number, number, number, number];
}

// Helper to get THREE.MOUSE constant
export function getMouseButton(name: 'ROTATE' | 'PAN' | 'DOLLY'): THREE.MOUSE {
  const map: Record<string, THREE.MOUSE> = {
    ROTATE: THREE.MOUSE.ROTATE,
    PAN: THREE.MOUSE.PAN,
    DOLLY: THREE.MOUSE.DOLLY,
  };
  return map[name] ?? THREE.MOUSE.ROTATE;
}

// Helper to get THREE.TOUCH constant
export function getTouchType(
  name: 'ROTATE' | 'PAN' | 'DOLLY_PAN' | 'DOLLY_ROTATE'
): THREE.TOUCH {
  const map: Record<string, THREE.TOUCH> = {
    ROTATE: THREE.TOUCH.ROTATE,
    PAN: THREE.TOUCH.PAN,
    DOLLY_PAN: THREE.TOUCH.DOLLY_PAN,
    DOLLY_ROTATE: THREE.TOUCH.DOLLY_ROTATE,
  };
  return map[name] ?? THREE.TOUCH.ROTATE;
}
