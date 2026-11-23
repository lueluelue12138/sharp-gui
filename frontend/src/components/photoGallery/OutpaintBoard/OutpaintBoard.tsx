import { useEffect, useRef, useState } from 'react';
import type { KeyboardEvent, PointerEvent } from 'react';

import { Crop, Focus, Minus, Move, Plus, RotateCcw, ScanLine } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/common/Button';
import { Choice, NumberField, Segments, ToggleField } from '@/components/portrait/WorkbenchControls';

import styles from '@/components/photoGallery/OutpaintBoard/OutpaintBoard.module.css';
import { aspectRatios, boardGeometry, clamp, constrainPads, edgeBase, initialLayout, sides } from '@/components/photoGallery/OutpaintBoard/geometry';
import type { ImageSize, OutpaintLayout, Pads } from '@/components/photoGallery/OutpaintBoard/geometry';

type Point = { x: number; y: number };
const center = { x: 0, y: 0 };
const handles = [
  { name: 'left', edges: [0] }, { name: 'right', edges: [1] }, { name: 'top', edges: [2] }, { name: 'bottom', edges: [3] },
  { name: 'topLeft', edges: [0, 2] }, { name: 'topRight', edges: [1, 2] },
  { name: 'bottomLeft', edges: [0, 3] }, { name: 'bottomRight', edges: [1, 3] },
];

interface Drag {
  id: number;
  origin: Point;
  pan: Point;
  pads: Pads;
  edges: number[];
  mode: 'edges' | 'image' | 'pan';
  scale: Point;
  displayScale: number;
  imageOrigin: Point;
  snaps: Map<number, number>;
}

function snap(drag: Drag, side: number, value: number, targets: number[]) {
  const scale = side < 2 ? drag.scale.x : drag.scale.y;
  const held = drag.snaps.get(side);
  if (held !== undefined && Math.abs(value - held) * scale <= 14) return held;
  const hit = targets.find((target) => Math.abs(value - target) * scale <= 6);
  if (hit === undefined) drag.snaps.delete(side);
  else drag.snaps.set(side, hit);
  return hit ?? value;
}

