import { useEffect, useRef, useState } from 'react';
import { Box, CircleHelp, Expand, Focus, Layers, Maximize, Move, Pause, RotateCcw, RotateCw, X } from 'lucide-react';

import { Button } from '@/components/common/Button';
import { createShareScene } from '@/share/scene';
import type { ShareScene } from '@/share/scene';
import type { ShareManifest, ShareStage } from '@/share/types';
import { shareViewer as en } from '@/i18n/en.json';
import { shareViewer as zh } from '@/i18n/zh.json';
import styles from './ShareViewer.module.css';

interface ShareViewerProps { manifest: ShareManifest; encoded: string; name: string }

export function ShareViewer({ manifest, encoded, name }: ShareViewerProps) {
  const canvasRef = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<ShareScene | null>(null);
  const [language, setLanguage] = useState<'en' | 'zh'>(() => navigator.language.toLowerCase().startsWith('zh') ? 'zh' : 'en');
  const text = language === 'zh' ? zh : en;
  const [status, setStatus] = useState<{ stage: ShareStage; value: number; count: number; error: string | null }>({ stage: 'preparing', value: 0, count: 0, error: null });
  const [attempt, setAttempt] = useState(0);
  const [autoRotate, setAutoRotate] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [moveOpen, setMoveOpen] = useState(false);
  const [background, setBackground] = useState(0);
  const [fullscreen, setFullscreen] = useState(false);
  const [stick, setStick] = useState({ x: 0, y: 0 });
  const [fullscreenFailed, setFullscreenFailed] = useState(false);
  const ready = status.stage === 'ready' && !status.error;

  useEffect(() => {
    document.documentElement.lang = language;
    canvasRef.current?.querySelector('canvas')?.setAttribute('aria-label', text.title);
  }, [language, text.title, status.stage]);

  useEffect(() => {
    let cancelled = false;
    let instance: ShareScene | null = null;
    void (async () => {
      try {
        instance = createShareScene(canvasRef.current!, manifest, encoded,
          (stage, value) => { if (!cancelled) setStatus((current) => ({ ...current, stage, value })); },
          () => { if (!cancelled) setStatus((current) => ({ ...current, error: 'context-lost' })); },
          () => { if (!cancelled) setAutoRotate(false); });
        sceneRef.current = instance;
        const count = await instance.ready;
        if (!cancelled) setStatus({ stage: 'ready', value: 100, count, error: null });
      } catch (error) {
        if (!cancelled) {
          instance?.dispose();
          setStatus((current) => ({ ...current, error: error instanceof Error ? error.message : 'Unknown error' }));
        }
      }
    })();
    return () => { cancelled = true; instance?.dispose(); sceneRef.current = null; };
  }, [attempt, manifest, encoded]);

  useEffect(() => {
    const changed = () => setFullscreen(Boolean(document.fullscreenElement));
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') setHelpOpen(false); };
    document.addEventListener('fullscreenchange', changed);
    document.addEventListener('keydown', escape);
    return () => { document.removeEventListener('fullscreenchange', changed); document.removeEventListener('keydown', escape); };
  }, []);

  const toggleFullscreen = async () => {
    setFullscreenFailed(false);
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await document.documentElement.requestFullscreen();
    } catch { setFullscreenFailed(true); }
  };
  const stopStick = () => { sceneRef.current?.move(0, 0); setStick({ x: 0, y: 0 }); };
  const stopMotion = () => { setAutoRotate(false); sceneRef.current?.setAutoRotate(false); stopStick(); };
  const retry = () => { stopMotion(); setStatus({ stage: 'preparing', value: 0, count: 0, error: null }); setAttempt((current) => current + 1); };
  const source = manifest.sourceMediaType === 'video' ? text.sourceVideo : manifest.sourceMediaType === 'image' ? text.sourceImage : text.sourceUnknown;
  const action = (callback: () => void) => { stopMotion(); callback(); };
  return (
    <main className={`${styles.viewer} ${background === 1 ? styles.black : background === 2 ? styles.light : ''}`}>
      <div ref={canvasRef} className={styles.canvas} />
      <header className={styles.header}>
        <div className={styles.title}>
          <Box size={20} aria-hidden="true" />
          <div><span>SHARP GUI</span><h1 title={name}>{name}</h1></div>
        </div>
        <div className={styles.headerActions}>
          <Button variant="ghost" size="sm" onClick={() => setLanguage(language === 'zh' ? 'en' : 'zh')} aria-label={language === 'zh' ? 'English' : '中文'}>{language === 'zh' ? 'EN' : '中文'}</Button>
          <Button variant="ghost" iconOnly icon={<CircleHelp />} aria-label={text.help} title={text.help} aria-expanded={helpOpen} onClick={() => setHelpOpen(!helpOpen)} />
        </div>
      </header>
      {!ready && <div className={styles.loading} role={status.error ? 'alert' : 'status'} aria-live="polite">
        <div className={styles.loadingCard}>
          <Box size={28} aria-hidden="true" />
          <h2>{status.error ? text.failed : text[status.stage]}</h2>
          {status.error ? <>
            <p>{status.error === 'context-lost' ? text.contextLost : text.loadReason}</p>
            {status.error !== 'context-lost' && <details><summary>{text.technicalDetails}</summary><p>{status.error}</p></details>}
            <p>{text.errorHint}</p>
            <Button onClick={retry} icon={<RotateCcw size={16} />}>{text.retry}</Button>
          </> : <><progress max={100} value={status.value} aria-label={text[status.stage]} /><p>{Math.round(status.value)}%</p></>}
        </div>
      </div>}
      {ready && <>
        <div className={styles.summary} aria-live="polite"><span className={styles.readyDot} />{source}<span>·</span>{manifest.format.toUpperCase()}<span>·</span>{status.count.toLocaleString()} {text.points}</div>
        <div className={styles.bottom}>
          <nav className={styles.toolbar} aria-label={text.title}>
            <Button variant="ghost" icon={<RotateCcw />} onClick={() => action(() => sceneRef.current?.reset())}>{text.reset}</Button>
            <Button variant="ghost" icon={<Focus />} onClick={() => action(() => sceneRef.current?.fit())}>{text.fit}</Button>
            <Button variant="ghost" icon={autoRotate ? <Pause /> : <RotateCw />} aria-pressed={autoRotate} onClick={() => { const next = !autoRotate; setAutoRotate(next); sceneRef.current?.setAutoRotate(next); }}>{autoRotate ? text.pause : text.rotate}</Button>
            <Button variant="ghost" className={styles.moveButton} icon={<Move />} aria-pressed={moveOpen} onClick={() => { stopStick(); setMoveOpen(!moveOpen); }}>{text.move}</Button>
            <div className={styles.utilityActions}>
            <Button variant="ghost" iconOnly icon={<Layers />} aria-label={text.background} title={text.background} onClick={() => setBackground((background + 1) % 3)} />
            {document.fullscreenEnabled && <Button variant="ghost" iconOnly icon={fullscreen ? <Expand /> : <Maximize />} aria-label={fullscreen ? text.exitFullscreen : text.fullscreen} title={fullscreen ? text.exitFullscreen : text.fullscreen} onClick={() => void toggleFullscreen()} />}
            </div>
          </nav>
          <p className={styles.mouseHint}>{text.orbitHint}</p><p className={styles.touchHint}>{text.touchHint}</p>
          {fullscreenFailed && <p role="status">{text.fullscreenUnavailable}</p>}
        </div>
      </>}
      {moveOpen && ready && <div className={styles.movePad} role="group" aria-label={text.moveHint}
        onPointerDown={(event) => { event.currentTarget.setPointerCapture(event.pointerId); }}
        onPointerMove={(event) => {
          if (!event.currentTarget.hasPointerCapture(event.pointerId)) return;
          const box = event.currentTarget.getBoundingClientRect();
          const x = Math.max(-1, Math.min(1, (event.clientX - box.left - box.width / 2) / (box.width / 2 - 16)));
          const y = Math.max(-1, Math.min(1, (event.clientY - box.top - box.height / 2) / (box.height / 2 - 16)));
          setStick({ x, y }); sceneRef.current?.move(x, y);
        }}
        onPointerUp={stopStick} onPointerCancel={stopStick} onLostPointerCapture={stopStick}>
        <Move size={24} style={{ transform: `translate(${stick.x * 24}px, ${stick.y * 24}px)` }} />
      </div>}
      {helpOpen && <aside className={styles.help} role="dialog" aria-label={text.help}>
        <div className={styles.helpHeading}><h2>{text.help}</h2><Button variant="ghost" iconOnly icon={<X />} aria-label={text.close} onClick={() => setHelpOpen(false)} /></div>
        <p>{text.orbitHint}</p><p>{text.touchHint}</p><p>{text.focusHint}</p><p>{text.keyboardHint}</p><p>{text.helpText}</p>
        <p>{text.privacy}</p><p>{text.responsibility}</p>
        <details><summary>{text.licenses}</summary><pre>{document.getElementById('share-licenses')?.textContent}</pre></details>
        <a href="https://github.com/lueluelue12138/sharp-gui" target="_blank" rel="noreferrer">Sharp GUI · GitHub</a>
      </aside>}
    </main>
  );
}
