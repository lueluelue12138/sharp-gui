import { useCallback, useEffect, useRef, useState } from 'react';
import type { KeyboardEvent, PointerEvent, ReactNode } from 'react';

import { ArrowDownToLine, Camera, Crosshair, Grid3X3, Hand, Image, Maximize, Minimize, Move, RotateCcw, Rotate3D } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/common/Button';
import { Choice, NumberField, RangeField, Segments } from '@/components/portrait/WorkbenchControls';
import { cameraFrame, framingScale, lookCamera, moveCamera, PortraitRenderer, portraitRatios, projectPivot, shiftCamera, turnCamera } from '@/components/portrait/PortraitWorkbench/portraitRenderer';
import type { CameraView } from '@/components/portrait/PortraitWorkbench/portraitRenderer';
import type { PortraitModel } from '@/types/portrait';
import styles from '@/components/portrait/PortraitWorkbench/PortraitWorkbench.module.css';

interface CameraEditorProps {
  model: PortraitModel;
  enabled: boolean;
  view: CameraView | null;
  onView: (view: CameraView) => void;
  rendererRef: React.RefObject<PortraitRenderer | null>;
  ratio: string;
  onRatio: (ratio: string) => void;
  ready: boolean;
  onReady: (ready: boolean) => void;
  released: boolean;
  onRelease: (released: boolean) => void;
  disabled: boolean;
  original: string;
  outputLabel: string;
  settings: ReactNode;
  trajectory: ReactNode;
  action: ReactNode;
}

interface GesturePoint {
  x: number; y: number; startX: number; startY: number;
  mode: 'rotate' | 'pan' | 'dolly'; moved: boolean; canPick: boolean;
}

