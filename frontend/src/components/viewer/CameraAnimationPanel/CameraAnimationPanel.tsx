import { useCallback, useEffect, useRef, useState } from 'react';
import type { RefObject } from 'react';
import * as THREE from 'three';
import { ArrowDown, ArrowUp, Camera, Download, Film, Focus, FolderOpen, Pause, Play, Plus, RefreshCw, Route, Save, Trash2, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/common/Button';
import type { ViewerContext } from '@/hooks/useViewer';
import { animationDuration, applyCameraPose, CAMERA_ANIMATION_CURVES, captureCameraPose, MAX_KEYFRAMES, parseCameraAnimation, sampleCameraAnimation } from '@/utils/cameraAnimation';
import type { CameraAnimationCurve, CameraAnimationProject, CameraKeyframe } from '@/utils/cameraAnimation';
import { exportCameraAnimation } from '@/utils/cameraAnimationExport';
import { useCameraPathOverview } from '@/hooks/useCameraPathOverview';
import styles from './CameraAnimationPanel.module.css';

interface CameraAnimationPanelProps {
  open: boolean;
  viewerRef: RefObject<ViewerContext | null>;
  portrait: boolean;
  onPortraitChange: (portrait: boolean) => void;
  onClose: () => void;
}

const knownErrors = new Set(['animationInvalidProject', 'animationLimits', 'animationCodecUnavailable',
  'animationEncodeFailed', 'animationMemoryLimit', 'animationFullModelRequired']);
const curveSuffix: Record<CameraAnimationCurve, string> = {
  cinematic: 'Cinematic', smooth: 'Smooth', sine: 'Sine', quintic: 'Quintic', linear: 'Linear',
};

export function CameraAnimationPanel({ open, viewerRef, portrait, onPortraitChange, onClose }: CameraAnimationPanelProps) {
  const { t } = useTranslation();
  const [frames, setFrames] = useState<CameraKeyframe[]>([]);
  const [thumbnails, setThumbnails] = useState<Record<string, string>>({});
  const [selected, setSelected] = useState<string | null>(null);
  const [easing, setEasing] = useState<CameraAnimationCurve>('cinematic');
  const [resolution, setResolution] = useState(1080);
  const [fps, setFps] = useState(30);
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState('');
  const [resultUrl, setResultUrl] = useState('');
  const [showOverview, setShowOverview] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const duration = animationDuration(frames);
  const locked = busy || playing;
  const width = portrait ? resolution : Math.round(resolution * 16 / 9);
  const height = portrait ? Math.round(resolution * 16 / 9) : resolution;
  const project: CameraAnimationProject = { version: 1, frames, easing, portrait };

  const stop = useCallback(() => {
    const ctx = viewerRef.current;
    if (ctx?.cameraPlayback) {
      ctx.cameraPlayback = undefined;
      // Align OrbitControls with the actual interpolated quaternion, avoiding a snap.
      const distance = Math.max(0.001, ctx.camera.position.distanceTo(ctx.controls.target));
      ctx.controls.target.copy(ctx.camera.position).addScaledVector(ctx.camera.getWorldDirection(new THREE.Vector3()), distance);
      ctx.controls.enabled = !ctx.cameraOverview;
    }
    setPlaying(false);
  }, [viewerRef]);

  useEffect(() => {
    if (!open) return;
    const ctx = viewerRef.current;
    if (!ctx) return;
    const saved = {
      pose: captureCameraPose(ctx.camera, ctx.controls.target), up: ctx.camera.up.clone(),
      enabled: ctx.controls.enabled, autoRotate: ctx.controls.autoRotate, damping: ctx.controls.enableDamping,
      minAzimuth: ctx.controls.minAzimuthAngle, maxAzimuth: ctx.controls.maxAzimuthAngle,
      minPolar: ctx.controls.minPolarAngle, maxPolar: ctx.controls.maxPolarAngle,
      minDistance: ctx.controls.minDistance, maxDistance: ctx.controls.maxDistance,
    };
    ctx.animationActive = true;
    ctx.controls.autoRotate = false;
    ctx.controls.enableDamping = false;
    ctx.controls.update(); // Drain residual orbit motion before recording.
    ctx.controls.minAzimuthAngle = -Infinity; ctx.controls.maxAzimuthAngle = Infinity;
    ctx.controls.minPolarAngle = 0; ctx.controls.maxPolarAngle = Math.PI;
    ctx.controls.minDistance = 0.001; ctx.controls.maxDistance = Infinity;
    return () => {
      abortRef.current?.abort();
      ctx.cameraPlayback = undefined; ctx.animationActive = false;
      if (ctx.disposed) return;
      applyCameraPose(ctx.camera, ctx.controls.target, saved.pose); ctx.camera.up.copy(saved.up);
      Object.assign(ctx.controls, { enabled: saved.enabled, autoRotate: saved.autoRotate, enableDamping: saved.damping,
        minAzimuthAngle: saved.minAzimuth, maxAzimuthAngle: saved.maxAzimuth,
        minPolarAngle: saved.minPolar, maxPolarAngle: saved.maxPolar,
        minDistance: saved.minDistance, maxDistance: saved.maxDistance });
    };
  }, [open, viewerRef]);

  // Set up the panel snapshot before the overview temporarily disables its controls.
  const overview = useCameraPathOverview(viewerRef, open && showOverview, frames, easing, portrait, selected);

  useEffect(() => () => { if (resultUrl) URL.revokeObjectURL(resultUrl); }, [resultUrl]);
  useEffect(() => {
    if (!playing) return;
    const hidden = () => { if (document.hidden) stop(); };
    document.addEventListener('visibilitychange', hidden);
    return () => document.removeEventListener('visibilitychange', hidden);
  }, [playing, stop]);
  useEffect(() => {
    if (!busy) return;
    const beforeUnload = (event: BeforeUnloadEvent) => { event.preventDefault(); };
    window.addEventListener('beforeunload', beforeUnload);
    return () => window.removeEventListener('beforeunload', beforeUnload);
  }, [busy]);

  const invalidate = () => { setResultUrl(''); setError(''); };
  const capture = (replaceId?: string) => {
    const ctx = viewerRef.current;
    if (!ctx || !ctx.splatMesh || ctx.cameraOverview || (!replaceId && frames.length >= MAX_KEYFRAMES)) return;
    const id = replaceId ?? `shot-${Date.now()}-${frames.length}`;
    const pose = captureCameraPose(ctx.camera, ctx.controls.target);
    if (replaceId) setFrames(previous => previous.map(frame => frame.id === id ? { ...frame, ...pose } : frame));
    else setFrames(previous => [...previous, { ...pose, id, seconds: 3 }]);
    setSelected(id); invalidate();
    ctx.renderer.render(ctx.scene, ctx.camera);
    const thumbnail = document.createElement('canvas'); thumbnail.width = 160; thumbnail.height = 90;
    thumbnail.getContext('2d')?.drawImage(ctx.renderer.domElement, 0, 0, 160, 90);
    setThumbnails(previous => ({ ...previous, [id]: thumbnail.toDataURL('image/jpeg', 0.75) }));
  };

  const seek = (seconds: number) => {
    stop();
    const ctx = viewerRef.current;
    const pose = sampleCameraAnimation(frames, seconds, easing);
    if (ctx && pose) applyCameraPose(ctx.camera, ctx.controls.target, pose);
    setTime(seconds);
  };
  const play = () => {
    const ctx = viewerRef.current;
    if (!ctx || frames.length < 2 || duration > 120) return;
    setError('');
    const start = performance.now() - (time >= duration ? 0 : time) * 1000;
    let lastUi = 0;
    ctx.controls.enabled = false;
    ctx.cameraPlayback = now => {
      const seconds = Math.min(duration, (now - start) / 1000);
      const pose = sampleCameraAnimation(frames, seconds, easing)!;
      applyCameraPose(ctx.camera, ctx.controls.target, pose);
      if (now - lastUi > 50 || seconds >= duration) { setTime(seconds); lastUi = now; }
      if (seconds >= duration) stop();
    };
    setPlaying(true);
  };
  const move = (index: number, delta: number) => {
    setFrames(previous => {
      const next = [...previous]; [next[index], next[index + delta]] = [next[index + delta], next[index]]; return next;
    }); invalidate(); setTime(0);
  };
  const saveProject = () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(project, null, 2)], { type: 'application/json' }));
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = 'camera-animation.json'; anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  const loadProject = async (file?: File) => {
    if (!file) return;
    try {
      if (file.size > 1024 * 1024) throw new Error('animationInvalidProject');
      const parsed = parseCameraAnimation(JSON.parse(await file.text()));
      stop(); setFrames(parsed.frames); setEasing(parsed.easing); onPortraitChange(parsed.portrait);
      const ctx = viewerRef.current;
      if (ctx && parsed.frames[0]) applyCameraPose(ctx.camera, ctx.controls.target, parsed.frames[0]);
      setThumbnails({}); setSelected(parsed.frames[0]?.id ?? null); setTime(0); invalidate();
    } catch { setError('animationInvalidProject'); }
  };
  const exportVideo = async () => {
    const ctx = viewerRef.current;
    if (!ctx) return;
    stop(); setBusy(true); setError(''); setResultUrl(''); setProgress(0);
    const abort = new AbortController(); abortRef.current = abort;
    try {
      const blob = await exportCameraAnimation(ctx, project, width, height, fps, abort.signal, setProgress);
      if (!abort.signal.aborted && !ctx.disposed) setResultUrl(URL.createObjectURL(blob));
    } catch (caught) {
      if (!abort.signal.aborted && !ctx.disposed) setError(caught instanceof Error && knownErrors.has(caught.message) ? caught.message : 'animationEncodeFailed');
    } finally {
      if (!ctx.disposed) setBusy(false);
      abortRef.current = null;
    }
  };

  if (!open) return null;
  return (
    <>
      <aside className={styles.panel} aria-label={t('animationTitle')} data-camera-animation="true">
        <header className={styles.header}>
          <div><span className={styles.eyebrow}>SHARP GUI</span><h2><Film size={20} />{t('animationTitle')}</h2></div>
          <Button variant="ghost" iconOnly icon={<X size={19} />} aria-label={t('animationClose')} disabled={busy} onClick={() => { stop(); onClose(); }} />
        </header>
        <div className={styles.scroll}>
          <div className={styles.viewMode} role="group" aria-label={t('animationViewMode')}>
            <Button variant={showOverview ? 'ghost' : 'secondary'} size="sm" icon={<Camera size={15} />} aria-pressed={!showOverview} disabled={busy} onClick={() => setShowOverview(false)}>{t('animationShotView')}</Button>
            <Button variant={showOverview ? 'secondary' : 'ghost'} size="sm" icon={<Route size={15} />} aria-pressed={showOverview} disabled={busy} onClick={() => setShowOverview(true)}>{t('animationPathView')}</Button>
          </div>
          <p className={styles.hint}>{t(showOverview ? 'animationPathHint' : 'animationHint')}</p>
          {showOverview && <div className={styles.pathLegend}>
            <span><i />{t('animationPathKeyframes')}</span><span><i className={styles.currentCamera} />{t('animationPathCurrent')}</span>
            <Button variant="ghost" size="sm" icon={<Focus size={15} />} disabled={busy} onClick={overview.fit}>{t('animationPathFit')}</Button>
          </div>}
          <fieldset disabled={locked} className={styles.fieldset}>
            <div className={styles.sectionTitle}><h3>{t('animationKeyframes')}</h3><span>{frames.length} / {MAX_KEYFRAMES}</span></div>
            <Button variant="secondary" icon={<Plus size={16} />} onClick={() => capture()} disabled={showOverview || frames.length >= MAX_KEYFRAMES} className={styles.add}>{t('animationAdd')}</Button>
            {!frames.length && <div className={styles.empty}><Camera size={25} /><p>{t('animationEmpty')}</p></div>}
            <ol className={styles.frames}>
              {frames.map((frame, index) => (
                <li key={frame.id} className={selected === frame.id ? styles.selected : ''}>
                  <button className={styles.frame} onClick={() => {
                    const ctx = viewerRef.current;
                    if (ctx) applyCameraPose(ctx.camera, ctx.controls.target, frame);
                    setSelected(frame.id); setTime(animationDuration(frames.slice(0, index + 1)));
                  }} aria-label={t('animationGoFrame', { index: index + 1 })}>
                    {thumbnails[frame.id] ? <img src={thumbnails[frame.id]} alt="" /> : <span className={styles.frameIcon}><Camera size={19} /></span>}
                    <span><strong>{t('animationFrame', { index: index + 1 })}</strong><small>{animationDuration(frames.slice(0, index + 1)).toFixed(1)} s</small></span>
                  </button>
                  <div className={styles.frameActions}>
                    <Button variant="ghost" size="sm" iconOnly icon={<RefreshCw size={14} />} aria-label={t('animationReplace')} disabled={showOverview} onClick={() => capture(frame.id)} />
                    <Button variant="ghost" size="sm" iconOnly icon={<ArrowUp size={14} />} aria-label={t('animationEarlier')} disabled={index === 0} onClick={() => move(index, -1)} />
                    <Button variant="ghost" size="sm" iconOnly icon={<ArrowDown size={14} />} aria-label={t('animationLater')} disabled={index === frames.length - 1} onClick={() => move(index, 1)} />
                    <Button variant="ghost" size="sm" iconOnly icon={<Trash2 size={14} />} aria-label={t('animationDelete')} onClick={() => {
                      setFrames(previous => previous.filter(item => item.id !== frame.id));
                      setThumbnails(previous => Object.fromEntries(Object.entries(previous).filter(([id]) => id !== frame.id)));
                      invalidate(); setTime(0);
                    }} />
                  </div>
                  {index > 0 && <label className={styles.seconds}>{t('animationTransition')}<input type="number" min="0.1" max="60" step="0.1" value={frame.seconds} onChange={event => {
                    const seconds = event.target.valueAsNumber;
                    if (Number.isFinite(seconds)) { setFrames(previous => previous.map(item => item.id === frame.id ? { ...item, seconds: Math.min(60, Math.max(0.1, seconds)) } : item)); invalidate(); }
                  }} /><span>s</span></label>}
                </li>
              ))}
            </ol>
            <div className={styles.projectActions}>
              <Button variant="ghost" size="sm" icon={<Save size={15} />} disabled={!frames.length} onClick={saveProject}>{t('animationSave')}</Button>
              <Button variant="ghost" size="sm" icon={<FolderOpen size={15} />} onClick={() => fileRef.current?.click()}>{t('animationLoad')}</Button>
              <input ref={fileRef} type="file" accept=".json,application/json" hidden onChange={event => { void loadProject(event.target.files?.[0]); event.target.value = ''; }} />
            </div>
            <h3 className={styles.settingsTitle}>{t('animationOutput')}</h3>
            <div className={styles.settings}>
              <label>{t('animationAspect')}<select value={String(portrait)} onChange={event => { onPortraitChange(event.target.value === 'true'); invalidate(); }}><option value="false">{t('animationLandscape')}</option><option value="true">{t('animationPortrait')}</option></select></label>
              <label>{t('animationResolution')}<select value={resolution} onChange={event => { setResolution(Number(event.target.value)); invalidate(); }}><option value="1080">1080p</option><option value="2160">4K</option></select></label>
              <label>{t('animationFps')}<select value={fps} onChange={event => { setFps(Number(event.target.value)); invalidate(); }}>{[24, 30, 60].map(value => <option key={value} value={value}>{value} fps</option>)}</select></label>
              <label>{t('animationEasing')}<select value={easing} onChange={event => { setEasing(event.target.value as CameraAnimationCurve); invalidate(); }}>{CAMERA_ANIMATION_CURVES.map(curve => <option key={curve} value={curve}>{t(`animationCurve${curveSuffix[curve]}`)}</option>)}</select></label>
            </div>
            <div className={styles.curvePreview}>
              <svg viewBox="0 0 80 44" aria-hidden="true"><path className={styles.curveGuide} d="M4 4V40H76" /><path d={easing === 'linear' ? 'M4 40L76 4' : easing === 'cinematic' ? 'M4 40C20 40 23 28 40 22S60 4 76 4' : easing === 'sine' ? 'M4 40C28 40 52 4 76 4' : easing === 'quintic' ? 'M4 40C42 40 38 4 76 4' : 'M4 40C35 40 45 4 76 4'} /></svg>
              <p>{t(`animationCurveHint${curveSuffix[easing]}`)}</p>
            </div>
          </fieldset>
          <p className={styles.hint}>{t('animationExportHint', { width, height, fps })}</p>
          {duration > 120 && <p className={styles.error} role="alert">{t('animationLimits')}</p>}
          {error && <p className={styles.error} role="alert">{t(error)}</p>}
          {busy && <div className={styles.progress} aria-live="polite"><label>{t('animationRendering')}<span>{Math.round(progress * 100)}%</span></label><progress max="1" value={progress} /><Button variant="secondary" size="sm" onClick={() => abortRef.current?.abort()}>{t('animationCancel')}</Button></div>}
          {resultUrl && <a className={styles.download} href={resultUrl} download="camera-animation.webm"><Download size={17} />{t('animationDownload')}</a>}
        </div>
        <footer><span>{t('animationSummary', { count: frames.length, seconds: duration.toFixed(1) })}</span><Button icon={<Download size={16} />} disabled={locked || frames.length < 2 || duration > 120} onClick={() => void exportVideo()}>{t('animationExport')}</Button></footer>
      </aside>
      <div className={styles.playback}>
        <Button variant="secondary" iconOnly icon={playing ? <Pause size={19} /> : <Play size={19} />} aria-label={t(playing ? 'animationPause' : 'animationPlay')} disabled={busy || frames.length < 2 || duration > 120} onClick={playing ? stop : play} />
        <span>{time.toFixed(1)} / {duration.toFixed(1)} s</span>
        <input type="range" aria-label={t('animationTimeline')} min="0" max={duration || 1} step="0.01" value={Math.min(time, duration)} disabled={busy || frames.length < 2} onChange={event => seek(Number(event.target.value))} />
      </div>
      {busy && <div className={styles.blocker} aria-hidden="true" />}
    </>
  );
}
