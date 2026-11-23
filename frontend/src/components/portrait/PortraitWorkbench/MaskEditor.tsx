import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { PointerEvent, ReactNode } from 'react';

import { Brush, Crop as CropIcon, Eraser, Hand, Maximize, Minimize, Minus, Plus, RotateCcw, Undo2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/common/Button';
import { findNativeMaskHoles, findNewMaskHoles } from '@/components/portrait/PortraitWorkbench/maskFill';
import type { MaskSpan } from '@/components/portrait/PortraitWorkbench/maskFill';
import { RangeField, Segments, ToggleField } from '@/components/portrait/WorkbenchControls';
import styles from '@/components/portrait/PortraitWorkbench/PortraitWorkbench.module.css';

export type Crop = [number, number, number, number];
type Tool = 'draw' | 'erase' | 'pan' | 'crop';
type Point = { x: number; y: number };
export type MaskStroke = { points: Point[]; erase: boolean; width: number; filled?: MaskSpan[] };
type Stroke = MaskStroke;
type Gesture = { id: number; tool: Tool; start: Point; origin: Point; width: number; fill: boolean; before?: ImageData; stroke?: Stroke };
type Transform = Point & { scale: number };
const fitted: Transform = { x: 0, y: 0, scale: 1 };
const maskColor = '#ff514a';

interface MaskEditorProps {
  image: string;
  label: string;
  onCanvas: (canvas: HTMLCanvasElement | null) => void;
  reference?: boolean;
  disabled: boolean;
  crop?: Crop;
  onCrop?: (crop?: Crop) => void;
  onPaint: (painted: boolean) => void;
  actions?: ReactNode;
  nativeFill?: boolean;
  showResolution?: boolean;
  initialStrokes?: MaskStroke[];
  onStrokesChange?: (strokes: MaskStroke[]) => void;
}

function distance(a: Point, b: Point) { return Math.hypot(b.x - a.x, b.y - a.y); }
function midpoint(a: Point, b: Point) { return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }; }
function bounds(a: Point, b: Point): Crop { return [Math.min(a.x, b.x), Math.min(a.y, b.y), Math.max(a.x, b.x), Math.max(a.y, b.y)]; }

