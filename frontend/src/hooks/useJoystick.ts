import { useEffect, useRef, useState, useCallback } from 'react';
import type { RefObject } from 'react';
import * as THREE from 'three';

interface JoystickViewer {
    animationActive?: boolean;
    camera?: THREE.Camera;
    controls?: {
        target?: THREE.Vector3;
        update?: () => void;
    };
}

interface UseJoystickProps {
    viewerRef: RefObject<JoystickViewer | null>;
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
        touchId: -1, // Track specific touch finger identifier
    });

    const animationRef = useRef<number | null>(null);
    const stickRef = useRef<HTMLDivElement>(null);
    const containerRef = useRef<HTMLDivElement>(null);
    const isActiveRef = useRef(false);

    const toggleJoystick = useCallback(() => {
        setIsJoystickVisible(prev => !prev);
    }, []);

    useEffect(() => {
        isActiveRef.current = isActive;
    }, [isActive]);

    useEffect(() => {
        if (isActive) {
            const updateMovement = () => {
                const viewer = viewerRef.current;
                if (!viewer || viewer.animationActive || !isActiveRef.current) {
                    return;
                }

                const camera = viewer.camera;
                const controls = viewer.controls;
                if (!camera) return;

                const { deltaX, deltaY, maxRadius, moveSpeed } = joystickState.current;

                // Normalize -1 to 1
                const nx = deltaX / maxRadius;
                const ny = deltaY / maxRadius;

                if (Math.abs(nx) > 0.1 || Math.abs(ny) > 0.1) {
                    const forward = new THREE.Vector3();
                    camera.getWorldDirection(forward);

                    const right = new THREE.Vector3();
                    right.crossVectors(forward, camera.up).normalize();

                    const delta = new THREE.Vector3();
                    delta.add(right.clone().multiplyScalar(nx * moveSpeed));
                    delta.add(forward.clone().multiplyScalar(-ny * moveSpeed));

                    camera.position.add(delta);
                    controls?.target?.add(delta);
                    controls?.update?.();
                }

                animationRef.current = requestAnimationFrame(updateMovement);
            };

            animationRef.current = requestAnimationFrame(updateMovement);
        } else {
             if (animationRef.current) {
                 cancelAnimationFrame(animationRef.current);
                 animationRef.current = null;
             }
        }
    }, [isActive, viewerRef]);


    // Find the specific touch that belongs to the joystick by identifier
    const findTouch = (touches: TouchList, id: number): Touch | null => {
        for (let i = 0; i < touches.length; i++) {
            if (touches[i].identifier === id) return touches[i];
        }
        return null;
    };

    // Handlers — track specific touch identifier to avoid multi-touch conflicts
    const handleTouchStart = (e: React.TouchEvent) => {
        e.preventDefault();
        if (!containerRef.current) return;
        // Only claim the first finger touching the joystick
        if (joystickState.current.touchId >= 0) return;

        // Use the native event to get changedTouches (the finger that just arrived)
        const nativeEvent = (e as unknown as { nativeEvent?: TouchEvent }).nativeEvent;
        const newTouch = nativeEvent?.changedTouches?.[0] ?? (e.touches?.[0] as unknown as Touch);
        if (!newTouch) return;

        joystickState.current.touchId = newTouch.identifier;

        const rect = containerRef.current.getBoundingClientRect();
        joystickState.current.centerX = rect.left + rect.width / 2;
        joystickState.current.centerY = rect.top + rect.height / 2;

        setIsActive(true);
    };

    const handleTouchMove = (e: React.TouchEvent) => {
        e.preventDefault();
        if (!isActiveRef.current) return;

        // Only follow our tracked finger
        const touch = findTouch(e.touches as unknown as TouchList, joystickState.current.touchId);
        if (!touch) return;

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
        // Only reset if our tracked finger was lifted
        const nativeEvent = (e as unknown as { nativeEvent?: TouchEvent }).nativeEvent;
        const changed = nativeEvent?.changedTouches;
        if (changed) {
            let found = false;
            for (let i = 0; i < changed.length; i++) {
                if (changed[i].identifier === joystickState.current.touchId) { found = true; break; }
            }
            if (!found) return;
        }
        resetJoystick();
    };

    const resetJoystick = () => {
        setIsActive(false);
        joystickState.current.touchId = -1;
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