export function OutpaintBoard({ image, size, layout, maskPreview, disabled, onSize, onChange }: {
  image: string; size: ImageSize | undefined; layout: OutpaintLayout; maskPreview?: string; disabled: boolean;
  onSize: (value: ImageSize) => void; onChange: (value: OutpaintLayout) => void;
}) {
  const { t } = useTranslation();
  const stage = useRef<HTMLDivElement>(null);
  const drag = useRef<Drag>(null);
  const [viewport, setViewport] = useState({ width: 1, height: 1 });
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState(center);
  const [panning, setPanning] = useState(false);
  const [symmetric, setSymmetric] = useState(false);
  const [fixed, setFixed] = useState<Pick<Drag, 'displayScale' | 'imageOrigin'>>();
  const geometry = size && boardGeometry(size, layout);
  const fit = geometry ? Math.max(0.001, Math.min((viewport.width - 64) / geometry.outputWidth,
    (viewport.height - 64) / geometry.outputHeight)) : 1;
  const scale = fixed ? fixed.displayScale : fit * zoom;

  useEffect(() => {
    if (!stage.current) return;
    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      if (width && height) setViewport({ width, height });
    });
    observer.observe(stage.current);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const element = stage.current;
    function wheel(event: WheelEvent) {
      if (!event.ctrlKey || !event.deltaY) return;
      event.preventDefault();
      setZoom((value) => clamp(value * (event.deltaY < 0 ? 1.1 : 0.9), 0.25, 3));
    }
    element?.addEventListener('wheel', wheel, { passive: false });
    return () => element?.removeEventListener('wheel', wheel);
  }, []);

  function setEdges(pads: Pads, edges: number[], mirrored = symmetric) {
    if (size) onChange({ ...layout, pads: constrainPads(pads, size, layout.ratio, edges, mirrored), translated: false });
  }

  function start(event: PointerEvent, edges: number[] = []) {
    if (!geometry || !size || !stage.current || drag.current || (event.button !== 0 && event.button !== 1)) return;
    const mode = event.button === 1 || panning ? 'pan' : edges.length ? 'edges' : 'image';
    if (disabled && mode !== 'pan') return;
    event.stopPropagation();
    if (event.button === 1) event.preventDefault();
    stage.current.setPointerCapture(event.pointerId);
    drag.current = { id: event.pointerId, origin: { x: event.clientX, y: event.clientY }, pan, pads: [...layout.pads], edges,
      mode, scale: { x: scale * geometry.scaleX, y: scale * geometry.scaleY }, displayScale: scale,
      imageOrigin: { x: (geometry.imageX - geometry.outputWidth / 2) * scale + pan.x,
        y: (geometry.imageY - geometry.outputHeight / 2) * scale + pan.y }, snaps: new Map() };
    if (mode === 'edges') setFixed(drag.current);
  }

  function move(event: PointerEvent) {
    const active = drag.current;
    if (!active || !size || active.id !== event.pointerId) return;
    const dx = event.clientX - active.origin.x, dy = event.clientY - active.origin.y;
    if (active.mode === 'pan') {
      setPan({ x: clamp(active.pan.x + dx, -viewport.width / 2, viewport.width / 2),
        y: clamp(active.pan.y + dy, -viewport.height / 2, viewport.height / 2) });
      return;
    }
    const x = Math.round(dx / active.scale.x), y = Math.round(dy / active.scale.y);
    if (!x && !y && active.pads.every((pad, index) => pad === layout.pads[index])) return;
    const pads: Pads = [...active.pads];
    if (active.mode === 'image') {
      const h = pads[0] + pads[1], v = pads[2] + pads[3];
      pads[0] = clamp(snap(active, 0, pads[0] + x, [0, h]), 1 - size.width, size.width + h - 1);
      pads[1] = h - pads[0];
      pads[2] = clamp(snap(active, 2, pads[2] + y, [0, v]), 1 - size.height, size.height + v - 1);
      pads[3] = v - pads[2];
      onChange({ ...layout, pads, translated: true });
      return;
    }
    const changes = [-x, x, -y, y];
    for (const side of active.edges) {
      pads[side] = clamp(pads[side] + changes[side], -65536, 65536);
    }
    const mirror = symmetric || event.shiftKey;
    if (layout.ratio === 'free') {
      active.edges.forEach((side) => { pads[side] = snap(active, side, pads[side], [0]); });
      setEdges(pads, active.edges, mirror);
      return;
    }
    const constrained = constrainPads(pads, size, layout.ratio, active.edges, mirror);
    const candidates = [0, 1, 2, 3].filter((side) => constrained[side] !== active.pads[side] || active.snaps.has(side))
      .sort((a, b) => Number(active.snaps.has(b)) - Number(active.snaps.has(a)) || Math.abs(constrained[a]) - Math.abs(constrained[b]));
    for (const side of candidates) {
      const distance = Math.abs(constrained[side]);
      const sideScale = side < 2 ? active.scale.x : active.scale.y;
      if (distance * sideScale > (active.snaps.has(side) ? 14 : 6)) continue;
      // The locked ratio can move an edge other than the one under the pointer.
      // Find the closest drag adjustment that still aligns it to the source.
      const at = (delta: number) => {
        const trial: Pads = [...pads];
        active.edges.forEach((edge) => { trial[edge] += delta; });
        return constrainPads(trial, size, layout.ratio, active.edges, mirror);
      };
      let low = -Math.max(size.width, size.height), high = -low;
      if (at(low)[side] > 0 || at(high)[side] < 0) continue;
      while (high - low > 1) {
        const mid = Math.floor((low + high) / 2);
        if (at(mid)[side] < 0) low = mid;
        else high = mid;
      }
      const aligned = at(high);
      if (aligned[side] !== 0) continue;
      active.snaps.clear();
      active.snaps.set(side, 0);
      onChange({ ...layout, pads: aligned, translated: false });
      return;
    }
    active.snaps.clear();
    onChange({ ...layout, pads: constrained, translated: false });
  }

  function finish(event: PointerEvent) {
    if (drag.current?.id !== event.pointerId) return;
    drag.current = null;
    setFixed(undefined);
  }

  function nudge(event: KeyboardEvent, edges: number[]) {
    if (!size || disabled) return;
    const deltas: Record<string, number[]> = { ArrowLeft: [1, -1, 0, 0], ArrowRight: [-1, 1, 0, 0],
      ArrowUp: [0, 0, 1, -1], ArrowDown: [0, 0, -1, 1] };
    const delta = deltas[event.key];
    if (!delta) return;
    event.preventDefault();
    const pads: Pads = [...layout.pads];
    edges.forEach((index) => { pads[index] += delta[index] * (event.altKey ? 10 : 1); });
    setEdges(pads, edges, symmetric || event.shiftKey);
  }

  const imageStyle = size && geometry ? {
    left: geometry.imageX * scale, top: geometry.imageY * scale,
    width: size.width * geometry.scaleX * scale, height: size.height * geometry.scaleY * scale,
  } : undefined;
  return <section className={styles.board}>
    <header className={styles.boardHeader}>
      <div>
        <strong>{t('outpaint.canvas')}</strong>
        {geometry && <output aria-label={t('outpaint.outputSize')}>{geometry.outputWidth} × {geometry.outputHeight}</output>}
      </div>
      <div className={styles.actions}>
        <Button variant="ghost" size="sm" type="button" iconOnly icon={<Minus size={16} />} aria-label={t('portrait.zoomOut')}
          disabled={zoom <= 0.25} onClick={() => setZoom((value) => Math.max(0.25, value / 1.25))} />
        <output aria-label={t('outpaint.zoom')}>{Math.round(zoom * 100)}%</output>
        <Button variant="ghost" size="sm" type="button" iconOnly icon={<Plus size={16} />} aria-label={t('portrait.zoomIn')}
          disabled={zoom >= 3} onClick={() => setZoom((value) => Math.min(3, value * 1.25))} />
        <Button variant="ghost" size="sm" type="button" iconOnly icon={<Focus size={16} />} aria-label={t('outpaint.fit')}
          onClick={() => { setZoom(1); setPan(center); }} />
        <Button variant="ghost" size="sm" type="button" iconOnly icon={<Move size={16} />} aria-label={t('outpaint.pan')}
          aria-pressed={panning} onClick={() => setPanning((value) => !value)} />
        <Button variant="ghost" size="sm" type="button" iconOnly icon={<RotateCcw size={16} />} aria-label={t('outpaint.reset')}
          data-tooltip={t('outpaint.reset')} disabled={disabled || !size} onClick={() => {
            if (size) setEdges(initialLayout.pads, [], false);
            setZoom(1);
            setPan(center);
          }} />
      </div>
    </header>
    <div ref={stage} className={styles.stage} data-panning={panning}
      onPointerDown={(event) => { if (panning || event.button === 1) start(event); }}
      onPointerMove={move} onPointerUp={finish} onPointerCancel={finish} onLostPointerCapture={finish}>
      {!imageStyle && <img className={styles.loader} src={image} alt="" onLoad={(event) => onSize({
        width: event.currentTarget.naturalWidth, height: event.currentTarget.naturalHeight,
      })} />}
      {size && geometry && <div className={styles.frame}
        style={{ width: geometry.outputWidth * scale, height: geometry.outputHeight * scale,
          background: layout.color, transform: fixed
            ? `translate(${fixed.imageOrigin.x - geometry.imageX * scale}px, ${fixed.imageOrigin.y - geometry.imageY * scale}px)`
            : `translate(calc(-50% + ${pan.x}px), calc(-50% + ${pan.y}px))` }}
        data-outpaint-frame>
        <div className={styles.content}>
          <div className={styles.image} style={imageStyle} data-movable={!disabled && !panning} onPointerDown={(event) => start(event)}>
            <img src={image} alt={t('photoTools.original')} draggable={false} onLoad={(event) => {
              const { naturalWidth, naturalHeight } = event.currentTarget;
              if (size.width !== naturalWidth || size.height !== naturalHeight) onSize({ width: naturalWidth, height: naturalHeight });
            }} />
            {maskPreview && <div className={styles.mask} style={{ background: layout.color, maskImage: `url(${maskPreview})` }} />}
          </div>
        </div>
        {!panning && handles.map(({ name, edges }) => <button key={name} className={styles.handle} data-side={name}
          type="button" aria-label={t(`outpaint.edge.${name}`)} disabled={disabled}
          onPointerDown={(event) => start(event, edges)} onKeyDown={(event) => nudge(event, edges)}>
          {edges.length === 1 && <span>{layout.unit === 'percent'
            ? `${Math.round(layout.pads[edges[0]] * 100 / edgeBase(size, edges[0]))}%` : layout.pads[edges[0]]}</span>}
        </button>)}
      </div>}
    </div>
    <footer className={styles.footer}>
      <span>{t(panning ? 'outpaint.panHint' : 'outpaint.dragHint')}</span>
      <ToggleField label={t('outpaint.symmetric')} checked={symmetric} onChange={setSymmetric} disabled={disabled} />
    </footer>
  </section>;
}

