import React, { useEffect } from 'react';
import styles from './VirtualJoystick.module.css';

interface VirtualJoystickProps {
    visible: boolean;
    isActive: boolean;
    containerRef: React.RefObject<HTMLDivElement | null>;
    stickRef: React.RefObject<HTMLDivElement | null>;
    handlers: {
        onTouchStart: (e: React.TouchEvent) => void;
        onTouchMove: (e: React.TouchEvent) => void;
        onTouchEnd: (e: React.TouchEvent) => void;
        onTouchCancel: (e: React.TouchEvent) => void;
    };
}

export const VirtualJoystick: React.FC<VirtualJoystickProps> = ({ 
    visible, 
    isActive, 
    containerRef, 
    stickRef, 
    handlers 
}) => {
    // Use native event binding with passive: false to prevent scrolling
    // Must be called unconditionally to follow React hook rules
    useEffect(() => {
        // Early return if not visible, but hook is still called
        if (!visible) return;
        
        const container = containerRef.current;
        if (!container) return;

        const handleTouchStart = (e: TouchEvent) => {
            e.preventDefault();
            const syntheticEvent = { 
                preventDefault: () => {}, 
                nativeEvent: e 
            } as unknown as React.TouchEvent;
            handlers.onTouchStart(syntheticEvent);
        };

        const handleTouchMove = (e: TouchEvent) => {
            e.preventDefault();
            const touch = e.touches[0];
            const rect = container.getBoundingClientRect();
            const centerX = rect.left + rect.width / 2;
            const centerY = rect.top + rect.height / 2;
            let dx = touch.clientX - centerX;
            let dy = touch.clientY - centerY;
            
            const maxRadius = 35;
            const dist = Math.sqrt(dx * dx + dy * dy);
            if (dist > maxRadius) {
                dx = (dx / dist) * maxRadius;
                dy = (dy / dist) * maxRadius;
            }

            if (stickRef.current) {
                stickRef.current.style.transform = `translate(${dx}px, ${dy}px)`;
            }

            const syntheticEvent = { 
                preventDefault: () => {}, 
                touches: e.touches,
                nativeEvent: e 
            } as unknown as React.TouchEvent;
            handlers.onTouchMove(syntheticEvent);
        };

        const handleTouchEnd = (e: TouchEvent) => {
            e.preventDefault();
            const syntheticEvent = { 
                preventDefault: () => {}, 
                nativeEvent: e 
            } as unknown as React.TouchEvent;
            handlers.onTouchEnd(syntheticEvent);
        };

        container.addEventListener('touchstart', handleTouchStart, { passive: false });
        container.addEventListener('touchmove', handleTouchMove, { passive: false });
        container.addEventListener('touchend', handleTouchEnd, { passive: false });
        container.addEventListener('touchcancel', handleTouchEnd, { passive: false });

        return () => {
            container.removeEventListener('touchstart', handleTouchStart);
            container.removeEventListener('touchmove', handleTouchMove);
            container.removeEventListener('touchend', handleTouchEnd);
            container.removeEventListener('touchcancel', handleTouchEnd);
        };
    }, [containerRef, stickRef, handlers, visible]);

    // Render null when not visible (after hooks are called)
    if (!visible) return null;

    // Render inside component tree (not portal) so it's positioned relative to viewer container
    return (
        <div 
            ref={containerRef}
            className={`${styles.joystickWrapper} ${visible ? styles.visible : ''} ${isActive ? styles.active : ''}`}
            id="virtual-joystick"
        >
            <div 
                ref={stickRef} 
                className={styles.stick} 
                id="joystick-stick"
            />
        </div>
    );
};
