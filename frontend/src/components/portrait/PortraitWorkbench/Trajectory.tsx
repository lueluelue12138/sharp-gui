import { useEffect, useRef, useState } from 'react';

import { useTranslation } from 'react-i18next';

import { Button } from '@/components/common/Button';
import { Choice, NumberField } from '@/components/portrait/WorkbenchControls';
import { blendViews } from '@/components/portrait/PortraitWorkbench/portraitRenderer';
import type { CameraView } from '@/components/portrait/PortraitWorkbench/portraitRenderer';
import { usePortraitDownload } from '@/components/portrait/PortraitWorkbench/usePortraitDownload';
import type { PortraitFrame } from '@/types/portrait';
import styles from '@/components/portrait/PortraitWorkbench/PortraitWorkbench.module.css';

interface TrajectoryProps {
  view: CameraView | null;
  disabled: boolean;
  onView: (view: CameraView) => void;
  onExport: (frames: Array<{ view: CameraView; keyframe: boolean }>, mode: 'preview' | 'repair') => Promise<void>;
  onStop: () => void;
  exporting: boolean;
  results: PortraitFrame[];
}

export function Trajectory({ view, disabled, onView, onExport, onStop, exporting, results }: TrajectoryProps) {
  const { t } = useTranslation();
  const { download, downloading, downloadFailed } = usePortraitDownload();
  const [frames, setFrames] = useState<CameraView[]>([]);
  const [selected, setSelected] = useState(0);
  const [between, setBetween] = useState(0);
  const [mode, setMode] = useState<'preview' | 'repair'>('preview');
  const [playing, setPlaying] = useState(false);
  const animation = useRef(0);
  const count = frames.length + Math.max(0, frames.length - 1) * between;
  const locked = disabled || playing || !view;
  const manifest = results.at(-1)?.manifest;

  useEffect(() => () => cancelAnimationFrame(animation.current), []);

  function play() {
    if (playing) {
      cancelAnimationFrame(animation.current);
      setPlaying(false);
      return;
    }
    setPlaying(true);
    const start = performance.now();
    function draw(now: number) {
      const position = (now - start) / 1300;
      const index = Math.floor(position);
      if (index >= frames.length - 1) {
        onView(frames[frames.length - 1]);
        setPlaying(false);
      } else {
        onView(blendViews(frames[index], frames[index + 1], position - index));
        animation.current = requestAnimationFrame(draw);
      }
    }
    animation.current = requestAnimationFrame(draw);
  }

  function reorder(offset: number) {
    const target = selected + offset;
    const next = [...frames];
    [next[target], next[selected]] = [next[selected], next[target]];
    setFrames(next);
    setSelected(target);
  }

  function exportFrames() {
    const samples = [{ view: frames[0], keyframe: true }];
    for (let index = 1; index < frames.length; index += 1) {
      for (let step = 1; step <= between; step += 1) {
        samples.push({ view: blendViews(frames[index - 1], frames[index], step / (between + 1)), keyframe: false });
      }
      samples.push({ view: frames[index], keyframe: true });
    }
    void onExport(samples, mode);
  }

  return <div className={styles.trajectoryPanel}>
    <div className={styles.controlRow}>
      <Button variant="secondary" size="sm" type="button" disabled={locked || frames.length >= 240} onClick={() => {
        if (view) { setFrames([...frames, view]); setSelected(frames.length); }
      }}>{t('portrait.addFrame')}</Button>
      <Choice label={t('portrait.keyframe')} value={selected} disabled={locked || !frames.length}
        options={frames.length ? frames.map((_, index) => ({ value: String(index), label: t('portrait.frameNumber', { count: index + 1 }) })) : [{ value: '0', label: t('portrait.noFrames') }]}
        onChange={(value) => { const index = Number(value); setSelected(index); onView(frames[index]); }} />
    </div>
    <div className={styles.controlRow}>
      <Button variant="secondary" size="sm" type="button" aria-label={t('portrait.frameEarlier')} disabled={locked || selected <= 0} onClick={() => reorder(-1)}>←</Button>
      <Button variant="secondary" size="sm" type="button" aria-label={t('portrait.frameLater')} disabled={locked || selected >= frames.length - 1} onClick={() => reorder(1)}>→</Button>
      <Button variant="secondary" size="sm" type="button" disabled={locked || !frames.length} onClick={() => {
        if (view) setFrames(frames.map((frame, index) => index === selected ? view : frame));
      }}>{t('portrait.replaceFrame')}</Button>
      <Button variant="secondary" size="sm" type="button" disabled={locked || !frames.length} onClick={() => {
        setFrames(frames.filter((_, index) => index !== selected)); setSelected(Math.max(0, Math.min(selected, frames.length - 2)));
      }}>{t('portrait.deleteFrame')}</Button>
      <Button variant="secondary" size="sm" type="button" disabled={disabled || frames.length < 2} onClick={play}>{t(playing ? 'portrait.stop' : 'portrait.play')}</Button>
    </div>
    <div className={styles.controlRow}>
      <NumberField label={t('portrait.between')} min={0} max={239} value={between} disabled={locked} onChange={(value) => setBetween(Math.floor(value))} />
      <Choice label={t('portrait.exportMode')} value={mode} disabled={locked} onChange={(value) => setMode(value === 'repair' ? 'repair' : 'preview')}
        options={[{ value: 'preview', label: t('portrait.rough') }, { value: 'repair', label: t('portrait.repaired') }]} />
    </div>
    <div className={styles.controlRow}>
      <Button variant="secondary" size="sm" type="button" disabled={locked || !count || count > 240} onClick={exportFrames}>{t('portrait.exportFrames', { count })}</Button>
      {exporting && <Button variant="secondary" size="sm" type="button" onClick={onStop}>{t('portrait.stopAfterFrame')}</Button>}
      {count > 240 && <small>{t('portrait.frameLimit')}</small>}
    </div>
    {manifest && <div className={styles.frameDownloads}>
      <Button variant="secondary" size="sm" type="button" className={styles.downloadButton}
        disabled={downloading !== null} aria-busy={downloading === manifest}
        onClick={() => void download(manifest, 'transforms.json', 'application/json')}>
        {downloading === manifest ? t('downloading') : 'transforms.json'}
      </Button>
      {results.map((frame, index) => (
        <Button key={frame.image} variant="secondary" size="sm" type="button" className={styles.downloadButton}
          disabled={downloading !== null} aria-busy={downloading === frame.image}
          onClick={() => void download(frame.image, `frame-${index + 1}.png`)}>
          {downloading === frame.image ? t('downloading') : t('portrait.frameNumber', { count: index + 1 })}
        </Button>
      ))}
    </div>}
    {downloadFailed && <p className={styles.downloadError} role="alert">{t('portrait.downloadFailed')}</p>}
  </div>;
}
