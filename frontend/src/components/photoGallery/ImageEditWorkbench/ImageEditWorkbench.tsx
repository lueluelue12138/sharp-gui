import { useCallback, useEffect, useRef, useState } from 'react';

import { ArrowLeft, ChevronRight, CloudUpload, ImagePlus, Pencil, Play, RefreshCw, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { ApiError } from '@/api/client';
import { cancelPortraitJob, openGalleryPhoto, portraitAvailability, prepareEditMask, releasePortraitMemory, runPortrait, startPortraitEngine, uploadPortrait } from '@/api/portrait';
import { Button } from '@/components/common/Button';
import { GalleryImagePicker } from '@/components/photoGallery/GalleryImagePicker';
import { ImagePrompt } from '@/components/photoGallery/ImagePrompt';
import { PhotoResultActions } from '@/components/photoGallery/PhotoResultActions';
import { PhotoSourceDownload, PhotoSourcePreview } from '@/components/photoGallery/PhotoSourcePreview';
import { ImageComparison } from '@/components/portrait/PortraitWorkbench/ImageComparison';
import { MaskEditor } from '@/components/portrait/PortraitWorkbench/MaskEditor';
import { BatchCount, BatchNotice, CacheReleaseStatus, PixelChoice, ReleaseCacheButton, Segments, ToggleField, WorkflowProgress } from '@/components/portrait/WorkbenchControls';
import { WorkflowInfo } from '@/components/portrait/WorkflowInfo';
import { useImageDrop, workbenchPhotoAccept } from '@/hooks/useImageDrop';
import { readPortraitDraft, savePortraitDraft } from '@/store/portraitSession';
import type { EnqueuePortraitBatch, ImageEditDraft, PendingPortrait, PortraitDraft, PortraitWorkspaceActions } from '@/store/portraitSession';
import type { PhotoItem } from '@/types/photoGallery';
import type { PhotoTool, PortraitAvailability, PortraitCacheRelease, PortraitProgress, PortraitSourceUpload, PortraitTask, PortraitUpload } from '@/types/portrait';
import { progressPercent } from '@/utils/portraitProgress';

import styles from '@/components/photoGallery/ImageEditWorkbench/ImageEditWorkbench.module.css';
import workbenchStyles from '@/components/portrait/PortraitWorkbench/PortraitWorkbench.module.css';

const sampleEdges = [768, 1024, 1280, 1536, 1920, 2048];
const editNodes: Record<string, string> = {
  '179': 'optimizePrompt', '249': 'prepareEdit', '250': 'prepareEdit', '255': 'prepareEdit', '256': 'decode',
  '247': 'prepareEdit', '252': 'mergeEdit', '274': 'sampling', '361': 'loadModel', '362': 'loadModel',
  '363': 'loadModel', '370': 'save',
};

interface ImageEditWorkbenchProps {
  workspaceId: string;
  active: boolean;
  canGenerate: boolean;
  canClearCache: boolean;
  galleryPhoto?: PhotoItem;
  initialUpload?: PortraitSourceUpload;
  uploadName?: string;
  savedTask?: PortraitTask;
  initialDraft?: PortraitDraft;
  enqueueBatch: EnqueuePortraitBatch;
  onJobSubmitted: (id: string) => void;
  waitForSubmission: boolean;
  onCacheCleared: () => void;
  onBack: () => void;
  onClose: (id: string, fromWorkbench: boolean) => void;
  onChoosePhoto: (file: File) => void;
  onChooseGalleryPhoto: (photo: PhotoItem) => void;
  onTaskUpdate: (task: PortraitTask) => void;
  onContinue: (tool: PhotoTool, image: string, name?: string) => void;
  registerActions: (id: string, actions: PortraitWorkspaceActions) => () => void;
}

function maskBlob(canvas: HTMLCanvasElement) {
  return new Promise<Blob>((resolve, reject) => canvas.toBlob((blob) => {
    if (blob) resolve(blob);
    else reject(new Error('Could not encode the selection.'));
  }, 'image/png'));
}

function editError(problem: unknown) {
  return {
    code: problem instanceof ApiError ? problem.data?.code ?? 'portraitRunError' : 'portraitRunError',
    message: problem instanceof Error ? problem.message : '',
  };
}

export function ImageEditWorkbench({
  workspaceId, active, canGenerate, canClearCache, galleryPhoto, initialUpload, uploadName, savedTask, initialDraft, onCacheCleared,
  onBack, onClose, onChoosePhoto, onChooseGalleryPhoto, onTaskUpdate, onContinue, registerActions, enqueueBatch, onJobSubmitted, waitForSubmission,
}: ImageEditWorkbenchProps) {
  const { t } = useTranslation();
  const [saved] = useState(() => initialDraft ?? readPortraitDraft(workspaceId));
  const [draft, setDraft] = useState(saved);
  const latest = useRef(saved);
  const disposed = useRef(false);
  const controller = useRef<AbortController>(null);
  const referenceRequest = useRef<AbortController>(null);
  const sourceLoading = useRef<Promise<PortraitUpload> | null>(null);
  const resume = useRef<() => void>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const sourceInput = useRef<HTMLInputElement>(null);
  const referenceInput = useRef<HTMLInputElement>(null);
  const [availability, setAvailability] = useState<PortraitAvailability>();
  const [healthVersion, setHealthVersion] = useState(0);
  const [launching, setLaunching] = useState(false);
  const [busy, setBusy] = useState(Boolean(initialUpload || saved.pending));
  const [preparing, setPreparing] = useState(0);
  const [queued, setQueued] = useState(0);
  const [releasing, setReleasing] = useState(false);
  const [cacheRelease, setCacheRelease] = useState<PortraitCacheRelease>();
  const [loadingReference, setLoadingReference] = useState(false);
  const [painted, setPainted] = useState(false);
  const [picker, setPicker] = useState<'source' | 'reference'>();
  const [progress, setProgress] = useState<PortraitProgress>({ state: savedTask?.status === 'queued' ? 'queued' : 'running' });
  const edit = draft.edit ?? {};
  const { prompt = '', area = 'full', edge = 2048, optimize = true, seed = '', page = 'edit', reference, result } = edit;
  const sourceUrl = draft.source?.url ?? galleryPhoto?.full_url ?? galleryPhoto?.preview_url;
  const sourceName = initialUpload?.filename ?? uploadName ?? galleryPhoto?.name ?? t('photoTools.original');
  const locked = busy || releasing || !canGenerate;
  const sourceDrop = useImageDrop(([file]) => onChoosePhoto(file), { enabled: !locked });
  const referenceDrop = useImageDrop(([file]) => pickReference(file), { enabled: !locked && !loadingReference });
  const missingReference = /<image2>/i.test(prompt) && !reference;
  const optimizerMissing = availability?.optimizer_missing ?? [];
  const error = draft.error ?? (savedTask?.status === 'failed' && !draft.error && !draft.source && !galleryPhoto && !initialUpload
    ? { code: 'portraitInterrupted', message: '' } : undefined);

  const commit = useCallback((patch: Partial<PortraitDraft>, editPatch?: Partial<ImageEditDraft>) => {
    if (disposed.current) return;
    const current = { ...latest.current, ...patch };
    if (editPatch) current.edit = { ...current.edit, ...editPatch };
    latest.current = current;
    savePortraitDraft(workspaceId, current);
    setDraft(current);
  }, [workspaceId]);

  useEffect(() => {
    if (!active) return;
    const health = new AbortController();
    let timer: number;
    async function refresh() {
      try {
        const current = await portraitAvailability(health.signal, true);
        if (health.signal.aborted) return;
        setAvailability(current);
        if (current.code === 'portraitStarting') timer = window.setTimeout(() => void refresh(), 2500);
      } catch {
        if (!health.signal.aborted) setAvailability({ ready: false, code: 'portraitOffline', missing: [] });
      }
    }
    void refresh();
    return () => { health.abort(); window.clearTimeout(timer); };
  }, [active, healthVersion]);

  useEffect(() => registerActions(workspaceId, {
    dispose() {
      disposed.current = true;
      controller.current?.abort();
      referenceRequest.current?.abort();
      initialUpload?.abort();
    },
    async cancel() {
      if (waitForSubmission) return;
      const { pending, source } = latest.current;
      if (pending?.job) await cancelPortraitJob({ job: pending.job });
      else if (pending?.requestId && source) {
        await cancelPortraitJob({ request_id: pending.requestId, source: source.token });
      }
      controller.current?.abort();
      initialUpload?.abort();
    },
  }), [initialUpload, registerActions, waitForSubmission, workspaceId]);

  useEffect(() => () => {
    controller.current?.abort();
    controller.current = null;
    referenceRequest.current?.abort();
  }, []);

  useEffect(() => {
    if (!initialUpload) return;
    let watching = true;
    const task = { workspaceId, filename: initialUpload.filename, stage: 'upload' as const, tool: 'edit' as const,
      startedAt: initialUpload.startedAt };
    onTaskUpdate({ ...task, status: 'running' });
    void initialUpload.result.then((source) => {
      if (!watching || disposed.current) return;
      commit({ source, error: undefined });
      onTaskUpdate({ ...task, status: 'completed' });
    }).catch((problem) => {
      if (!watching || disposed.current) return;
      commit({ error: editError(problem) });
      onTaskUpdate({ ...task, status: 'failed' });
    }).finally(() => {
      if (watching && !disposed.current) setBusy(false);
    });
    return () => { watching = false; };
  }, [commit, initialUpload, onTaskUpdate, workspaceId]);

  useEffect(() => {
    if (saved.pending?.stage !== 'edit' || waitForSubmission) return;
    const timer = window.setTimeout(() => resume.current?.(), 0);
    return () => window.clearTimeout(timer);
  }, [saved.pending, waitForSubmission]);

  async function startEngine() {
    setLaunching(true);
    try {
      await startPortraitEngine();
      commit({ error: undefined });
      setHealthVersion((version) => version + 1);
    } catch (problem) {
      commit({ error: editError(problem) });
    } finally {
      setLaunching(false);
    }
  }

  function pickReference(file: File) {
    void loadReference(file.name, (signal) => uploadPortrait('reference', file, signal));
  }

  async function loadReference(name: string, load: (signal: AbortSignal) => Promise<PortraitUpload>) {
    if (locked) return;
    referenceRequest.current?.abort();
    const request = new AbortController();
    referenceRequest.current = request;
    setLoadingReference(true);
    try {
      const uploaded = await load(request.signal);
      if (request.signal.aborted) return;
      commit({ error: undefined }, { reference: uploaded, referenceName: name });
    } catch (problem) {
      if (!request.signal.aborted) commit({ error: editError(problem) });
    } finally {
      if (referenceRequest.current === request) {
        referenceRequest.current = null;
        setLoadingReference(false);
      }
    }
  }

  async function releaseCache() {
    if (controller.current || locked || !canClearCache || !availability?.ready) return;
    const request = new AbortController();
    controller.current = request;
    setReleasing(true);
    setCacheRelease(undefined);
    commit({ error: undefined });
    try {
      const result = await releasePortraitMemory(request.signal);
      onCacheCleared();
      if (!disposed.current) setCacheRelease(result);
    } catch (problem) {
      if (!request.signal.aborted) commit({ error: editError(problem) });
    } finally {
      if (controller.current === request) controller.current = null;
      if (!disposed.current) setReleasing(false);
    }
  }

  async function queueEdit() {
    const count = draft.batchCount ?? 1;
    const inputDraft = { ...latest.current, pending: undefined, error: undefined,
      edit: { ...latest.current.edit, page: 'edit' as const, result: undefined } };
    setPreparing((value) => value + count);
    commit({ error: undefined });
    try {
      await enqueueBatch({ stage: 'edit', count, filename: sourceName, originId: workspaceId, photo: galleryPhoto, prepare: async (signal) => {
        const localMask = area === 'local' && canvas.current ? await maskBlob(canvas.current) : undefined;
        signal.throwIfAborted();
        if (area === 'local' && !localMask) throw new ApiError('', 400, { code: 'editMaskRequired' });
        if (!latest.current.source && galleryPhoto && !sourceLoading.current) {
          sourceLoading.current = openGalleryPhoto(galleryPhoto.id, signal, 'edit-source')
            .then((source) => { commit({ source }); return source; })
            .finally(() => { sourceLoading.current = null; });
        }
        const source = latest.current.source ?? await sourceLoading.current;
        if (!source) throw new ApiError('', 400, { code: 'portraitInvalidImage' });
        const mask = localMask ? (await prepareEditMask(source.token, localMask, signal)).token : undefined;
        return { draft: { ...inputDraft, source }, options: { source: source.token, area, mask, reference: reference?.token, prompt, optimize,
          sample_edge: edge, seed: seed.trim() ? Number(seed) : undefined } };
      } });
      if (!disposed.current) setQueued(count);
    } catch (problem) {
      commit({ error: editError(problem) });
    } finally {
      if (!disposed.current) setPreparing((value) => value - count);
    }
  }

  async function generate(tracked: PendingPortrait) {
    if (controller.current || disposed.current) return;
    const request = new AbortController();
    controller.current = request;
    const { signal } = request;
    const task = { workspaceId, filename: sourceName, stage: 'edit' as const, tool: 'edit' as const,
      startedAt: tracked.startedAt };
    setBusy(true);
    setCacheRelease(undefined);
    onTaskUpdate({ ...task, status: !tracked.job || savedTask?.status === 'queued' ? 'queued' : 'running' });
    commit({ error: undefined });
    try {
      const completed = await runPortrait('edit', tracked.options, (update) => {
        setProgress(update);
        onTaskUpdate({ ...task, status: update.state, percent: progressPercent(update) });
      }, signal, {
        requestId: tracked.requestId, job: tracked.job, onSubmitted: (job) => {
          commit({ pending: { ...tracked, job } });
          onJobSubmitted(workspaceId);
        },
      });
      commit({ pending: undefined }, { result: completed, page: 'result' });
      onTaskUpdate({ ...task, status: 'completed' });
    } catch (problem) {
      if (!signal.aborted) {
        commit({ pending: undefined, error: editError(problem) });
        onTaskUpdate({ ...task, status: 'failed' });
      }
    } finally {
      if (controller.current === request) {
        controller.current = null;
        if (!disposed.current) setBusy(false);
      }
    }
  }
  resume.current = () => { if (latest.current.pending) void generate(latest.current.pending); };

  const validSeed = !seed.trim() || /^\d+$/.test(seed.trim()) && Number.isSafeInteger(Number(seed));
  const canRun = Boolean(sourceUrl && availability?.ready && canGenerate && !releasing && !loadingReference && prompt.trim()
    && prompt.length <= 4000 && !missingReference && (area === 'full' || painted) && validSeed
    && (!optimize || !optimizerMissing.length));
  const connection = availability?.ready ? 'connected' : !availability ? 'checking'
    : availability.code === 'portraitStarting' ? 'starting' : availability.missing.length ? 'missing' : 'offline';
  const uploading = Boolean(busy && initialUpload && !draft.source);
  const nodeName = progress.node ? editNodes[progress.node] ?? 'processing' : undefined;
  const errorLabel = error && t(`portrait.errors.${error.code}`, { defaultValue: error.message || t('portrait.errors.portraitRunError') });

  if (!active) return null;
  return <div className={workbenchStyles.workbench}>
    <div className={workbenchStyles.inner}>
      <header className={workbenchStyles.header}>
        <div className={workbenchStyles.headerTitle}>
          <nav className={workbenchStyles.breadcrumb} aria-label={t('portrait.navigation')}>
            <Button variant="ghost" size="sm" type="button" icon={<ArrowLeft size={15} />} onClick={onBack}>{t('photoView')}</Button>
            <ChevronRight size={13} aria-hidden="true" /><span>{t('photoTools.edit')}</span>
          </nav>
          <h1>{t('photoTools.edit')}</h1>
        </div>
        <div className={workbenchStyles.engineActions}>
          <WorkflowInfo workflow="photo-edit" title={t('photoTools.edit')} />
          <Button variant="ghost" size="sm" type="button" className={workbenchStyles.connection} data-ready={availability?.ready ?? false}
            icon={<i className={workbenchStyles.connectionDot} />} aria-label={t('portrait.refreshConnection')}
            onClick={() => setHealthVersion((version) => version + 1)} disabled={busy || releasing || launching}>
            {t(`portrait.${connection}`)} <RefreshCw size={13} />
          </Button>
          <ReleaseCacheButton disabled={locked || !availability?.ready} canClearCache={canClearCache}
            onClick={() => void releaseCache()} />
        </div>
        <Button variant="secondary" size="sm" type="button" iconOnly icon={<X size={18} />} className={workbenchStyles.closeWorkspace}
          aria-label={t('photoTools.closeEdit')} onClick={() => onClose(workspaceId, true)} />
      </header>
      {availability && !availability.ready && <div className={`${workbenchStyles.banner} ${workbenchStyles.engineBanner}`}>
        <div role="status">{t(availability.missing.length ? 'portrait.dependencies'
          : connection === 'starting' ? 'portrait.startingHint' : 'portrait.openComfy')}
          {availability.missing.length > 0 && <ul>{availability.missing.map((name) => <li key={name}>{name}</li>)}</ul>}
        </div>
        {canGenerate && availability.can_start && connection === 'offline' &&
          <Button type="button" size="sm" icon={<Play size={16} />} disabled={launching} onClick={() => void startEngine()}>
            {t(launching ? 'portrait.starting' : 'portrait.startComfy')}
          </Button>}
      </div>}
      {!canGenerate && <div className={workbenchStyles.banner}>{t('portrait.lanAccess')}</div>}
      {errorLabel && <div className={styles.error} role="alert">{errorLabel}
        {error?.code === 'portraitRunError' && error.message && error.message !== errorLabel && <small>{error.message}</small>}
      </div>}
      <div className={workbenchStyles.workspaceBar}>
        <Segments label={t('portrait.workflowSteps')} value={page} onChange={(next) => commit({}, { page: next })}
          options={[{ value: 'edit', label: t('photoTools.edit'), icon: <Pencil size={16} /> },
            { value: 'result', label: t('photoTools.result'), disabled: !result }]} />
        <div className={workbenchStyles.sourceTools} {...sourceDrop}>
          {sourceUrl && <PhotoSourcePreview src={sourceUrl} name={sourceName} width={galleryPhoto?.width} height={galleryPhoto?.height} />}
          <PhotoSourceDownload photo={galleryPhoto} source={draft.source} name={sourceName} />
          {sourceUrl && <Button variant="ghost" type="button" size="sm" icon={<ImagePlus size={16} />}
            disabled={locked} onClick={() => setPicker('source')}>{t('photoTools.fromGallery')}</Button>}
          {sourceUrl && <Button variant="ghost" type="button" size="sm" icon={<CloudUpload size={16} />}
            disabled={locked} onClick={() => sourceInput.current?.click()}>{t('portrait.replacePhoto')}</Button>}
          <input ref={sourceInput} type="file" accept={workbenchPhotoAccept} hidden onChange={(event) => {
            const file = event.currentTarget.files?.[0];
            if (file) onChoosePhoto(file);
            event.currentTarget.value = '';
          }} />
        </div>
      </div>
      {!sourceUrl ? <section className={styles.empty} {...sourceDrop}>
        <ImagePlus size={34} aria-hidden="true" />
        <strong>{t(busy ? 'loading' : 'photoTools.choosePhoto')}</strong>
        {!locked && <small className={styles.dropHint}>{t('portrait.dropPhoto')}</small>}
        {!busy && <div>
          <Button type="button" icon={<ImagePlus size={17} />} disabled={locked} onClick={() => setPicker('source')}>{t('photoTools.fromGallery')}</Button>
          <Button type="button" variant="secondary" icon={<CloudUpload size={17} />} disabled={locked} onClick={() => sourceInput.current?.click()}>{t('photoTools.upload')}</Button>
        </div>}
      </section> : <>
        <div className={styles.layout} hidden={page !== 'edit'}>
          <div className={styles.canvas} {...sourceDrop}>
            <MaskEditor image={sourceUrl} label={t('photoTools.original')} disabled={locked} nativeFill initialStrokes={edit.strokes}
              onPaint={setPainted} onCanvas={(element) => { canvas.current = element; }}
              onStrokesChange={(strokes) => commit({ error: undefined }, { strokes, ...(strokes.length ? { area: 'local' } : {}) })} />
          </div>
          <aside className={styles.settings}>
            <div className={styles.reference} {...referenceDrop}>
              <span className={styles.label}>{t('portrait.reference')} <small>{t('photoTools.optional')}</small></span>
              {reference && <div className={styles.referencePhoto}>
                <PhotoSourcePreview src={reference.url} name={edit.referenceName} large />
                <Button type="button" variant="ghost" size="sm" iconOnly icon={<X size={16} />} aria-label={t('photoTools.removeReference')}
                  disabled={locked || loadingReference} onClick={() => commit({ error: undefined }, { reference: undefined, referenceName: undefined })} />
              </div>}
              <div className={styles.referenceButtons}>
                <Button variant="secondary" type="button" size="sm" icon={<ImagePlus size={16} />} disabled={locked || loadingReference}
                  onClick={() => setPicker('reference')}>{t('photoTools.fromGallery')}</Button>
                <Button variant="secondary" type="button" size="sm" icon={<CloudUpload size={16} />} disabled={locked || loadingReference}
                  onClick={() => referenceInput.current?.click()}>{t(loadingReference ? 'loading' : 'photoTools.upload')}</Button>
                <input ref={referenceInput} type="file" accept={workbenchPhotoAccept} hidden onChange={(event) => {
                  const file = event.currentTarget.files?.[0];
                  if (file) pickReference(file);
                  event.currentTarget.value = '';
                }} />
              </div>
            </div>
            <ImagePrompt value={prompt} onChange={(value) => commit({ error: undefined }, { prompt: value })} original={sourceUrl}
              reference={reference?.url} disabled={locked} />
            {missingReference && <p role="alert" className={styles.error}>{t('portrait.errors.editReferenceRequired')}</p>}
            {prompt.length > 4000 && <p role="alert" className={styles.error}>{t('portrait.errors.editDescriptionRequired')}</p>}
            <div className={styles.area}>
              <Segments label={t('photoTools.area')} value={area} onChange={(next) => commit({ error: undefined }, { area: next })}
                options={[{ value: 'full', label: t('photoTools.fullImage'), disabled: locked },
                  { value: 'local', label: t('photoTools.localEdit'), disabled: locked }]} />
              {area === 'local' && !painted && <small>{t('photoTools.paintSelection')}</small>}
              {area === 'full' && painted && <small>{t('photoTools.fullImageHint')}</small>}
            </div>
            <details className={styles.advanced}>
              <summary>{t('photoTools.settings')}</summary>
              <ToggleField label={t('photoTools.optimize')} checked={optimize} disabled={locked}
                onChange={(value) => commit({ error: undefined }, { optimize: value })} />
              <PixelChoice label={t('photoTools.sampleEdge')} disabled={locked} values={sampleEdges} value={edge}
                onChange={(value) => commit({}, { edge: value })} />
              <label className={styles.seed}>{t('portrait.seed')} <input type="text" inputMode="numeric" maxLength={16}
                placeholder={t('photoTools.randomSeed')} aria-invalid={!validSeed} value={seed} disabled={locked}
                onChange={(event) => commit({}, { seed: event.currentTarget.value })} /></label>
              {!validSeed && <small role="alert">{t('photoTools.invalidSeed')}</small>}
            </details>
            {optimize && optimizerMissing.length > 0 && <p role="alert" className={styles.error}>
              {t('photoTools.optimizerMissing', { models: optimizerMissing.join('、') })}
            </p>}
            <div className={styles.submit}>
              <BatchCount value={draft.batchCount ?? 1} onChange={(count) => commit({ batchCount: count })} />
              <Button type="button" disabled={!canRun} icon={<Pencil size={17} />}
                onClick={() => void queueEdit()}>{t('photoTools.run')}</Button>
              <BatchNotice preparing={preparing} queued={queued} />
            </div>
          </aside>
        </div>
        {result && page === 'result' && <section className={workbenchStyles.compareCard} aria-label={t('photoTools.result')}>
          <ImageComparison key={result.image} before={sourceUrl} after={result.image} beforeLabel={t('photoTools.original')}
            afterLabel={t('photoTools.result')} fallbackFilename="image-edit.png"
            resultActions={<PhotoResultActions image={result.image} tool="edit" canUseResult={canGenerate}
              onContinue={(tool, image) => onContinue(tool, image, sourceName)} />} />
          {result.prompt && <details className={styles.finalPrompt}>
            <summary>{t('photoTools.finalPrompt')}</summary><p>{result.prompt}</p>
          </details>}
        </section>}
      </>}
      {picker && <GalleryImagePicker onClose={() => setPicker(undefined)} onDropFile={!locked && (picker === 'source' || !loadingReference) ? (file) => {
        if (picker === 'source') onChoosePhoto(file);
        else pickReference(file);
        setPicker(undefined);
      } : undefined} onSelect={(photo) => {
        if (picker === 'source') onChooseGalleryPhoto(photo);
        else void loadReference(photo.name, (signal) => openGalleryPhoto(photo.id, signal, 'reference'));
        setPicker(undefined);
      }} />}
    </div>
    {(busy || releasing || cacheRelease) && <aside className={workbenchStyles.statusBar} role="status">
      {(busy || releasing) && <div className={workbenchStyles.statusTitle}>
        <strong>{t(releasing ? 'portrait.progress.release' : uploading ? 'portrait.progress.upload' : 'portrait.progress.edit')}</strong>
      </div>}
      {busy && !uploading && <WorkflowProgress progress={progress} nodeName={nodeName} />}
      {cacheRelease && <CacheReleaseStatus result={cacheRelease} onClose={() => setCacheRelease(undefined)} />}
    </aside>}
  </div>;
}