export function CameraEditor({ model, enabled, view, onView, rendererRef, ratio, onRatio, ready, onReady, released, onRelease, disabled, original, outputLabel, settings, trajectory, action }: CameraEditorProps) {
  const { t } = useTranslation();
  const [failure, setFailure] = useState('');
  const [expanded, setExpanded] = useState(false);
  const [pickFailed, setPickFailed] = useState(false);
  const [dolly, setDolly] = useState<{ anchor: CameraView; applied: CameraView; depth: number; factor: number }>();
  const [interaction, setInteraction] = useState<GesturePoint['mode']>('rotate');
  const [inspector, setInspector] = useState<'camera' | 'output' | 'path'>('camera');
  const [inspectorOpen, setInspectorOpen] = useState(true);
  const [grid, setGrid] = useState(false);
  const [showOriginal, setShowOriginal] = useState(false);
  const [generation, setGeneration] = useState(0);
  const canvas = useRef<HTMLCanvasElement>(null);
  const pointers = useRef(new Map<number, GesturePoint>());
  const currentView = useRef(view);
  const currentRatio = useRef(ratio);
  const pickCounter = useRef(0);

  useEffect(() => { currentView.current = view; }, [view]);
  useEffect(() => { currentRatio.current = ratio; }, [ratio]);

  useEffect(() => {
    const element = canvas.current;
    if (!element || !enabled || released) return;
    const controller = new AbortController();
    const resize = new ResizeObserver(() => {
      if (currentView.current) rendererRef.current?.draw(currentView.current, currentRatio.current);
    });
    resize.observe(element);
    void PortraitRenderer.load(element, model, controller.signal).then((renderer) => {
      if (controller.signal.aborted) { renderer.dispose(); return; }
      rendererRef.current = renderer;
      const initial = currentView.current ?? renderer.reset();
      setFailure('');
      onReady(true);
      onView(initial);
      renderer.draw(initial, currentRatio.current);
    }).catch((error: unknown) => {
      if (!controller.signal.aborted) setFailure(error instanceof Error ? error.message : String(error));
    });
    return () => {
      controller.abort();
      resize.disconnect();
      rendererRef.current?.dispose();
      rendererRef.current = null;
      onReady(false);
    };
  }, [enabled, generation, model, onReady, onView, released, rendererRef]);

  useEffect(() => { if (ready && view) rendererRef.current?.draw(view, ratio); }, [ratio, ready, rendererRef, view]);

  const change = useCallback((next: CameraView) => {
    currentView.current = next;
    onView(next);
    setDolly(undefined);
    setPickFailed(false);
    pickCounter.current += 1;
  }, [onView]);

  useEffect(() => {
    if (!expanded) return;
    function close(event: globalThis.KeyboardEvent) {
      if (event.key === 'Escape' && !event.defaultPrevented) setExpanded(false);
    }
    window.addEventListener('keydown', close);
    return () => window.removeEventListener('keydown', close);
  }, [expanded]);

  const wheel = useCallback((event: WheelEvent) => {
    const active = currentView.current;
    const renderer = rendererRef.current;
    if (disabled || showOriginal || !active || !renderer) return;
    event.preventDefault();
    const next = moveCamera(active, Math.exp(Math.max(-600, Math.min(600, event.deltaY * (event.deltaMode === 1 ? 20 : 1))) * (event.shiftKey ? 0.0001 : 0.001)), renderer.depth);
    change(next);
  }, [change, disabled, rendererRef, showOriginal]);

  useEffect(() => {
    const element = canvas.current;
    element?.addEventListener('wheel', wheel, { passive: false });
    return () => element?.removeEventListener('wheel', wheel);
  }, [enabled, generation, released, wheel]);

  function pointerStart(event: PointerEvent<HTMLCanvasElement>) {
    if (!ready || disabled || showOriginal || event.button > 2) return;
    const x = event.clientX;
    const y = event.clientY;
    const canPick = event.button === 0 && !event.shiftKey;
    const sharedGesture = pointers.current.size > 0;
    if (sharedGesture) {
      pointers.current.forEach((pointer) => { pointer.moved = true; });
      pickCounter.current += 1;
    }
    event.currentTarget.setPointerCapture(event.pointerId);
    event.currentTarget.focus({ preventScroll: true });
    pointers.current.set(event.pointerId, { x, y, startX: x, startY: y, moved: sharedGesture, canPick, mode: canPick ? interaction : 'pan' });
  }

  function pointerMove(event: PointerEvent<HTMLCanvasElement>) {
    const pointer = pointers.current.get(event.pointerId);
    const active = currentView.current;
    const renderer = rendererRef.current;
    if (!pointer || !active || !renderer || disabled) return;
    const x = event.clientX;
    const y = event.clientY;
    const dx = x - pointer.x;
    const dy = y - pointer.y;
    const other = [...pointers.current.values()].find((item) => item !== pointer);
    if (!other && !pointer.moved && Math.hypot(x - pointer.startX, y - pointer.startY) < 4) return;
    const perPixel = renderer.translationPerPixel(active, ratio);
    const fine = event.altKey ? 0.1 : 1;
    let next: CameraView;
    if (other) {
      const oldDistance = Math.max(1, Math.hypot(pointer.x - other.x, pointer.y - other.y));
      const newDistance = Math.max(1, Math.hypot(x - other.x, y - other.y));
      other.moved = true;
      next = moveCamera(shiftCamera(active, -dx * perPixel / 2, -dy * perPixel / 2, 0), oldDistance / newDistance, renderer.depth);
    } else {
      if (pointer.mode === 'pan') next = shiftCamera(active, -dx * perPixel * fine, -dy * perPixel * fine, 0);
      else if (pointer.mode === 'dolly') next = moveCamera(active, Math.exp(dy * 0.006 * fine), renderer.depth);
      else next = turnCamera(active, dx * 0.005 * fine, -dy * 0.005 * fine);
    }
    pointer.moved = true;
    pointer.x = x;
    pointer.y = y;
    change(next);
  }

  function pointerEnd(event: PointerEvent<HTMLCanvasElement>) {
    const pointer = pointers.current.get(event.pointerId);
    pointers.current.delete(event.pointerId);
    if (pointer?.canPick && !pointer.moved) void pickFocus(event.clientX, event.clientY);
  }

  async function pickFocus(x: number, y: number) {
    const renderer = rendererRef.current;
    const active = currentView.current;
    if (!renderer || !active || disabled || showOriginal) return;
    const sequence = ++pickCounter.current;
    const hit = await renderer.pick(active, ratio, x, y).catch(() => null);
    if (sequence !== pickCounter.current || currentView.current !== active || currentRatio.current !== ratio) return;
    if (!hit) { setPickFailed(true); return; }
    change({ ...active, pivot: hit });
  }

  function keyboard(event: KeyboardEvent<HTMLCanvasElement>) {
    const active = currentView.current;
    if (!active || disabled || showOriginal) return;
    if (event.key === 'Enter') {
      event.preventDefault();
      const bounds = event.currentTarget.getBoundingClientRect();
      void pickFocus(bounds.left + bounds.width / 2, bounds.top + bounds.height / 2);
      return;
    }
    const distance = active.distance * (event.shiftKey ? 0.006 : 0.045);
    const angle = event.shiftKey ? 0.008 : 0.055;
    const commands: Record<string, () => CameraView> = {
      ArrowLeft: () => shiftCamera(active, -distance, 0, 0), KeyA: () => shiftCamera(active, -distance, 0, 0),
      ArrowRight: () => shiftCamera(active, distance, 0, 0), KeyD: () => shiftCamera(active, distance, 0, 0),
      ArrowUp: () => shiftCamera(active, 0, -distance, 0), ArrowDown: () => shiftCamera(active, 0, distance, 0),
      KeyW: () => shiftCamera(active, 0, 0, distance), KeyS: () => shiftCamera(active, 0, 0, -distance),
      KeyQ: () => lookCamera(active, -angle, 0), KeyE: () => lookCamera(active, angle, 0),
      KeyR: () => lookCamera(active, 0, -angle), KeyF: () => lookCamera(active, 0, angle),
      KeyZ: () => ({ ...active, roll: active.roll - angle }), KeyC: () => ({ ...active, roll: active.roll + angle }),
    };
    if (!commands[event.code]) return;
    event.preventDefault();
    change(commands[event.code]());
  }

  const { width, height } = cameraFrame(model.intrinsics, ratio);
  const pin = view ? projectPivot(view, model.intrinsics, ratio) : undefined;
  const currentDolly = dolly?.applied === view ? dolly : undefined;
  const dollyDepth = currentDolly?.depth ?? pin?.depth;
  const dollyAnchor = currentDolly?.anchor ?? view;
  const dollyFactor = currentDolly?.factor ?? 1;
  const controlsDisabled = disabled || !view || !ready || released || showOriginal;
  const rollAngle = view ? view.roll * 180 / Math.PI : 0;
  const roll = ((rollAngle + 180) % 360 + 360) % 360 - 180;
  const setRoll = (next: number) => { if (view) change({ ...view, roll: next * Math.PI / 180 }); };
  const inspectorOptions = [
    { value: 'camera', label: t('portrait.compose') }, { value: 'output', label: t('portrait.output') },
    { value: 'path', label: t('portrait.trajectory') },
  ] as const;
  const modes = [
    { value: 'rotate', label: t('portrait.orbit'), icon: <Rotate3D size={17} />, disabled: controlsDisabled },
    { value: 'pan', label: t('portrait.pan'), icon: <Hand size={17} />, disabled: controlsDisabled },
    { value: 'dolly', label: t('portrait.pushPull'), icon: <Move size={17} />, disabled: controlsDisabled },
  ] as const;
  return <section className={`${styles.cameraPanel} ${expanded ? styles.expanded : ''}`} data-angle-expanded={expanded}>
    <div className={styles.cameraViewport}>
      <div className={styles.cameraStage} style={{ '--frame-ratio': width / height, '--frame-scale': framingScale } as React.CSSProperties}>
        {enabled && !released && <canvas className={styles.cameraCanvas} key={generation} ref={canvas} tabIndex={0} aria-label={t('portrait.camera')} data-tool={interaction}
          onContextMenu={(event) => event.preventDefault()}
          onPointerDown={pointerStart} onPointerMove={pointerMove} onPointerUp={pointerEnd}
          onPointerCancel={(event) => pointers.current.delete(event.pointerId)}
          onLostPointerCapture={(event) => pointers.current.delete(event.pointerId)} onKeyDown={keyboard} />}
        {showOriginal && <img className={styles.cameraOriginal} src={original} alt={t('portrait.originalAngle')} />}
        {!showOriginal && !released && ready && <div className={styles.cameraFrame} aria-hidden="true">
          {grid && <div className={styles.thirds} />}
          {pin && <span className={styles.pin} style={{ left: `${pin.x * 100}%`, top: `${pin.y * 100}%` }} />}
        </div>}
        {!showOriginal && (!ready || failure || released) && <div className={styles.cameraNotice} role="status">
          <Camera size={24} /><strong>{t(released ? 'portrait.previewReleased' : failure ? 'portrait.previewError' : 'portrait.previewLoading')}</strong>
          {failure && <small>{failure}</small>}
          {(released || failure) && <Button variant="secondary" size="sm" type="button" onClick={() => {
            onReady(false); setFailure(''); setGeneration(generation + 1); onRelease(false);
          }}>{t('portrait.restorePreview')}</Button>}
        </div>}
        <div className={styles.viewportTop}>
          <span className={styles.viewportLabel}>{t(showOriginal ? 'portrait.originalAngle' : 'portrait.camera')}</span>
          <div className={styles.viewportActions}>
            <Button variant="ghost" type="button" size="sm" iconOnly icon={<Image size={18} />}
              aria-label={t('portrait.showOriginal')} data-tooltip={t('portrait.showOriginal')}
              aria-pressed={showOriginal} onClick={() => setShowOriginal(!showOriginal)} />
            <Button variant="ghost" type="button" size="sm" iconOnly icon={<Grid3X3 size={18} />}
              aria-label={t('portrait.grid')} data-tooltip={t('portrait.grid')} aria-pressed={grid} onClick={() => setGrid(!grid)} />
            <Button variant="ghost" type="button" size="sm" iconOnly icon={expanded ? <Minimize size={18} /> : <Maximize size={18} />}
              aria-label={t(expanded ? 'portrait.closePreview' : 'portrait.fullscreen')}
              data-tooltip={t(expanded ? 'portrait.closePreview' : 'portrait.fullscreen')} onClick={() => setExpanded(!expanded)} />
          </div>
        </div>
      </div>
      <div className={styles.cameraDock}>
        <Segments value={interaction} options={modes} onChange={setInteraction} label={t('portrait.cameraTools')} />
        <Button variant="ghost" size="sm" type="button" icon={<RotateCcw size={16} />} disabled={controlsDisabled}
          onClick={() => { if (rendererRef.current) change(rendererRef.current.reset()); setInteraction('rotate'); }}>
          {t('portrait.resetAngle')}
        </Button>
      </div>
      <p className={styles.cameraHint} aria-live="polite">{t(pickFailed ? 'portrait.noDepth' : 'portrait.cameraGesture')}</p>
    </div>
    <aside className={styles.inspector}>
      <Segments value={inspector} options={inspectorOptions} label={t('portrait.cameraSettings')}
        onChange={(value) => { setInspectorOpen(value !== inspector || !inspectorOpen); setInspector(value); }} />
      <div className={styles.inspectorBody} data-open={inspectorOpen}>
        <div className={styles.inspectorPanel} hidden={inspector !== 'camera'}>
          <section className={styles.perspectivePanel} aria-label={t('portrait.perspective')}>
            <h3><Crosshair size={16} aria-hidden="true" />{t('portrait.perspective')}</h3>
            <p aria-live="polite">{t(pin ? 'portrait.focusReady' : 'portrait.dollyHint')}</p>
            <RangeField label={t('portrait.linkedDolly')} min={dollyAnchor && dollyDepth ? Math.max(0.5, 0.2 / dollyAnchor.zoom, 0.02 / dollyDepth) : 0.5}
              max={dollyAnchor ? Math.min(2, 3 / dollyAnchor.zoom) : 2} step={0.01} value={dollyFactor}
              disabled={controlsDisabled || !dollyDepth} display={`${Math.round(dollyFactor * 100)}%`} onChange={(factor) => {
                if (!dollyAnchor || !dollyDepth) return;
                const shifted = shiftCamera(dollyAnchor, 0, 0, dollyDepth * (1 - factor));
                const next = { ...shifted, zoom: dollyAnchor.zoom * factor };
                pickCounter.current += 1;
                currentView.current = next;
                setDolly({ anchor: dollyAnchor, applied: next, depth: dollyDepth, factor });
                onView(next);
              }} />
          </section>
          <Choice label={t('portrait.ratio')} value={ratio} disabled={disabled || released} onChange={onRatio}
            options={portraitRatios.map((option) => ({ value: option, label: option === 'source' ? t('portrait.originalRatio') : option }))} />
          <RangeField label={t('portrait.zoom')} min={0.2} max={3} step={0.01} value={view?.zoom ?? 1} disabled={controlsDisabled}
            display={`${(view?.zoom ?? 1).toFixed(2)}×`} onChange={(zoom) => { if (view) change({ ...view, zoom }); }} />
          <RangeField label={t('portrait.roll')} min={-180} max={180} step={0.1} value={roll} disabled={controlsDisabled}
            display={`${roll.toFixed(1)}°`} onChange={setRoll} />
          <NumberField label={t('portrait.rollFine')} min={-180} max={180} step={0.1} disabled={controlsDisabled}
            value={Number(roll.toFixed(1))} onChange={setRoll} />
        </div>
        <div className={styles.inspectorPanel} hidden={inspector !== 'output'}>{settings}
          {!released && ready && <Button variant="secondary" size="sm" type="button" disabled={disabled}
            icon={<ArrowDownToLine size={16} />} onClick={() => { onReady(false); onRelease(true); }}>
            {t('portrait.releasePreview')}
          </Button>}
        </div>
        <div className={styles.inspectorPanel} hidden={inspector !== 'path'}>{trajectory}</div>
      </div>
      <div className={styles.editorFooter}><span>{outputLabel}</span>
        {showOriginal ? <Button type="button" variant="secondary" onClick={() => setShowOriginal(false)}>
          {t('portrait.backToCamera')}
        </Button> : action}
      </div>
    </aside>
  </section>;
}
