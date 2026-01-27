import { useEffect, useRef, useState, useCallback } from 'react';
import * as THREE from 'three';

interface UseJoystickProps {
    viewerRef: React.MutableRefObject<any>;
}

export const useJoystick = ({ viewerRef }: UseJoystickProps) => {
    // We can store joystick enabled state in store if we want to toggle it globally
    // For now, let's keep it local or use a simple toggle since it's UI state.
    // However, the original code had a toggle button.
    const [isJoystickVisible, setIsJoystickVisible] = useState(false);
    const [isActive, setIsActive] = useState(false);

    const joystickState = useRef({
        centerX: 0,
        centerY: 0,
        deltaX: 0,
        deltaY: 0,
        maxRadius: 35, // Max movement radius
        moveSpeed: 0.03,
    });

    const animationRef = useRef<number | null>(null);
    const stickRef = useRef<HTMLDivElement>(null);
    const containerRef = useRef<HTMLDivElement>(null);

    const toggleJoystick = useCallback(() => {
        setIsJoystickVisible(prev => !prev);
    }, []);

    // Movement Loop
    const updateMovement = useCallback(() => {
        const viewer = viewerRef.current;
        if (!viewer || !isActive) { // Check isActive from state or ref? State might be stale in loop if not careful.
            // Actually, we should check a ref for active logic to avoid dependency issues in loop
            return; 
        }

        const camera = viewer.camera;
        const controls = viewer.cameraControls || viewer.controls;
        // controls can be null if not initialized
        if (!camera) return;

        const { deltaX, deltaY, maxRadius, moveSpeed } = joystickState.current;

        // Normalize -1 to 1
        const nx = deltaX / maxRadius;
        const ny = deltaY / maxRadius;

        if (Math.abs(nx) > 0.1 || Math.abs(ny) > 0.1) {
            // Get camera direction
            const forward = new THREE.Vector3();
            camera.getWorldDirection(forward);

            // Right vector
            const right = new THREE.Vector3();
            right.crossVectors(forward, camera.up).normalize();

            // Calculate delta
            const delta = new THREE.Vector3();
            
            // X: Left/Right (Strafe)
            delta.add(right.clone().multiplyScalar(nx * moveSpeed));
            
            // Y: Forward/Backward
            // ny is negative when dragging up. We want to move forward when dragging up.
            // So we subtract (or add negative) scaled vector.
            delta.add(forward.clone().multiplyScalar(-ny * moveSpeed));

            camera.position.add(delta);
            if (controls && controls.target) {
                controls.target.add(delta);
            }
            if (controls && controls.update) {
                controls.update();
            }
        }

        animationRef.current = requestAnimationFrame(updateMovement);
    }, [viewerRef, isActive]); // We need isActive here?

    // But if we put isActive in dependency, recreating the function might restart the loop unnecessarily?
    // Let's use a Ref for active status to be safe in the loop.
    const isActiveRef = useRef(false);

    useEffect(() => {
        isActiveRef.current = isActive;
        if (isActive) {
            animationRef.current = requestAnimationFrame(updateMovement);
        } else {
             if (animationRef.current) {
                 cancelAnimationFrame(animationRef.current);
                 animationRef.current = null;
             }
        }
    }, [isActive, updateMovement]);


    // Handlers
    const handleTouchStart = (e: React.TouchEvent) => {
        e.preventDefault(); // Prevent scrolling
        if (!containerRef.current) return;
        
        const rect = containerRef.current.getBoundingClientRect();
        joystickState.current.centerX = rect.left + rect.width / 2;
        joystickState.current.centerY = rect.top + rect.height / 2;
        
        setIsActive(true);
    };

    const handleTouchMove = (e: React.TouchEvent) => {
        e.preventDefault();
        if (!isActiveRef.current) return;

        const touch = e.touches[0];
        let dx = touch.clientX - joystickState.current.centerX;
        let dy = touch.clientY - joystickState.current.centerY;

        const { maxRadius } = joystickState.current;
        const dist = Math.sqrt(dx * dx + dy * dy);

        if (dist > maxRadius) {
            dx = (dx / dist) * maxRadius;
            dy = (dy / dist) * maxRadius;
        }

        joystickState.current.deltaX = dx;
        joystickState.current.deltaY = dy;

        // Update UI directly for performance
        if (stickRef.current) {
            stickRef.current.style.transform = `translate(${dx}px, ${dy}px)`;
        }
    };

    const handleTouchEnd = (e: React.TouchEvent) => {
        e.preventDefault();
        resetJoystick();
    };

    const resetJoystick = () => {
        setIsActive(false);
        joystickState.current.deltaX = 0;
        joystickState.current.deltaY = 0;
        if (stickRef.current) {
            stickRef.current.style.transform = `translate(0px, 0px)`;
        }
    };

    return {
        isJoystickVisible,
        toggleJoystick,
        containerRef,
        stickRef,
        isActive,
        handlers: {
            onTouchStart: handleTouchStart,
            onTouchMove: handleTouchMove,
            onTouchEnd: handleTouchEnd,
            onTouchCancel: handleTouchEnd
        }
    };
};