export function OutpaintSettings({ layout, size, disabled, mask, onChange, onMask }: {
  layout: OutpaintLayout; size: ImageSize | undefined; disabled: boolean; mask: boolean;
  onChange: (value: OutpaintLayout) => void; onMask: () => void;
}) {
  const { t } = useTranslation();
  const unit = layout.unit === 'percent' ? '%' : 'px';
  const patch = (settings: Partial<OutpaintLayout>) => onChange({ ...layout, ...settings });
  return <>
    <Choice label={t('outpaint.ratio')} value={layout.ratio} disabled={disabled || !size}
      options={aspectRatios.map((value) => ({ value, label: value.includes(':') ? value : t(`outpaint.${value}`) }))}
      onChange={(ratio) => { if (size) patch({ ratio, translated: false, pads: constrainPads(layout.pads, size, ratio) }); }} />
    <div className={styles.units}><span>{t('outpaint.edges')}</span>
      <Segments label={t('outpaint.unit')} value={layout.unit} onChange={(value) => patch({ unit: value })}
        options={[{ value: 'percent', label: '%', disabled }, { value: 'pixels', label: 'px', disabled }]} />
    </div>
    <div className={styles.edges}>{sides.map((side, index) => {
      const base = size ? edgeBase(size, index) : 1;
      const value = layout.unit === 'pixels' ? layout.pads[index] : Math.round(layout.pads[index] * 100 / base);
      return <NumberField key={side} label={`${t(`outpaint.edge.${side}`)} (${unit})`} value={value}
        min={-3000} max={3000} disabled={disabled || !size}
        onChange={(next) => {
          if (!size) return;
          const pads: Pads = [...layout.pads];
          pads[index] = Math.trunc(layout.unit === 'pixels' ? next : base * next / 100);
          patch({ translated: false, pads: constrainPads(pads, size, layout.ratio, [index]) });
        }} />;
    })}</div>
    <Button type="button" variant="secondary" size="sm" icon={mask ? <Crop size={16} /> : <ScanLine size={16} />}
      aria-pressed={mask} onClick={onMask}>{t(mask ? 'outpaint.showCanvas' : 'outpaint.editMask')}</Button>
  </>;
}

export function OutpaintOutputSettings({ layout, onChange, disabled }: {
  layout: OutpaintLayout; disabled: boolean; onChange: (value: OutpaintLayout) => void;
}) {
  const { t } = useTranslation();
  const patch = (settings: Partial<OutpaintLayout>) => onChange({ ...layout, ...settings });
  return <>
    <NumberField label={t('outpaint.outputEdge')} value={layout.outputEdge} min={0} max={8192} step={128} disabled={disabled}
      onChange={(value) => patch({ outputEdge: Math.round(value) })} />
    {layout.outputEdge === 0 && <small>{t('outpaint.unlimitedOutput')}</small>}
    <Choice label={t('outpaint.multiple')} value={layout.multiple} disabled={disabled}
      options={[0, 8, 16, 32, 64].map((value) => ({ value: String(value), label: value ? String(value) : t('outpaint.noMultiple') }))}
      onChange={(value) => patch({ multiple: Number(value) })} />
    <label className={styles.color}>{t('outpaint.fillColor')}
      <span>{layout.color.toUpperCase()} <input type="color" value={layout.color} disabled={disabled}
        onChange={(event) => patch({ color: event.currentTarget.value })} /></span>
    </label>
  </>;
}
