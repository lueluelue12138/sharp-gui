import { useCallback, useEffect, useRef, useState } from 'react';
import type { CSSProperties, KeyboardEvent, PointerEvent } from 'react';

import { ArrowLeftRight, Download, LoaderCircle, Maximize, Minimize, Minus, Plus } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/common/Button';
import { usePortraitDownload } from '@/components/portrait/PortraitWorkbench/usePortraitDownload';
import styles from '@/components/portrait/PortraitWorkbench/PortraitWorkbench.module.css';

interface ImageComparisonProps {
  before: string;
  after: string;
  beforeLabel: string;
  afterLabel: string;
}

type Point = { x: number; y: number };
type Viewport = Point & { scale: number };
const fitted: Viewport = { x: 0, y: 0, scale: 1 };
const maximumZoom = 8;

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function midpoint(a: Point, b: Point) {
  return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
}

function touchDistance(a: Point, b: Point, rect: DOMRect) {
  return Math.max(1, Math.hypot((a.x - b.x) * rect.width, (a.y - b.y) * rect.height));
}

function imagePoint(x: number, y: number, rect: DOMRect) {
  return { x: (x - rect.left) / rect.width - 0.5, y: (y - rect.top) / rect.height - 0.5 };
}

export function ImageComparison({ before, after, beforeLabel, afterLabel }: ImageComparisonProps) {
  const { t } = useTranslation();
  const { download, downloading, downloadFailed } = usePortraitDownload();
  const [position, setPosition] = useState(50);
  const [sideBySide, setSideBySide] = useState(false);
  const [imageRatio, setImageRatio] = useState(4 / 3);
  const [expanded, setExpanded] = useState(false);
  const [viewport, setViewport] = useState(fitted);
  const stage = useRef<HTMLDivElement>(null);
  const currentViewport = useRef(fitted);
  const pointers = useRef(new Map<number, Point>());
  const gesture = useRef<{ pane: HTMLDivElement; divider: boolean; initialPosition: number }>(null);

  const setView = useCallback((next: Viewport) => {
    const limit = (next.scale - 1) / 2;
    currentViewport.current = { scale: next.scale, x: clamp(next.x, -limit, limit), y: clamp(next.y, -limit, limit) };
    setViewport(currentViewport.current);
  }, []);

  const zoom = useCallback((factor: number, from: Point = fitted, to = from) => {
    const current = currentViewport.current;
    const scale = clamp(current.scale * factor, 1, maximumZoom);
    const ratio = scale / current.scale;
    setView({ scale, x: to.x - (from.x - current.x) * ratio, y: to.y - (from.y - current.y) * ratio });
  }, [setView]);

  useEffect(() => {
    const element = stage.current;
    function wheel(event: WheelEvent) {
      const pane = event.target instanceof Element ? event.target.closest('[data-comparison-pane]') : null;
      if (!pane || !event.deltaY) return;
      event.preventDefault();
      const rect = pane.getBoundingClientRect();
      const delta = event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? rect.height : 1);
      zoom(Math.exp(-clamp(delta, -120, 120) * 0.006), imagePoint(event.clientX, event.clientY, rect));
    }
    element?.addEventListener('wheel', wheel, { passive: false });
    return () => element?.removeEventListener('wheel', wheel);
  }, [zoom]);

  useEffect(() => {
    if (!expanded) return;
    function escape(event: globalThis.KeyboardEvent) {
      if (event.key === 'Escape' && !event.defaultPrevented) setExpanded(false);
    }
    window.addEventListener('keydown', escape);
    return () => window.removeEventListener('keydown', escape);
  }, [expanded]);

  function pointerStart(event: PointerEvent<HTMLDivElement>) {
    const pane = event.currentTarget;
    if (event.button !== 0 || pointers.current.size >= 2 || (gesture.current && event.pointerType !== 'touch')) return;
    const rect = (gesture.current?.pane ?? pane).getBoundingClientRect();
    const next = imagePoint(event.clientX, event.clientY, rect);
    if (!gesture.current) {
      const target = event.target instanceof Element ? event.target.closest('[role="slider"]') : null;
      const nearDivider = Math.abs((next.x + 0.5 - position / 100) * rect.width) <= 22;
      gesture.current = { pane, divider: !sideBySide && (Boolean(target) || nearDivider || currentViewport.current.scale === 1), initialPosition: position };
      if (target instanceof HTMLElement) target.focus({ preventScroll: true });
    } else if (gesture.current.divider) {
      setPosition(gesture.current.initialPosition);
      gesture.current.divider = false;
    }
    pane.setPointerCapture(event.pointerId);
    pointers.current.set(event.pointerId, next);
  }

  function pointerMove(event: PointerEvent<HTMLDivElement>) {
    const previous = pointers.current.get(event.pointerId);
    const active = gesture.current;
    if (!previous || !active) return;
    const rect = active.pane.getBoundingClientRect();
    const next = imagePoint(event.clientX, event.clientY, rect);
    const other = [...pointers.current.entries()].find(([id]) => id !== event.pointerId)?.[1];
    pointers.current.set(event.pointerId, next);
    if (other) {
      zoom(touchDistance(next, other, rect) / touchDistance(previous, other, rect), midpoint(previous, other), midpoint(next, other));
    } else if (active.divider) {
      setPosition(clamp(Math.round((next.x + 0.5) * 100), 0, 100));
    } else {
      const current = currentViewport.current;
      setView({ ...current, x: current.x + next.x - previous.x, y: current.y + next.y - previous.y });
    }
  }

  function pointerEnd(event: PointerEvent<HTMLDivElement>) {
    if (!pointers.current.delete(event.pointerId)) return;
    const active = gesture.current;
    if (event.type === 'pointerup' && active?.divider) {
      const rect = active.pane.getBoundingClientRect();
      setPosition(clamp(Math.round(100 * (event.clientX - rect.left) / rect.width), 0, 100));
    }
    if (!pointers.current.size) gesture.current = null;
  }

  function dividerKeys(event: KeyboardEvent<HTMLDivElement>) {
    const values: Record<string, number> = {
      ArrowLeft: position - 2, ArrowDown: position - 2, ArrowRight: position + 2, ArrowUp: position + 2,
      PageDown: position - 10, PageUp: position + 10, Home: 0, End: 100,
    };
    if (!Object.hasOwn(values, event.key)) return;
    event.preventDefault();
    setPosition(clamp(values[event.key], 0, 100));
  }

  const paneEvents = {
    onPointerDown: pointerStart, onPointerMove: pointerMove, onPointerUp: pointerEnd,
    onPointerCancel: pointerEnd, onLostPointerCapture: pointerEnd,
  };
  const pictureStyle = { transform: `translate3d(${viewport.x * 100}%, ${viewport.y * 100}%, 0) scale(${viewport.scale})` };
  const readAspect = (image: HTMLImageElement) => {
    if (image.naturalHeight) setImageRatio(image.naturalWidth / image.naturalHeight);
  };
  return <div className={`${styles.comparison} ${expanded ? styles.comparisonExpanded : ''}`} data-angle-expanded={expanded}>
    <div className={styles.compareControls}>
      <Button variant="secondary" size="sm" type="button" icon={<ArrowLeftRight size={16} />} onClick={() => setSideBySide(!sideBySide)}>
        {t(sideBySide ? 'portrait.sliderMode' : 'portrait.sideBySide')}
      </Button>
      <div className={styles.compareZoom} role="group" aria-label={t('portrait.comparisonZoom')}>
        <Button variant="ghost" size="sm" type="button" iconOnly icon={<Minus size={17} />} aria-label={t('portrait.zoomOut')}
          disabled={viewport.scale === 1} onClick={() => zoom(1 / 1.35)} />
        <Button variant="ghost" size="sm" type="button" aria-label={t('portrait.fitImage')}
          onClick={() => setView(fitted)}>{Math.round(viewport.scale * 100)}%</Button>
        <Button variant="ghost" size="sm" type="button" iconOnly icon={<Plus size={17} />} aria-label={t('portrait.zoomIn')}
          disabled={viewport.scale >= maximumZoom} onClick={() => zoom(1.35)} />
      </div>
      <Button variant="secondary" size="sm" type="button" iconOnly icon={expanded ? <Minimize size={17} /> : <Maximize size={17} />}
        aria-label={t(expanded ? 'portrait.closePreview' : 'portrait.fullscreenComparison')}
        onClick={() => setExpanded(!expanded)} />
      <Button variant="secondary" size="sm" type="button" disabled={downloading !== null}
        className={styles.downloadButton} aria-busy={downloading !== null}
        icon={downloading ? <LoaderCircle className="spin" /> : <Download />}
        onClick={() => void download(after, 'spatial-reframing.png')}>
        {t(downloading ? 'downloading' : 'portrait.download')}
      </Button>
    </div>
    {downloadFailed && <p className={styles.downloadError} role="alert">{t('portrait.downloadFailed')}</p>}
    <div ref={stage} className={sideBySide ? styles.compareGrid : styles.compareStage}
      style={{ '--comparison-ratio': imageRatio, '--split': `${position}%` } as CSSProperties}>
      {sideBySide ? <>
        <div className={styles.comparePane} data-comparison-pane data-zoomed={viewport.scale > 1} {...paneEvents}>
          <img src={before} alt={beforeLabel} draggable={false} style={pictureStyle} />
          <span className={styles.beforeLabel}>{beforeLabel}</span>
        </div>
        <div className={styles.comparePane} data-comparison-pane data-zoomed={viewport.scale > 1} {...paneEvents}>
          <img src={after} alt={afterLabel} draggable={false} style={pictureStyle} onLoad={(event) => readAspect(event.currentTarget)} />
          <span className={styles.beforeLabel}>{afterLabel}</span>
        </div>
      </> : <div className={`${styles.comparePane} ${styles.splitPane}`} data-comparison-pane data-zoomed={viewport.scale > 1} {...paneEvents}>
        <img src={after} alt={afterLabel} draggable={false} style={pictureStyle} onLoad={(event) => readAspect(event.currentTarget)} />
        <div className={styles.beforeLayer}><img src={before} alt={beforeLabel} draggable={false} style={pictureStyle} /></div>
        <span className={styles.beforeLabel}>{beforeLabel}</span>
        <span className={styles.afterLabel}>{afterLabel}</span>
        <div className={styles.divider} role="slider" tabIndex={0} aria-label={t('portrait.compareSlider')}
          aria-valuemin={0} aria-valuemax={100} aria-valuenow={position} onKeyDown={dividerKeys}>
          <span><ArrowLeftRight size={16} aria-hidden="true" /></span>
        </div>
      </div>}
    </div>
  </div>;
}
