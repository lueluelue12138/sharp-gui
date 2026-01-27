import React, { useRef } from 'react';
import { useViewer } from '@/hooks/useViewer';
import { useAppStore } from '@/store/useAppStore';
import { ControlsBar } from '@/components/layout/ControlsBar/ControlsBar';
import { Help } from '@/components/layout/Help/Help';
import { GyroIndicator } from '@/components/viewer/GyroIndicator/GyroIndicator';
import { VirtualJoystick } from '@/components/viewer/VirtualJoystick/VirtualJoystick';
import { SpeedTooltip } from '@/components/viewer/SpeedTooltip';
import styles from './ViewerCanvas.module.css';

export const ViewerCanvas: React.FC = () => {
  const { currentModelUrl } = useAppStore();
  
  // Using key to force re-mounting when model URL changes, 
  // implementing the "destroy and recreate" strategy from the original code
  // to avoid texture overlap/cleanup issues.
  if (!currentModelUrl) return null;

  return (
    <div className={styles.container}>
        <ViewerInstance key={currentModelUrl} />
    </div>
  );
};

// Internal component to handle the actual viewer lifecycle
const ViewerInstance: React.FC = () => {
    const containerRef = useRef<HTMLDivElement>(null);
    const viewerHook = useViewer(containerRef);

    return (
        <>
            <div ref={containerRef} className={styles.viewerTarget} />
            <ControlsBar viewerHook={viewerHook} />
            <GyroIndicator ballRef={viewerHook.indicatorBallRef} />
            <VirtualJoystick 
                visible={viewerHook.joystick.isJoystickVisible}
                isActive={viewerHook.joystick.isActive}
                containerRef={viewerHook.joystick.containerRef}
                stickRef={viewerHook.joystick.stickRef}
                handlers={viewerHook.joystick.handlers}
            />
            <SpeedTooltip mode={viewerHook.speedMode} />
            <Help />
        </>
    );
};
