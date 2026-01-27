import { useEffect, useRef, useState, useCallback } from 'react';
import { useAppStore } from '@/store/useAppStore';

interface UseGyroscopeProps {
    viewerRef: React.MutableRefObject<any>;
}

export const useGyroscope = ({ viewerRef }: UseGyroscopeProps) => {
    const { isGyroEnabled, toggleGyro } = useAppStore();
    const [isSupported, setIsSupported] = useState(false);
    
    // UI Refs
    const indicatorBallRef = useRef<HTMLDivElement>(null);
    
    // Logic Refs
    const gyroState = useRef({
        alpha: 0,
        beta: 0,
        gamma: 0,
        targetAzimuth: 0,
        targetPolar: Math.PI / 2,
        smoothAzimuth: 0,
        smoothPolar: Math.PI / 2,
        refBeta: 0,
        refGamma: 0,
        needsCalibration: true,
    });

    const animationRef = useRef<number | null>(null);

    // Configuration
    const CONFIG = {
        dampingFactor: 0.08,
        maxTiltAngle: 35,
        sensitivity: 1.0,
    };

    // Check support
    useEffect(() => {
        if (typeof window !== 'undefined' && 'DeviceOrientationEvent' in window) {
            setIsSupported(true);
        }
    }, []);

    // Request Permission (iOS 13+)
    const requestPermission = async () => {
        if (typeof (DeviceOrientationEvent as any).requestPermission === 'function') {
            try {
                const permission = await (DeviceOrientationEvent as any).requestPermission();
                return permission === 'granted';
            } catch (e) {
                console.error('Gyroscope permission error:', e);
                return false;
            }
        }
        return true;
    };

    // Handle Toggle
    const handleToggle = async () => {
        if (!isGyroEnabled) {
            // Turning ON
            const granted = await requestPermission();
            if (granted) {
                toggleGyro(); // Set store state to true
                gyroState.current.needsCalibration = true;
            } else {
                alert("Permission denied or not supported");
            }
        } else {
            // Turning OFF
            toggleGyro();
        }
    };

    // Event Handler
    const handleOrientation = useCallback((event: DeviceOrientationEvent) => {
        if (!isGyroEnabled) return;

        const state = gyroState.current;
        state.alpha = event.alpha || 0;
        state.beta = event.beta || 0;
        state.gamma = event.gamma || 0;

        const maxTilt = CONFIG.maxTiltAngle;

        // Calibration
        if (state.needsCalibration) {
            state.refBeta = state.beta;
            state.refGamma = state.gamma;
            state.needsCalibration = false;
        }

        // Normalize
        let normalizedBeta = state.beta - state.refBeta;
        normalizedBeta = Math.max(-maxTilt, Math.min(maxTilt, normalizedBeta));

        let normalizedGamma = state.gamma - state.refGamma;
        normalizedGamma = Math.max(-maxTilt, Math.min(maxTilt, normalizedGamma));

        // Map to camera angles
        // Azimuth: ±45 deg
        // Polar: 60 - 120 deg
        state.targetAzimuth = (normalizedGamma / maxTilt) * (Math.PI / 4) * CONFIG.sensitivity;
        state.targetPolar = Math.PI / 2 + (normalizedBeta / maxTilt) * (Math.PI / 6) * CONFIG.sensitivity;
    }, [isGyroEnabled]);

    // Render Loop
    useEffect(() => {
        if (!isGyroEnabled || !viewerRef.current) {
            if (animationRef.current) {
                cancelAnimationFrame(animationRef.current);
                animationRef.current = null;
            }
            return;
        }

        const animate = () => {
            const viewer = viewerRef.current;
            const state = gyroState.current;
            
            // Allow controls to update first if needed, though we interrupt them essentially
            const c = viewer?.cameraControls || viewer?.controls;

            if (c && c.object) {
                // Smooth interpolation
                state.smoothAzimuth += (state.targetAzimuth - state.smoothAzimuth) * CONFIG.dampingFactor;
                state.smoothPolar += (state.targetPolar - state.smoothPolar) * CONFIG.dampingFactor;

                // Calculate position
                const distance = c.object.position.distanceTo(c.target);
                
                // Spherical to Cartesian relative to target
                const x = distance * Math.sin(state.smoothPolar) * Math.sin(state.smoothAzimuth);
                const y = distance * Math.cos(state.smoothPolar);
                const z = distance * Math.sin(state.smoothPolar) * Math.cos(state.smoothAzimuth);

                c.object.position.set(
                    c.target.x + x,
                    c.target.y + y,
                    c.target.z + z
                );
                c.object.lookAt(c.target);
                c.update();
            }
            
            // Update Indicator Ball
            if (indicatorBallRef.current) {
                const maxOffset = 18;
                const xOffset = (state.smoothAzimuth / (Math.PI / 4)) * maxOffset;
                const yOffset = ((state.smoothPolar - Math.PI / 2) / (Math.PI / 6)) * maxOffset;
                indicatorBallRef.current.style.transform = `translate(${xOffset}px, ${yOffset}px)`;
            }

            animationRef.current = requestAnimationFrame(animate);
        };

        // Bind event listener
        window.addEventListener('deviceorientation', handleOrientation);
        
        // Start loop
        animate();

        return () => {
            window.removeEventListener('deviceorientation', handleOrientation);
            if (animationRef.current) {
                cancelAnimationFrame(animationRef.current);
            }
        };
    }, [isGyroEnabled, handleOrientation, viewerRef]);

    return {
        isSupported,
        handleToggle,
        indicatorBallRef
    };
};
