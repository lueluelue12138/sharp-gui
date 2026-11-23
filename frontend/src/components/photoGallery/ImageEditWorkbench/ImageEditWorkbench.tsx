import { useCallback, useEffect, useRef, useState } from 'react';

import { ArrowLeft, ChevronRight, CloudUpload, ImagePlus, Maximize2, Pencil, Play, RefreshCw, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { ApiError } from '@/api/client';
import { cancelPortraitJob, openGalleryPhoto, portraitAvailability, prepareEditMask, releasePortraitMemory, runPortrait, startPortraitEngine, uploadPortrait } from '@/api/portrait';
import { Button } from '@/components/common/Button';
import { GalleryImagePicker } from '@/components/photoGallery/GalleryImagePicker';
import { ImagePrompt } from '@/components/photoGallery/ImagePrompt';
import { OutpaintBoard, OutpaintOutputSettings, OutpaintSettings } from '@/components/photoGallery/OutpaintBoard';
import { boardGeometry, canvasPixelLimit, initialLayout } from '@/components/photoGallery/OutpaintBoard/geometry';
import type { ImageSize, OutpaintLayout } from '@/components/photoGallery/OutpaintBoard/geometry';
import { PhotoResultActions } from '@/components/photoGallery/PhotoResultActions';
import { PhotoSourceDownload, PhotoSourcePreview } from '@/components/photoGallery/PhotoSourcePreview';
import { ImageComparison } from '@/components/portrait/PortraitWorkbench/ImageComparison';
import { MaskEditor } from '@/components/portrait/PortraitWorkbench/MaskEditor';
import { BatchCount, BatchNotice, BatchProgress, CacheReleaseStatus, PixelChoice, ReleaseCacheButton, Segments, ToggleField, WorkflowProgress } from '@/components/portrait/WorkbenchControls';
import { WorkflowInfo } from '@/components/portrait/WorkflowInfo';
import { useImageDrop, workbenchPhotoAccept } from '@/hooks/useImageDrop';
import { readPortraitDraft, savePortraitDraft } from '@/store/portraitSession';
import type { EnqueuePortraitBatch, ImageEditDraft, PendingPortrait, PortraitDraft, PortraitWorkspaceActions } from '@/store/portraitSession';
import type { PhotoItem } from '@/types/photoGallery';
import type { PhotoTool, PortraitAvailability, PortraitCacheRelease, PortraitProgress, PortraitSourceUpload, PortraitTask, PortraitUpload } from '@/types/portrait';

import styles from '@/components/photoGallery/ImageEditWorkbench/ImageEditWorkbench.module.css';
import boardStyles from '@/components/photoGallery/OutpaintBoard/OutpaintBoard.module.css';
import workbenchStyles from '@/components/portrait/PortraitWorkbench/PortraitWorkbench.module.css';

const sampleEdges = [768, 1024, 1280, 1536, 1920, 2048];
const editNodes: Record<string, string> = {
  '179': 'optimizePrompt', '249': 'prepareEdit', '250': 'prepareEdit', '255': 'prepareEdit', '256': 'decode',
  '247': 'prepareEdit', '252': 'mergeEdit', '274': 'sampling', '361': 'loadModel', '362': 'loadModel',
  '363': 'loadModel', '370': 'save',
};
const extendNodes: Record<string, string> = {
  '48': 'prepareExtend', '40': 'prepareExtend', '24': 'prepareExtend', '5': 'prepareExtend', '7': 'prepareExtend',
  '19': 'sampling', '21': 'decode', '25': 'mergeEdit', '46': 'save', '51': 'save',
  '8': 'loadModel', '9': 'loadModel', '14': 'loadModel', '17': 'loadModel',
};

interface ImageEditWorkbenchProps {
  tool: 'edit' | 'extend';
  workspaceId: string;
  active: boolean;
  canGenerate: boolean;
  canClearCache: boolean;
  galleryPhoto?: PhotoItem;
  initialUpload?: PortraitSourceUpload;
  uploadName?: string;
  savedTask?: PortraitTask;
  batchTask?: PortraitTask;
  initialDraft?: PortraitDraft;
  enqueueBatch: EnqueuePortraitBatch;
  onJobSubmitted: (id: string) => void;
  waitForSubmission: boolean;
  onCacheCleared: () => void;
  onBack: () => void;
  onClose: (id: string, fromWorkbench: boolean) => void;
  onChoosePhoto: (tool: 'edit' | 'extend', file: File) => void;
  onChooseGalleryPhoto: (tool: PhotoTool, photo: PhotoItem) => void;
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
  tool, workspaceId, active, canGenerate, canClearCache, galleryPhoto, initialUpload, uploadName, savedTask, batchTask, initialDraft, onCacheCleared,
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
  const [showMask, setShowMask] = useState(false);
  const [maskPreview, setMaskPreview] = useState<string>();
  const [imageSize, setImageSize] = useState<ImageSize>();
  const [picker, setPicker] = useState<'source' | 'reference'>();
  const [progress, setProgress] = useState<PortraitProgress>(savedTask?.progress
    ?? { state: savedTask?.status === 'queued' || (saved.pending && !saved.pending.job) ? 'queued' : 'running' });
  const edit = draft.edit ?? {};
  const { prompt = '', area = 'full', edge = 2048, optimize = true, seed = '', page = 'edit', reference, result, layout = initialLayout } = edit;
  const extending = tool === 'extend';
  const ToolIcon = extending ? Maximize2 : Pencil;
  const toolTitle = t(`photoTools.${tool}`);
  const geometry = imageSize && boardGeometry(imageSize, layout);
  const canvasTooLarge = geometry && Math.max(geometry.width * geometry.height, geometry.outputWidth * geometry.outputHeight) > canvasPixelLimit;
  const sourceUrl = draft.source?.url ?? galleryPhoto?.full_url ?? galleryPhoto?.preview_url;
  const sourceName = initialUpload?.filename ?? uploadName ?? galleryPhoto?.name ?? t('photoTools.original');
  const locked = busy || releasing || !canGenerate;
  const sourceDrop = useImageDrop(([file]) => onChoosePhoto(tool, file), { enabled: !locked });
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

  function updateLayout(value: OutpaintLayout) {
    commit({ error: undefined }, { layout: value });
  }

  useEffect(() => {
    if (!active) return;
    const health = new AbortController();
    let timer: number;
    async function refresh() {
      try {
        const current = await portraitAvailability(health.signal, tool);
        if (health.signal.aborted) return;
        setAvailability(current);
        if (current.code === 'portraitStarting') timer = window.setTimeout(() => void refresh(), 2500);
      } catch {
        if (!health.signal.aborted) setAvailability({ ready: false, code: 'portraitOffline', missing: [] });
      }
    }
    void refresh();
    return () => { health.abort(); window.clearTimeout(timer); };
  }, [active, healthVersion, tool]);

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
    const task = { workspaceId, filename: initialUpload.filename, stage: 'upload' as const, tool,
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
  }, [commit, initialUpload, onTaskUpdate, tool, workspaceId]);

  useEffect(() => {
    if (saved.pending?.stage !== tool || waitForSubmission) return;
    const timer = window.setTimeout(() => resume.current?.(), 0);
    return () => window.clearTimeout(timer);
  }, [saved.pending, tool, waitForSubmission]);

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

  async function queueGeneration() {
    const count = draft.batchCount ?? 1;
    const inputDraft = { ...latest.current, pending: undefined, error: undefined,
      edit: { ...latest.current.edit, page: 'edit' as const, result: undefined } };
    setPreparing((value) => value + count);
    commit({ error: undefined });
    try {
      await enqueueBatch({ stage: tool, count, filename: sourceName, originId: workspaceId, photo: galleryPhoto, prepare: async (signal) => {
        const needsMask = extending ? painted : area === 'local';
        const localMask = needsMask && canvas.current ? await maskBlob(canvas.current) : undefined;
        signal.throwIfAborted();
        if (needsMask && !localMask) throw new ApiError('', 400, { code: 'editMaskRequired' });
        if (!latest.current.source && galleryPhoto && !sourceLoading.current) {
          sourceLoading.current = openGalleryPhoto(galleryPhoto.id, signal, `${tool}-source`)
            .then((source) => { commit({ source }); return source; })
            .finally(() => { sourceLoading.current = null; });
        }
        const source = latest.current.source ?? await sourceLoading.current;
        if (!source) throw new ApiError('', 400, { code: 'portraitInvalidImage' });
        const mask = localMask ? (await prepareEditMask(source.token, localMask, signal, tool)).token : undefined;
        const common = { source: source.token, mask, prompt, sample_edge: edge, seed: seed.trim() ? Number(seed) : undefined };
        const settings = extending && imageSize ? {
          size: [imageSize.width, imageSize.height], pads: layout.pads, unit: layout.unit, translated: layout.translated,
          ratio: layout.ratio === 'free' ? '自由比例' : layout.ratio === 'original' ? '原始比例' : layout.ratio,
          color: layout.color, multiple: layout.multiple, output_edge: layout.outputEdge,
        } : { area, reference: reference?.token, optimize };
        return { draft: { ...inputDraft, source }, options: { ...common, ...settings } };
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
    const task = { workspaceId, filename: sourceName, stage: tool, tool,
      startedAt: tracked.startedAt };
    setBusy(true);
    setCacheRelease(undefined);
    onTaskUpdate({ ...task, status: !tracked.job || savedTask?.status === 'queued' ? 'queued' : 'running' });
    commit({ error: undefined });
    try {
      const completed = await runPortrait(tool, tracked.options, (update) => {
        setProgress(update);
        onTaskUpdate({ ...task, status: update.state, progress: update });
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
  const canRun = Boolean(sourceUrl && availability?.ready && !locked && !loadingReference && prompt.length <= 4000 && validSeed
    && (extending ? imageSize && !canvasTooLarge : prompt.trim() && !missingReference && (area === 'full' || painted)
      && (!optimize || !optimizerMissing.length)));
  const connection = availability?.ready ? 'connected' : !availability ? 'checking'
    : availability.code === 'portraitStarting' ? 'starting' : availability.missing.length ? 'missing' : 'offline';
  const uploading = Boolean(busy && initialUpload && !draft.source);
  const nodeName = progress.node ? (extending ? extendNodes : editNodes)[progress.node] ?? 'processing' : undefined;
  const errorLabel = error && t(`portrait.errors.${error.code}`, { defaultValue: error.message || t('portrait.errors.portraitRunError') });

  if (!active) return null;
  return <div className={workbenchStyles.workbench}>
    <div className={workbenchStyles.inner}>
      <header className={workbenchStyles.header}>
        <div className={workbenchStyles.headerTitle}>
          <nav className={workbenchStyles.breadcrumb} aria-label={t('portrait.navigation')}>
            <Button variant="ghost" size="sm" type="button" icon={<ArrowLeft size={15} />} onClick={onBack}>{t('photoView')}</Button>
            <ChevronRight size={13} aria-hidden="true" /><span>{toolTitle}</span>
          </nav>
          <h1>{toolTitle}</h1>
        </div>
        <div className={workbenchStyles.engineActions}>
          <WorkflowInfo workflow={`photo-${tool}`} title={toolTitle} />
          <Button variant="ghost" size="sm" type="button" className={workbenchStyles.connection} data-ready={availability?.ready ?? false}
            icon={<i className={workbenchStyles.connectionDot} />} aria-label={t('portrait.refreshConnection')}
            onClick={() => setHealthVersion((version) => version + 1)} disabled={busy || releasing || launching}>
            {t(`portrait.${connection}`)} <RefreshCw size={13} />
          </Button>
          <ReleaseCacheButton disabled={locked || !availability?.ready} canClearCache={canClearCache}
            onClick={() => void releaseCache()} />
        </div>
        <Button variant="secondary" size="sm" type="button" iconOnly icon={<X size={18} />} className={workbenchStyles.closeWorkspace}
          aria-label={t(extending ? 'outpaint.close' : 'photoTools.closeEdit')} onClick={() => onClose(workspaceId, true)} />
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
          options={[{ value: 'edit', label: toolTitle, icon: <ToolIcon size={16} /> },
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
            if (file) onChoosePhoto(tool, file);
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
            {extending && <div hidden={showMask}>
              <OutpaintBoard image={sourceUrl} size={imageSize} layout={layout} maskPreview={maskPreview} disabled={locked}
                onSize={setImageSize} onChange={updateLayout} />
            </div>}
            <div hidden={extending && !showMask}>
              <MaskEditor image={sourceUrl} label={t(extending ? 'outpaint.mask' : 'photoTools.original')} disabled={locked}
                nativeFill={!extending} initialStrokes={edit.strokes}
                onPaint={(value) => {
                  setPainted(value);
                  if (extending) setMaskPreview(value ? canvas.current?.toDataURL('image/png') : undefined);
                }} onCanvas={(element) => { canvas.current = element; }}
                onStrokesChange={(strokes) => commit({ error: undefined }, { strokes, ...(!extending && strokes.length ? { area: 'local' } : {}) })} />
            </div>
          </div>
          <aside className={styles.settings}>
            {extending ? <>
              <OutpaintSettings layout={layout} size={imageSize} disabled={locked} mask={showMask}
                onChange={updateLayout} onMask={() => setShowMask((value) => !value)} />
              <label className={boardStyles.prompt}>{t('outpaint.prompt')} <textarea value={prompt} disabled={locked}
                placeholder={t('outpaint.promptHint')} maxLength={4000}
                onChange={(event) => commit({ error: undefined }, { prompt: event.currentTarget.value })} /></label>
              {canvasTooLarge && <p role="alert" className={styles.error}>{t('portrait.errors.extendCanvasTooLarge')}</p>}
            </> : <>
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
            </>}
            <details className={styles.advanced}>
              <summary>{t('photoTools.settings')}</summary>
              {extending ? <OutpaintOutputSettings layout={layout} disabled={locked} onChange={updateLayout} />
                : <ToggleField label={t('photoTools.optimize')} checked={optimize} disabled={locked}
                  onChange={(value) => commit({ error: undefined }, { optimize: value })} />}
              <PixelChoice label={t('photoTools.sampleEdge')} disabled={locked} values={sampleEdges} value={edge}
                onChange={(value) => commit({}, { edge: value })} />
              <label className={styles.seed}>{t('portrait.seed')} <input type="text" inputMode="numeric" maxLength={16}
                placeholder={t('photoTools.randomSeed')} aria-invalid={!validSeed} value={seed} disabled={locked}
                onChange={(event) => commit({}, { seed: event.currentTarget.value })} /></label>
              {!validSeed && <small role="alert">{t('photoTools.invalidSeed')}</small>}
            </details>
            {!extending && optimize && optimizerMissing.length > 0 && <p role="alert" className={styles.error}>
              {t('photoTools.optimizerMissing', { models: optimizerMissing.join('、') })}
            </p>}
            <div className={styles.submit}>
              <BatchCount value={draft.batchCount ?? 1} onChange={(count) => commit({ batchCount: count })} />
              <Button type="button" disabled={!canRun} icon={<ToolIcon size={17} />}
                onClick={() => void queueGeneration()}>{t(extending ? 'outpaint.run' : 'photoTools.run')}</Button>
              <BatchNotice preparing={preparing} queued={queued} />
            </div>
          </aside>
        </div>
        {result && page === 'result' && <section className={workbenchStyles.compareCard} aria-label={t('photoTools.result')}>
          <ImageComparison key={result.image} before={result.before ?? sourceUrl} after={result.image}
            beforeLabel={t(result.before ? 'outpaint.canvas' : 'photoTools.original')}
            afterLabel={t('photoTools.result')} fallbackFilename={`image-${tool}.png`}
            resultActions={<PhotoResultActions image={result.image} tool={tool} canUseResult={canGenerate}
              onContinue={(tool, image) => onContinue(tool, image, sourceName)} />} />
          {result.prompt && <details className={styles.finalPrompt}>
            <summary>{t('photoTools.finalPrompt')}</summary><p>{result.prompt}</p>
          </details>}
        </section>}
      </>}
      {picker && <GalleryImagePicker onClose={() => setPicker(undefined)} onDropFile={!locked && (picker === 'source' || !loadingReference) ? (file) => {
        if (picker === 'source') onChoosePhoto(tool, file);
        else pickReference(file);
        setPicker(undefined);
      } : undefined} onSelect={(photo) => {
        if (picker === 'source') onChooseGalleryPhoto(tool, photo);
        else void loadReference(photo.name, (signal) => openGalleryPhoto(photo.id, signal, 'reference'));
        setPicker(undefined);
      }} />}
    </div>
    {(busy || releasing || cacheRelease || batchTask) && <aside className={workbenchStyles.statusBar} role="status">
      {(busy || releasing) && <div className={workbenchStyles.statusTitle}>
        <strong>{t(releasing ? 'portrait.progress.release' : uploading ? 'portrait.progress.upload' : `portrait.progress.${tool}`)}</strong>
      </div>}
      {busy && !uploading && <WorkflowProgress progress={progress} nodeName={nodeName} />}
      {!busy && !releasing && batchTask && <BatchProgress task={batchTask} nodeNames={extending ? extendNodes : editNodes} />}
      {cacheRelease && <CacheReleaseStatus result={cacheRelease} onClose={() => setCacheRelease(undefined)} />}
    </aside>}
  </div>;
}
