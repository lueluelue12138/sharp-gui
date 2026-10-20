import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useViewer } from '@/hooks/useViewer';
import { useAppStore } from '@/store/useAppStore';
import { fetchEditorSource } from '@/api/modelEditor';
import { ControlsBar } from '@/components/layout/ControlsBar/ControlsBar';
import { Help } from '@/components/layout/Help/Help';
import { GyroIndicator } from '@/components/viewer/GyroIndicator/GyroIndicator';
import { QuickControls } from '@/components/viewer/QuickControls';
import { ModelEditor } from '@/components/viewer/ModelEditor';
import { CameraAnimationPanel } from '@/components/viewer/CameraAnimationPanel';
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
  const [animationOpen, setAnimationOpen] = useState(false);
  const [portrait, setPortrait] = useState(false);
  const [stageSize, setStageSize] = useState<{ width: number; height: number } | null>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const sidebarCollapsed = useAppStore((state) => state.sidebarCollapsed);
  const [editorCheck, setEditorCheck] = useState<{ assetId: string; supported: boolean } | null>(null);
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
    revealEffect: editorOpen || animationOpen ? 'none' : activeEffect,
    replayToken,
  });
  const { viewerRef, toggleGyro, xr: { isInXR } } = viewerHook;

  useLayoutEffect(() => {
    const stage = stageRef.current;
    if (!stage) return;
    const resize = () => {
      if (!animationOpen) { setStageSize(null); return; }
      const aspect = portrait ? 9 / 16 : 16 / 9;
      const width = Math.min(stage.clientWidth, stage.clientHeight * aspect);
      setStageSize({ width, height: width / aspect });
    };
    const observer = new ResizeObserver(resize); observer.observe(stage); resize();
    return () => observer.disconnect();
  }, [animationOpen, portrait]);

  useEffect(() => {
    setActiveEffect(resolveRevealEffectPreference(viewerDefaultRevealEffect));
  }, [viewerDefaultRevealEffect]);

  useEffect(() => {
    if (!isOwnerAccess || !currentModelId || currentModelSource === 'temporary') return;
    const abort = new AbortController();
    // Use the actual editor source, including for legacy gallery entries. A file
    // extension or source label cannot establish that its structure is editable.
    void fetchEditorSource(currentModelId, abort.signal).then(() => {
      if (!abort.signal.aborted) setEditorCheck({ assetId: currentModelId, supported: true });
    }).catch(() => {
      if (!abort.signal.aborted) setEditorCheck({ assetId: currentModelId, supported: false });
    });
    return () => abort.abort();
  }, [currentModelId, currentModelSource, isOwnerAccess]);

  useEffect(() => {
    if (!pendingModelEditorId || pendingModelEditorId !== currentModelId) return;
    if (!isOwnerAccess || currentModelSource === 'temporary') {
      clearModelEditorRequest();
      return;
    }
    if (editorCheck?.assetId !== currentModelId) return;
    if (!editorCheck.supported) {
      clearModelEditorRequest();
      return;
    }
    if (isLoading || !viewerRef.current?.splatMesh || isInXR) return;
    if (useAppStore.getState().isGyroEnabled) toggleGyro();
    clearModelEditorRequest();
    setAnimationOpen(false);
    setEditorOpen(true);
  }, [clearModelEditorRequest, currentModelId, currentModelSource, isInXR, isLoading, isOwnerAccess,
    pendingModelEditorId, toggleGyro, viewerRef, editorCheck]);

  return (
    <div className={[styles.layout, animationOpen && !sidebarCollapsed && styles.animationSidebarExpanded].filter(Boolean).join(' ')}>
      <div ref={stageRef} className={[styles.stage, animationOpen && styles.animationStage].filter(Boolean).join(' ')}>
        <div ref={containerRef} className={styles.viewerTarget} style={stageSize ? { ...stageSize, left: '50%', top: '50%', transform: 'translate(-50%, -50%)' } : undefined} />
      </div>
      <CameraAnimationPanel open={animationOpen} viewerRef={viewerRef} portrait={portrait} onPortraitChange={setPortrait} onClose={() => setAnimationOpen(false)} />
      {editorOpen && currentModelId ? (
        <ModelEditor
          viewerRef={viewerHook.viewerRef}
          assetId={currentModelId}
          onClose={() => setEditorOpen(false)}
        />
      ) : !animationOpen ? (
        <>
          <ControlsBar
            viewerHook={viewerHook}
            onAnimate={!isLoading && !isInXR ? () => {
              if (useAppStore.getState().isGyroEnabled) toggleGyro();
              useAppStore.getState().setQuickControlsOpen(false);
              setAnimationOpen(true);
            } : undefined}
            onEdit={
              isOwnerAccess &&
              currentModelId &&
              editorCheck?.assetId === currentModelId && editorCheck.supported &&
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
      ) : null}
    </div>
  );
};
