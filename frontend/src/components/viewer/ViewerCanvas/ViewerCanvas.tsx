import React, { useEffect, useRef, useState } from 'react';
import { useViewer } from '@/hooks/useViewer';
import { useAppStore } from '@/store/useAppStore';
import { ControlsBar } from '@/components/layout/ControlsBar/ControlsBar';
import { Help } from '@/components/layout/Help/Help';
import { GyroIndicator } from '@/components/viewer/GyroIndicator/GyroIndicator';
import { QuickControls } from '@/components/viewer/QuickControls';
import { ModelEditor } from '@/components/viewer/ModelEditor';
import { ViewerRevealEffectsRail } from '@/components/viewer/ViewerRevealEffectsRail';
import { VirtualJoystick } from '@/components/viewer/VirtualJoystick/VirtualJoystick';
import { SpeedTooltip } from '@/components/viewer/SpeedTooltip';
import { resolveRevealEffectPreference, type RevealEffectId } from '@/utils/viewerRevealEffects';
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
  const [editorOpen, setEditorOpen] = useState(false);
  const currentModelId = useAppStore((state) => state.currentModelId);
  const currentModelSource = useAppStore((state) => state.currentModelSource);
  const isOwnerAccess = useAppStore((state) => state.isOwnerAccess);
  const isLoading = useAppStore((state) => state.isLoading);
  const pendingModelEditorId = useAppStore((state) => state.pendingModelEditorId);
  const clearModelEditorRequest = useAppStore((state) => state.clearModelEditorRequest);
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerDefaultRevealEffect = useAppStore((state) => state.viewerDefaultRevealEffect);
  const [activeEffect, setActiveEffect] = useState<RevealEffectId>(
    resolveRevealEffectPreference(viewerDefaultRevealEffect),
  );
  const [replayToken, setReplayToken] = useState(0);
  const viewerHook = useViewer(containerRef, {
    revealEffect: editorOpen ? 'none' : activeEffect,
    replayToken,
  });
  const { viewerRef, toggleGyro, xr: { isInXR } } = viewerHook;

  useEffect(() => {
    setActiveEffect(resolveRevealEffectPreference(viewerDefaultRevealEffect));
  }, [viewerDefaultRevealEffect]);

  useEffect(() => {
    if (!pendingModelEditorId || pendingModelEditorId !== currentModelId) return;
    if (!isOwnerAccess || currentModelSource === 'temporary') {
      clearModelEditorRequest();
      return;
    }
    if (isLoading || !viewerRef.current?.splatMesh || isInXR) return;
    if (useAppStore.getState().isGyroEnabled) toggleGyro();
    clearModelEditorRequest();
    setEditorOpen(true);
  }, [clearModelEditorRequest, currentModelId, currentModelSource, isInXR, isLoading, isOwnerAccess,
    pendingModelEditorId, toggleGyro, viewerRef]);

  return (
    <>
      <div ref={containerRef} className={styles.viewerTarget} />
      {editorOpen && currentModelId ? (
        <ModelEditor
          viewerRef={viewerHook.viewerRef}
          assetId={currentModelId}
          onClose={() => setEditorOpen(false)}
        />
      ) : (
        <>
          <ControlsBar
            viewerHook={viewerHook}
            onEdit={
              isOwnerAccess &&
              currentModelId &&
              currentModelSource !== 'temporary' &&
              !isLoading &&
              !viewerHook.xr.isInXR
                ? () => {
                    if (useAppStore.getState().isGyroEnabled) viewerHook.toggleGyro();
                    setEditorOpen(true);
                  }
                : undefined
            }
          />
          <GyroIndicator ballRef={viewerHook.indicatorBallRef} />
          <VirtualJoystick
            visible={viewerHook.joystick.isJoystickVisible}
            isActive={viewerHook.joystick.isActive}
            containerRef={viewerHook.joystick.containerRef}
            stickRef={viewerHook.joystick.stickRef}
            handlers={viewerHook.joystick.handlers}
          />
          <SpeedTooltip mode={viewerHook.speedMode} />
          <ViewerRevealEffectsRail
            activeEffect={activeEffect}
            isInXr={viewerHook.xr.isInXR}
            onReplay={() => setReplayToken((value) => value + 1)}
            onSelectEffect={setActiveEffect}
          />
          <QuickControls debugInfo={viewerHook.debugInfo} isInXr={viewerHook.xr.isInXR} />
          <Help />
        </>
      )}
    </>
  );
};