export function MaskEditor({ image, label, onCanvas, reference, disabled, crop, onCrop, onPaint, actions,
  nativeFill, showResolution, initialStrokes, onStrokesChange }: MaskEditorProps) {
  const { t } = useTranslation();
  const stage = useRef<HTMLDivElement>(null);
  const layer = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const nativePreview = useRef<HTMLCanvasElement>(null);
  const brushCursor = useRef<HTMLSpanElement>(null);
  const brushPoint = useRef<Point | null>(null);
  const transform = useRef(fitted);
  const pointers = useRef(new Map<number, Point>());
  const gesture = useRef<Gesture>(null);
  const strokes = useRef<Stroke[]>(initialStrokes?.slice() ?? []);
  const space = useRef(false);
  const [viewport, setViewport] = useState(fitted);
  const [tool, setTool] = useState<Tool>(reference ? 'pan' : 'draw');
  const [brush, setBrush] = useState(5);
  const [autoFill, setAutoFill] = useState(true);
  const [expanded, setExpanded] = useState(false);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const [photo, setPhoto] = useState({ width: 0, height: 0 });
  const [draft, setDraft] = useState<Crop>();
  const [hasStrokes, setHasStrokes] = useState(false);
  const scale = photo.width ? Math.min(size.width / photo.width, size.height / photo.height) : 0;
  const width = photo.width * scale;
  const height = photo.height * scale;

  useEffect(() => {
    const element = stage.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      if (width > 0 && height > 0) setSize({ width, height });
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!expanded) return;
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') setExpanded(false); };
    window.addEventListener('keydown', escape);
    return () => window.removeEventListener('keydown', escape);
  }, [expanded]);

  function position(next: Transform) {
    // Keep at least a portion of the image reachable after panning.
    const limitX = Math.max(size.width / 3, width * next.scale / 2 + size.width / 3);
    const limitY = Math.max(size.height / 3, height * next.scale / 2 + size.height / 3);
    transform.current = {
      x: Math.max(-limitX, Math.min(limitX, next.x)), y: Math.max(-limitY, Math.min(limitY, next.y)), scale: next.scale,
    };
    setViewport(transform.current);
  }

  function zoom(factor: number, from?: Point, to = from) {
    const current = transform.current;
    const scale = Math.max(1, Math.min(8, current.scale * factor));
    const ratio = scale / current.scale;
    const rect = stage.current?.getBoundingClientRect();
    const origin = rect ? { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 } : { x: 0, y: 0 };
    const start = from ?? origin;
    const end = to ?? origin;
    position({ scale, x: end.x - origin.x - (start.x - origin.x - current.x) * ratio,
      y: end.y - origin.y - (start.y - origin.y - current.y) * ratio });
  }

  // Attachment and cleanup follow the actual editor surface, including fullscreen toggles.
  const wheel = useRef<(event: WheelEvent) => void>(null);
  useEffect(() => {
    const element = stage.current;
    const handler = (event: WheelEvent) => wheel.current?.(event);
    element?.addEventListener('wheel', handler, { passive: false });
    return () => element?.removeEventListener('wheel', handler);
  }, []);
  useEffect(() => {
    wheel.current = (event) => {
      event.preventDefault();
      const factor = Math.exp(-Math.max(-120, Math.min(120, event.deltaY)) * 0.005);
      zoom(factor, { x: event.clientX, y: event.clientY });
    };
  });

  function updateBrushCursor() {
    const element = stage.current;
    const cursor = brushCursor.current;
    if (!element || !cursor) return;

    const active = gesture.current;
    const mode = active?.tool ?? (space.current ? 'pan' : tool);
    const panning = mode === 'pan' || disabled || pointers.current.size > 1;
    element.toggleAttribute('data-panning', panning);

    const point = brushPoint.current;
    const photoRect = layer.current?.getBoundingClientRect();
    const stageRect = element.getBoundingClientRect();
    const diameter = photoRect ? Math.min(photoRect.width, photoRect.height) * (active?.width ?? brush / 100) : 0;
    const visible = Boolean(point && photoRect && diameter > 0 && !panning && mode !== 'crop' &&
      point.x >= Math.max(photoRect.left, stageRect.left) && point.x <= Math.min(photoRect.right, stageRect.right) &&
      point.y >= Math.max(photoRect.top, stageRect.top) && point.y <= Math.min(photoRect.bottom, stageRect.bottom));
    element.toggleAttribute('data-brush-cursor', visible);
    if (visible && point) {
      cursor.style.left = `${point.x - stageRect.left}px`;
      cursor.style.top = `${point.y - stageRect.top}px`;
      cursor.style.width = cursor.style.height = `${diameter}px`;
    }
  }

  useLayoutEffect(() => { updateBrushCursor(); });

  function trackBrush(event: PointerEvent<HTMLDivElement>) {
    brushPoint.current = event.pointerType === 'touch' ? null : { x: event.clientX, y: event.clientY };
    updateBrushCursor();
  }

  function imagePoint(point: Point) {
    const rect = layer.current?.getBoundingClientRect();
    if (!rect?.width || !rect.height) return null;
    return { x: Math.max(0, Math.min(1, (point.x - rect.left) / rect.width)),
      y: Math.max(0, Math.min(1, (point.y - rect.top) / rect.height)) };
  }

  function readMask() {
    const surface = canvas.current;
    return surface?.getContext('2d')?.getImageData(0, 0, surface.width, surface.height);
  }

  function paintFill(ctx: CanvasRenderingContext2D, spans: MaskSpan[]) {
    ctx.globalCompositeOperation = 'source-over';
    ctx.fillStyle = maskColor;
    for (const { x, y, width } of spans) ctx.fillRect(x, y, width, 1);
  }

  function paint(stroke: Stroke, start = 0) {
    const surface = canvas.current;
    const ctx = surface?.getContext('2d', { willReadFrequently: true });
    if (!surface || !ctx || !stroke.points.length) return;
    const weight = stroke.width * Math.min(surface.width, surface.height);
    const first = stroke.points[start];
    ctx.globalCompositeOperation = stroke.erase ? 'destination-out' : 'source-over';
    ctx.strokeStyle = ctx.fillStyle = maskColor;
    ctx.lineWidth = weight;
    ctx.lineCap = ctx.lineJoin = 'round';
    ctx.beginPath();
    if (stroke.points.length === 1) {
      ctx.arc(first.x * surface.width, first.y * surface.height, weight / 2, 0, Math.PI * 2);
      ctx.fill();
    } else {
      ctx.moveTo(first.x * surface.width, first.y * surface.height);
      for (let index = start + 1; index < stroke.points.length; index += 1) {
        const point = stroke.points[index];
        ctx.lineTo(point.x * surface.width, point.y * surface.height);
      }
      ctx.stroke();
    }
    if (stroke.filled) paintFill(ctx, stroke.filled);
  }

  function replay() {
    const surface = canvas.current;
    surface?.getContext('2d', { willReadFrequently: true })?.clearRect(0, 0, surface.width, surface.height);
    strokes.current.forEach((stroke) => paint(stroke));
    if (nativeFill) previewFill();
  }

  function previewFill(mask = readMask()) {
    const preview = nativePreview.current;
    const original = canvas.current;
    const ctx = preview?.getContext('2d');
    if (!preview || !original || !ctx || !mask) return;
    if (preview.width !== mask.width || preview.height !== mask.height) {
      preview.width = mask.width;
      preview.height = mask.height;
    }
    ctx.clearRect(0, 0, mask.width, mask.height);
    // Preview the native binary fill; the unfilled canvas is the input to Goohai.
    for (let i = 3; i < mask.data.length; i += 4) mask.data[i] = mask.data[i] > 25 ? 255 : 0;
    ctx.putImageData(mask, 0, 0);
    if (strokes.current.length) paintFill(ctx, findNativeMaskHoles(mask));
    original.style.visibility = 'hidden';
    preview.hidden = false;
  }

  function reportPaint(save = true) {
    const mask = readMask();
    const pixels = mask?.data;
    setHasStrokes(strokes.current.length > 0);
    if (save) onStrokesChange?.(strokes.current.slice());
    if (!pixels) return;
    if (nativeFill) previewFill(mask);
    for (let index = 3; index < pixels.length; index += 4) {
      if (pixels[index] > 5) { onPaint(true); return; }
    }
    onPaint(false);
  }

  function start(event: PointerEvent<HTMLDivElement>) {
    if (event.button > 2 || !photo.width) return;
    const point = { x: event.clientX, y: event.clientY };
    const intended = event.button !== 0 || space.current || disabled ? 'pan' : tool;
    const imageRect = layer.current?.getBoundingClientRect();
    const inside = imageRect && point.x >= imageRect.left && point.x <= imageRect.right &&
      point.y >= imageRect.top && point.y <= imageRect.bottom;
    event.currentTarget.setPointerCapture(event.pointerId);
    event.currentTarget.focus({ preventScroll: true });
    pointers.current.set(event.pointerId, point);
    if (pointers.current.size > 1) {
      if (gesture.current?.stroke || nativeFill) replay();
      gesture.current = null;
      setDraft(undefined);
      trackBrush(event);
      return;
    }
    const origin = inside || intended === 'pan' ? imagePoint(point) : null;
    if (origin) gesture.current = {
      id: event.pointerId, tool: intended, start: point, origin, width: brush / 100, fill: !nativeFill && autoFill && intended === 'draw',
    };
    if (origin && nativePreview.current && canvas.current && (intended === 'draw' || intended === 'erase')) {
      nativePreview.current.hidden = true;
      canvas.current.style.visibility = '';
    }
    trackBrush(event);
  }

  function move(event: PointerEvent<HTMLDivElement>) {
    trackBrush(event);
    const previous = pointers.current.get(event.pointerId);
    if (!previous) return;
    const next = { x: event.clientX, y: event.clientY };
    const other = [...pointers.current.entries()].find(([id]) => id !== event.pointerId)?.[1];
    pointers.current.set(event.pointerId, next);
    if (other) {
      zoom(Math.max(1, distance(next, other)) / Math.max(1, distance(previous, other)), midpoint(previous, other), midpoint(next, other));
      return;
    }
    const active = gesture.current;
    if (!active || active.id !== event.pointerId) return;
    if (active.tool === 'pan') {
      const view = transform.current;
      position({ ...view, x: view.x + next.x - previous.x, y: view.y + next.y - previous.y });
      return;
    }
    const point = imagePoint(next);
    if (!point) return;
    if (active.tool === 'crop') { setDraft(bounds(active.origin, point)); return; }
    if (!active.stroke && distance(next, active.start) < 3) return;
    if (!active.stroke) {
      if (active.fill) active.before = readMask();
      active.stroke = { points: [active.origin], erase: active.tool === 'erase', width: active.width };
    }
    active.stroke.points.push(point);
    paint(active.stroke, active.stroke.points.length - 2);
  }

  function end(event: PointerEvent<HTMLDivElement>) {
    pointers.current.delete(event.pointerId);
    const active = gesture.current;
    if (active?.id === event.pointerId) gesture.current = null;
    if (event.type === 'pointercancel') {
      brushPoint.current = null;
      updateBrushCursor();
    } else {
      trackBrush(event);
    }
    if (active?.id !== event.pointerId) return;
    if (event.type !== 'pointerup') {
      if (active.stroke || nativeFill) replay();
      setDraft(undefined);
      return;
    }
    if (active.tool === 'crop') {
      const point = imagePoint({ x: event.clientX, y: event.clientY });
      if (point) {
        const box = bounds(active.origin, point);
        if ((box[2] - box[0]) * photo.width >= 8 && (box[3] - box[1]) * photo.height >= 8) onCrop?.(box);
      }
      setDraft(undefined);
    } else if (active.tool !== 'pan') {
      const before = active.before ?? (active.fill && !active.stroke ? readMask() : undefined);
      let stroke: Stroke = active.stroke ?? { points: [active.origin], erase: active.tool === 'erase', width: active.width };
      if (!active.stroke) {
        paint(stroke);
      } else {
        const point = imagePoint({ x: event.clientX, y: event.clientY });
        const last = stroke.points[stroke.points.length - 1];
        if (point && (point.x !== last.x || point.y !== last.y)) {
          stroke.points.push(point);
          paint(stroke, stroke.points.length - 2);
        }
      }
      if (before) {
        const ctx = canvas.current?.getContext('2d');
        const after = readMask();
        if (ctx && after && after.width === before.width && after.height === before.height) {
          const filled = findNewMaskHoles(before, after);
          paintFill(ctx, filled);
          stroke = { ...stroke, filled };
        }
      }
      strokes.current.push(stroke);
      reportPaint();
    }
  }

  const box = draft ?? crop;
  const tools = [
    { value: 'draw', label: t('portrait.draw'), icon: <Brush size={17} />, disabled },
    { value: 'erase', label: t('portrait.erase'), icon: <Eraser size={17} />, disabled },
    { value: 'pan', label: t('portrait.pan'), icon: <Hand size={17} /> },
    ...(reference ? [{ value: 'crop' as const, label: t('portrait.crop'), icon: <CropIcon size={17} />, disabled }] : []),
  ] as const;
  return <section className={`${styles.maskEditor} ${expanded ? styles.maskExpanded : ''}`} data-angle-expanded={expanded}>
    <div className={styles.maskHeader}>
      <div className={styles.maskTitle}>
        <strong>{label}</strong>
        {showResolution && photo.width > 0 && photo.height > 0 && <span>
          {t('photoTools.sourceResolution', { width: photo.width, height: photo.height })}
        </span>}
      </div>
      <div className={styles.viewportActions}>
        <Button variant="ghost" iconOnly size="sm" type="button" icon={<Minus size={17} />} aria-label={t('portrait.zoomOut')} disabled={viewport.scale <= 1} onClick={() => zoom(1 / 1.35)} />
        <Button variant="ghost" size="sm" type="button" aria-label={t('portrait.fitImage')} onClick={() => position(fitted)}>{Math.round(viewport.scale * 100)}%</Button>
        <Button variant="ghost" iconOnly size="sm" type="button" icon={<Plus size={17} />} aria-label={t('portrait.zoomIn')} disabled={viewport.scale >= 8} onClick={() => zoom(1.35)} />
        <Button variant="ghost" iconOnly size="sm" type="button" icon={expanded ? <Minimize size={17} /> : <Maximize size={17} />}
          aria-label={t(expanded ? 'portrait.closePreview' : 'portrait.fullscreenMask')} onClick={() => setExpanded(!expanded)} />
      </div>
    </div>
    <div className={styles.maskStage} ref={stage} tabIndex={0} aria-label={label} data-tool={tool}
      onContextMenu={(event) => event.preventDefault()} onPointerDown={start} onPointerMove={move} onPointerUp={end} onPointerCancel={end} onLostPointerCapture={end}
      onPointerEnter={trackBrush} onPointerLeave={() => { brushPoint.current = null; updateBrushCursor(); }}
      onKeyDown={(event) => {
        if (event.code === 'Space') { space.current = true; event.preventDefault(); updateBrushCursor(); }
        if (event.key === '+' || event.key === '=') zoom(1.35);
        if (event.key === '-') zoom(1 / 1.35);
        if (event.key === '0') position(fitted);
      }} onKeyUp={(event) => {
        if (event.code === 'Space') { space.current = false; updateBrushCursor(); }
      }} onBlur={() => { space.current = false; updateBrushCursor(); }}>
      <div className={styles.maskLayer} ref={layer} style={{ width, height, transform: `translate(-50%, -50%) translate(${viewport.x}px, ${viewport.y}px) scale(${viewport.scale})` }}>
        <img src={image} alt={label} draggable={false} onLoad={(event) => {
          const { naturalWidth, naturalHeight } = event.currentTarget;
          setPhoto({ width: naturalWidth, height: naturalHeight });
          const surface = canvas.current;
          if (!surface) return;
          const downscale = Math.min(1, 2560 / Math.max(naturalWidth, naturalHeight));
          surface.width = Math.max(1, Math.round(naturalWidth * downscale));
          surface.height = Math.max(1, Math.round(naturalHeight * downscale));
          replay();
          if (initialStrokes?.length) reportPaint(false);
        }} />
        <canvas aria-hidden="true" ref={(element) => { canvas.current = element; onCanvas(element); }} />
        {nativeFill && <canvas aria-hidden="true" ref={nativePreview} />}
        {box && <span className={styles.cropBox} style={{ left: `${box[0] * 100}%`, top: `${box[1] * 100}%`, width: `${(box[2] - box[0]) * 100}%`, height: `${(box[3] - box[1]) * 100}%` }} />}
      </div>
      <span className={styles.brushCursor} ref={brushCursor} aria-hidden="true" />
    </div>
    <div className={styles.maskDock}>
      <Segments label={t('portrait.maskTools')} options={tools} value={tool} onChange={setTool} />
      <div className={styles.viewportActions}>
        <Button variant="ghost" iconOnly size="sm" type="button" aria-label={t('portrait.undoStroke')} icon={<Undo2 size={17} />}
          disabled={disabled || !hasStrokes} onClick={() => { strokes.current.pop(); replay(); reportPaint(); }} />
        <Button variant="ghost" iconOnly size="sm" type="button" aria-label={t('portrait.clearMask')} icon={<RotateCcw size={17} />}
          disabled={disabled || !hasStrokes} onClick={() => { strokes.current = []; replay(); reportPaint(); }} />
        {crop && <Button variant="ghost" size="sm" type="button" disabled={disabled} onClick={() => onCrop?.()}>{t('portrait.clearCrop')}</Button>}
      </div>
    </div>
    {(tool === 'draw' || tool === 'erase') && <div className={styles.maskBrushControls}>
      <div className={styles.brushSize}>
        <RangeField label={t('portrait.brush')} min={1} max={30} step={1} display={`${brush}%`}
          value={brush} disabled={disabled} onChange={setBrush} />
      </div>
      <ToggleField label={t('portrait.autoFillMask')} checked={nativeFill || autoFill} disabled={disabled || nativeFill} onChange={setAutoFill} />
    </div>}
    <p className={styles.maskGesture}>{t('portrait.maskGesture')}</p>
    {actions}
  </section>;
}
