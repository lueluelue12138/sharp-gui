import type { CameraConfig } from '@/types';

/**
 * Default camera configuration
 * Migrated from original index.html CAMERA_CONFIG
 */
export const DEFAULT_CAMERA_CONFIG: CameraConfig = {
  // Initial position
  initialPosition: [0, 0, 1],
  cameraUp: [0, -1, 0], // Y-axis down (Gaussian Splats convention)

  // Mouse button mapping
  mouseButtons: {
    LEFT: 'ROTATE',
    MIDDLE: 'DOLLY',
    RIGHT: 'PAN',
  },

  // Speed settings
  rotateSpeed: 1.0,
  panSpeed: 1.0,
  zoomSpeed: 1.0,
  keyPanSpeed: 10.0,

  // Shift accelerated mode
  acceleratedZoomSpeed: 3.0,
  acceleratedMoveSpeed: 0.15,

  // Alt precision mode
  precisionZoomSpeed: 0.3,
  precisionMoveSpeed: 0.01,

  // Keyboard move speed
  keyboardMoveSpeed: 0.05,

  // Distance limits
  minDistance: 0.3,
  maxDistance: 10.0,

  // Angle limits (Front View mode)
  limits: {
    minAzimuth: -Math.PI / 4,  // -45°
    maxAzimuth: Math.PI / 4,   // +45°
    minPolar: Math.PI / 3,     // 60°
    maxPolar: (2 * Math.PI) / 3, // 120°
    minDist: 0.1,
    maxDist: 20,
  },

  // Free mode
  freeMode: {
    minAzimuth: -Infinity,
    maxAzimuth: Infinity,
    minPolar: 0,
    maxPolar: Math.PI,
    minDist: 0.1,
    maxDist: 20,
  },

  // Animation
  resetAnimationDuration: 800,

  // Damping
  enableDamping: true,
  dampingFactor: 0.05,

  // Auto rotate
  autoRotate: false,
  autoRotateSpeed: 2.0,

  // Touch
  touches: {
    ONE: 'ROTATE',
    TWO: 'DOLLY_PAN',
  },

  // Camera
  fov: 50,
  near: 0.01,
  far: 1000,

  // Model
  modelScale: [2.0, 2.0, 2.0],
  modelRotation: [0, 1, 0, 0],
};
