import { useEffect, useLayoutEffect, useRef, useState } from 'react';

import { ArrowLeft, Camera, ChevronRight, CloudUpload, Image as ImageIcon, Images, LoaderCircle, Play, RefreshCw, Scan, Sparkles, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { ApiError } from '@/api/client';
import { cancelPortraitJob, openGalleryPhoto, portraitAvailability, releasePortraitMemory, runPortrait, startPortraitEngine, uploadPortrait } from '@/api/portrait';
import { Button } from '@/components/common/Button';
import { PhotoResultActions } from '@/components/photoGallery/PhotoResultActions';
import { PhotoSourceDownload, PhotoSourcePreview } from '@/components/photoGallery/PhotoSourcePreview';
import { BatchCount, BatchNotice, CacheReleaseStatus, NumberField, PixelChoice, RangeField, ReleaseCacheButton, Segments, ToggleField, WorkflowProgress } from '@/components/portrait/WorkbenchControls';
import { WorkflowInfo } from '@/components/portrait/WorkflowInfo';
import { CameraEditor } from '@/components/portrait/PortraitWorkbench/CameraEditor';
import { ImageComparison } from '@/components/portrait/PortraitWorkbench/ImageComparison';
import { MaskEditor } from '@/components/portrait/PortraitWorkbench/MaskEditor';
import type { Crop } from '@/components/portrait/PortraitWorkbench/MaskEditor';
import { Trajectory } from '@/components/portrait/PortraitWorkbench/Trajectory';
import { cameraFrame } from '@/components/portrait/PortraitWorkbench/portraitRenderer';
import type { CameraView, PortraitRenderer } from '@/components/portrait/PortraitWorkbench/portraitRenderer';
import { useImageDrop, workbenchPhotoAccept } from '@/hooks/useImageDrop';
import { newPortraitId, readPortraitDraft, savePortraitDraft } from '@/store/portraitSession';
import type { EnqueuePortraitBatch, PortraitBatchRequest, PortraitDraft, PortraitTrajectory, PortraitWorkspaceActions } from '@/store/portraitSession';
import type { PhotoTool, PortraitAvailability, PortraitCacheRelease, PortraitCapture, PortraitFrame, PortraitModel, PortraitProgress, PortraitRepair, PortraitSourceUpload, PortraitStageResults, PortraitTask, PortraitTaskStage } from '@/types/portrait';
import type { PhotoItem } from '@/types';
import { progressPercent } from '@/utils/portraitProgress';
import styles from '@/components/portrait/PortraitWorkbench/PortraitWorkbench.module.css';

const outputEdges = [512, 768, 1024, 1280, 1536, 1920, 2048, 2304, 2560];
const nodeNames: Record<string, string> = {
  '2': 'reconstruct', '3': 'framing', '6': 'fill', '7': 'loadModel', '8': 'loadModel', '9': 'loadModel',
  '17': 'sampling', '18': 'decode', '20': 'save', '22': 'prepareDetail', '206': 'prepareDetail', '207': 'prepareDetail',
  '208': 'sampling', '217': 'decode', '31': 'save', '10000': 'save',
};
type Stage = PortraitTaskStage | 'release';

function describeError(problem: unknown) {
  return {
    code: problem instanceof ApiError ? problem.data?.code ?? 'portraitRunError' : 'portraitRunError',
    message: problem instanceof Error ? problem.message : '',
  };
}

function canvasPng(canvas: HTMLCanvasElement) {
  return new Promise<Blob>((resolve, reject) => canvas.toBlob(
    (blob) => blob ? resolve(blob) : reject(new Error('The mask could not be saved.')), 'image/png',
  ));
}

export function PortraitWorkbench({ workspaceId, active, canGenerate, galleryPhoto, initialUpload, uploadName, savedTask, initialDraft, previewCacheRevision, canClearCache, onCacheCleared, onBack, onClose, onChoosePhoto, onTaskUpdate, onContinue, registerActions, enqueueBatch, onJobSubmitted, waitForSubmission, backgroundJob }: {
  workspaceId: string; active: boolean; canGenerate: boolean; galleryPhoto?: PhotoItem; initialUpload?: PortraitSourceUpload;
  uploadName?: string; savedTask?: PortraitTask; initialDraft?: PortraitDraft;
  previewCacheRevision: number; canClearCache: boolean; onCacheCleared: () => void;
  onBack: () => void; onClose: (id: string, fromWorkbench: boolean) => void; onChoosePhoto: (file: File) => void; onTaskUpdate: (task: PortraitTask) => void;
  onContinue: (tool: PhotoTool, image: string, name?: string) => void;
  registerActions: (id: string, actions: PortraitWorkspaceActions) => () => void;
  enqueueBatch: EnqueuePortraitBatch; onJobSubmitted: (id: string) => void;
  waitForSubmission: boolean; backgroundJob: boolean;
}) {
  const { t } = useTranslation();
  const [saved] = useState(() => initialDraft ?? readPortraitDraft(workspaceId));
  const [available, setAvailable] = useState<PortraitAvailability>();
  const [healthVersion, setHealthVersion] = useState(0);
  const [launchPending, setLaunchPending] = useState(false);
  const [launchError, setLaunchError] = useState<string>();
  const [source, setSource] = useState(saved.source);
  const sourceName = initialUpload?.filename ?? uploadName ?? galleryPhoto?.name;
  const [page, setPage] = useState(saved.page ?? 'frame');
  const [maskTab, setMaskTab] = useState(saved.maskTab ?? 'target');
  const [refineAdvanced, setRefineAdvanced] = useState(false);
  const [sourceSettings, setSourceSettings] = useState(false);
  const [cacheRelease, setCacheRelease] = useState<PortraitCacheRelease>();
  const [model, setModel] = useState(saved.model);
  const [modelVersion, setModelVersion] = useState(0);
  const [previewReady, setPreviewReady] = useState(false);
  const [previewReleased, setPreviewReleased] = useState(saved.previewReleased ?? false);
  const [capturing, setCapturing] = useState(false);
  const [releaseOnRepair, setReleaseOnRepair] = useState(saved.releaseOnRepair ?? false);
  const [view, setView] = useState<CameraView | null>(saved.view ?? null);
  const [base, setBase] = useState(saved.base);
  const [reference, setReference] = useState(saved.reference);
  const [refined, setRefined] = useState(saved.refined);
  const [frames, setFrames] = useState<PortraitFrame[]>(saved.frames ?? []);
  const [progress, setProgress] = useState<PortraitProgress>({ state: savedTask?.status === 'queued' ? 'queued' : 'running' });
  const [stage, setStage] = useState<Stage | undefined>(initialUpload ? 'upload' : saved.pending?.stage);
  const [error, setError] = useState(saved.error ?? (savedTask?.status === 'failed'
    ? { code: 'portraitInterrupted', message: '' } : undefined));
  const [lens, setLens] = useState(saved.lens ?? 30);
  const [ratio, setRatio] = useState(saved.ratio ?? 'source');
  const [edge, setEdge] = useState(saved.edge ?? 1920);
  const [repairReferenceEdge, setRepairReferenceEdge] = useState(saved.repairReferenceEdge ?? 1920);
  const [repairPrompt, setRepairPrompt] = useState(saved.repairPrompt);
  const [matchCloseup, setMatchCloseup] = useState(saved.matchCloseup ?? true);
  const [seed, setSeed] = useState(saved.seed ?? 1);
  const [randomSeed, setRandomSeed] = useState(saved.randomSeed ?? (saved.seed === undefined || saved.seed === 1));
  const [batchCount, setBatchCount] = useState(saved.batchCount ?? 1);
  const [preparing, setPreparing] = useState(0);
  const [queued, setQueued] = useState(0);
  const [strength, setStrength] = useState(saved.strength ?? 0.44);
  const [referenceEdge, setReferenceEdge] = useState(saved.referenceEdge ?? 1536);
  const [sampleEdge, setSampleEdge] = useState(saved.sampleEdge ?? 2048);
  const [expand, setExpand] = useState(saved.expand ?? 4);
  const [feather, setFeather] = useState(saved.feather ?? 5);
  const [color, setColor] = useState(saved.color ?? 1);
  const [optimize, setOptimize] = useState(saved.optimize ?? false);
  const [prompt, setPrompt] = useState(saved.prompt ?? '');
  const [crop, setCrop] = useState<Crop | undefined>(saved.crop);
  const [targetPainted, setTargetPainted] = useState(false);
  const [referencePainted, setReferencePainted] = useState(false);
  const [originalComparison, setOriginalComparison] = useState(true);
  const [frameIndex, setFrameIndex] = useState<{ index: number; total: number }>();
  const rendererRef = useRef<PortraitRenderer>(null);
  const targetMask = useRef<HTMLCanvasElement>(null);
  const referenceMask = useRef<HTMLCanvasElement>(null);
  const sourceInput = useRef<HTMLInputElement>(null);
  const referenceInput = useRef<HTMLInputElement>(null);
  const workbench = useRef<HTMLDivElement>(null);
  const current = useRef<AbortController>(null);
  const pending = useRef(saved.pending);
  const disposed = useRef(false);
  const cancellation = useRef<Promise<void> | null>(null);
  const startedAtRef = useRef(0);
  const lastCapture = useRef(saved.lastCapture && {
    ...saved.lastCapture,
    view: saved.view && JSON.stringify(saved.view) === JSON.stringify(saved.lastCapture.view) ? saved.view : saved.lastCapture.view,
  });
  const snapshot = useRef<PortraitDraft>(saved);
  const repairCapture = useRef<{ view: CameraView; ratio: string; edge: number; result: Promise<PortraitCapture> } | null>(null);
  const resume = useRef<() => void>(null);
  snapshot.current = {
    source, model, base, refined, reference, crop, frames, view, page, maskTab, lens, ratio, edge, repairReferenceEdge,
    repairPrompt, matchCloseup, seed, strength, referenceEdge, sampleEdge, expand, feather, color, optimize, prompt, releaseOnRepair, error,
    previewReleased, lastCapture: lastCapture.current, batchCount, randomSeed,
  };
  function persist(patch: Partial<PortraitDraft> = {}) {
    if (disposed.current) return;
    snapshot.current = { ...snapshot.current, ...patch };
    savePortraitDraft(workspaceId, { ...snapshot.current, pending: pending.current });
  }
  const monitorStartup = useRef(false);
  const stopFrames = useRef(false);
  const clearedRevision = useRef(previewCacheRevision);
  const busy = Boolean(stage);
  const locked = busy || !canGenerate || !available?.ready;
  const sourceDrop = useImageDrop(([file]) => onChoosePhoto(file), { enabled: !locked });
  const referenceDrop = useImageDrop(([file]) => pickReference(file), { enabled: !locked });

  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    let timer: number;
    async function check() {
      try {
        const next = await portraitAvailability(controller.signal);
        if (controller.signal.aborted) return;
        setAvailable(next);
        monitorStartup.current = next.code === 'portraitStarting';
        if (next.ready || next.missing.length > 0) setLaunchError(undefined);
      } catch {
        if (controller.signal.aborted) return;
        if (!monitorStartup.current) setAvailable((previous) => ({ ...previous, ready: false, code: 'portraitOffline', missing: [] }));
      }
      if (monitorStartup.current) timer = window.setTimeout(() => void check(), 2000);
    }
    void check();
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [active, healthVersion]);

  useEffect(() => () => current.current?.abort(), []);

  useLayoutEffect(() => {
    function dispose() {
      disposed.current = true;
      current.current?.abort();
      initialUpload?.abort();
    }
    async function cancel() {
      if (waitForSubmission) return;
      const job = pending.current;
      const source = job?.options?.source;
      const target = job?.job ? { job: job.job }
        : job?.requestId && typeof source === 'string' ? { request_id: job.requestId, source } : undefined;
      if (!target) {
        dispose();
        return;
      }
      const request = cancelPortraitJob(target).then(dispose);
      cancellation.current = request;
      try {
        await request;
      } finally {
        cancellation.current = null;
      }
    }
    return registerActions(workspaceId, { dispose, cancel });
  }, [initialUpload, registerActions, waitForSubmission, workspaceId]);

  useEffect(() => {
    const write = () => {
      if (!disposed.current) savePortraitDraft(workspaceId, { ...snapshot.current, pending: pending.current });
    };
    const timer = window.setTimeout(write, 200);
    return () => window.clearTimeout(timer);
  });

  useEffect(() => {
    const write = () => {
      if (!disposed.current) savePortraitDraft(workspaceId, { ...snapshot.current, pending: pending.current });
    };
    window.addEventListener('pagehide', write);
    return () => window.removeEventListener('pagehide', write);
  }, [workspaceId]);

  useEffect(() => {
    if (!saved.pending || waitForSubmission) return;
    const timer = window.setTimeout(() => resume.current?.(), 0);
    return () => window.clearTimeout(timer);
  }, [saved.pending, waitForSubmission]);

  useEffect(() => {
    if (clearedRevision.current === previewCacheRevision) return;
    clearedRevision.current = previewCacheRevision;
    setModel(undefined);
    setPreviewReady(false);
    setPreviewReleased(false);
    setView(null);
    lastCapture.current = undefined;
  }, [previewCacheRevision]);

  useEffect(() => {
    if (!initialUpload) return;
    let watching = true;
    const task = { workspaceId, filename: initialUpload.filename, stage: 'upload' as const, startedAt: initialUpload.startedAt };
    onTaskUpdate({ ...task, status: 'running' });
    void initialUpload.result.then((result) => {
      if (!watching || disposed.current) return;
      savePortraitDraft(workspaceId, { ...snapshot.current, source: result });
      setSource(result);
      setStage(undefined);
      onTaskUpdate({ ...task, status: 'completed' });
    }, (problem: unknown) => {
      if (!watching || disposed.current) return;
      setError(describeError(problem));
      setStage(undefined);
      onTaskUpdate({ ...task, status: 'failed' });
    });
    return () => { watching = false; };
  }, [initialUpload, onTaskUpdate, workspaceId]);

  async function perform(action: Stage, work: (signal: AbortSignal, onProgress: (progress: PortraitProgress) => void) => Promise<void>, restoring = false) {
    if (disposed.current || current.current || (!restoring && locked)) return;
    const controller = new AbortController();
    current.current = controller;
    setError(undefined);
    const initialStatus = restoring && (backgroundJob || savedTask?.status === 'queued') ? 'queued' : 'running';
    setProgress({ state: initialStatus });
    setCacheRelease(undefined);
    setStage(action);
    const startedAt = restoring ? pending.current!.startedAt : Date.now();
    startedAtRef.current = startedAt;
    function report(status: PortraitTask['status'], percent?: number) {
      if (action !== 'release' && sourceName && !controller.signal.aborted) {
        onTaskUpdate({ workspaceId, filename: sourceName, stage: action, status, startedAt, percent });
      }
    }
    report(initialStatus);
    try {
      await work(controller.signal, (next) => {
        setProgress(next);
        report(next.state, progressPercent(next));
      });
      controller.signal.throwIfAborted();
      report('completed');
      pending.current = undefined;
      persist();
    } catch (problem) {
      if (!controller.signal.aborted) {
        const failure = describeError(problem);
        setError(failure);
        report('failed');
        pending.current = undefined;
        persist({ error: failure });
      }
    } finally {
      current.current = null;
      if (!controller.signal.aborted) setStage(undefined);
    }
  }

  async function runTracked<S extends keyof PortraitStageResults>(
    action: S, options: Record<string, unknown> | undefined, onProgress: (next: PortraitProgress) => void, signal: AbortSignal,
  ) {
    // A trajectory must wait for the cancellation response before queuing another frame.
    if (cancellation.current) await cancellation.current.catch(() => {});
    signal.throwIfAborted();
    if (!pending.current?.job && !pending.current?.requestId) {
      pending.current = { ...pending.current, stage: action, startedAt: startedAtRef.current, options, requestId: newPortraitId() };
      persist();
    }
    const savedJob = pending.current;
    return runPortrait(action, savedJob.options, onProgress, signal, {
      job: savedJob.job, requestId: savedJob.requestId, onSubmitted: (job) => {
        pending.current = { ...(pending.current ?? savedJob), job };
        persist();
        if (backgroundJob) onJobSubmitted(workspaceId);
      },
    });
  }

  function clearReference() {
    setReference(undefined); setReferencePainted(false); setCrop(undefined);
  }

  function clearResults() {
    setBase(undefined); setRefined(undefined); setTargetPainted(false);
    setOriginalComparison(true); setMaskTab('target'); clearReference();
  }

  function resetPreview() {
    setPreviewReady(false); setPreviewReleased(false); setView(null); setFrames([]);
    lastCapture.current = undefined;
  }

  function pickReference(file: File) {
    void perform('upload', async (signal) => {
      const result = await uploadPortrait('reference', file, signal);
      clearReference(); setReference(result);
      persist({ reference: result, crop: undefined });
    });
  }

  function build() {
    if (!source && !galleryPhoto) return;
    void perform('build', async (signal, onProgress) => {
      const input = source ?? await openGalleryPhoto(galleryPhoto!.id, signal);
      setSource(input);
      persist({ source: input });
      completeBuild(await runTracked('build', { source: input.token, lens }, onProgress, signal));
    });
  }

  function completeBuild(result: PortraitModel) {
    setModel(result); setModelVersion((version) => version + 1); resetPreview(); clearResults();
    persist({ model: result, view: null, frames: [], base: undefined, refined: undefined, reference: undefined, crop: undefined,
      maskTab: 'target', lastCapture: undefined, previewReleased: false });
  }

  function completeRepair(result: PortraitRepair) {
    clearResults(); setBase(result); navigate('compare');
    persist({ base: result, refined: undefined, reference: undefined, crop: undefined, page: 'compare', maskTab: 'target' });
  }

  function completeRefine(result: { image: string }) {
    setRefined(result.image);
    setMaskTab('result');
    workbench.current?.scrollTo({ top: 0 });
    persist({ refined: result.image, maskTab: 'result' });
  }

  async function captureOptions(cameraView: CameraView, signal: AbortSignal): Promise<PortraitCapture> {
    signal.throwIfAborted();
    const renderer = rendererRef.current;
    if (!renderer || !source || !model) throw new Error(t('portrait.restorePreview'));
    setCapturing(true);
    try {
      const { camera, blob } = await renderer.capture(cameraView, ratio, edge);
      const referenceCrop = await renderer.closeupReference(cameraView, camera);
      const capture = await uploadPortrait('capture', blob, signal);
      return { source: source.token, model: model.model, capture: capture.token, camera, lens, edge, referenceCrop };
    } finally {
      if (!signal.aborted) setCapturing(false);
    }
  }

  async function queueBatch(stage: 'repair' | 'refine', prepare: PortraitBatchRequest['prepare']) {
    setPreparing((value) => value + batchCount);
    setError(undefined);
    try {
      await enqueueBatch({ stage, count: batchCount, originId: workspaceId, photo: galleryPhoto,
        filename: sourceName ?? t('photoTools.original'), prepare });
      if (!disposed.current) setQueued(batchCount);
    } catch (problem) {
      if (!disposed.current) setError(describeError(problem));
    } finally {
      if (!disposed.current) setPreparing((value) => value - batchCount);
    }
  }

  function repair() {
    if (!view) return;
    const inputDraft: PortraitDraft = {
      ...snapshot.current, pending: undefined, error: undefined, page: 'frame', maskTab: 'target',
      base: undefined, refined: undefined, reference: undefined, crop: undefined,
    };
    const repairSeed = randomSeed ? crypto.getRandomValues(new Uint32Array(1))[0] : seed;
    void queueBatch('repair', async (signal) => {
      const cached = lastCapture.current;
      let options: PortraitCapture;
      const queuedCapture = repairCapture.current;
      if (cached?.view === view && cached.ratio === ratio && cached.edge === edge) {
        options = cached.options;
      } else if (queuedCapture?.view === view && queuedCapture.ratio === ratio && queuedCapture.edge === edge) {
        options = await queuedCapture.result;
      } else {
        const result = (async () => {
          await queuedCapture?.result.catch(() => {});
          return captureOptions(view, signal);
        })();
        repairCapture.current = { view, ratio, edge, result };
        try {
          options = await result;
        } finally {
          if (repairCapture.current?.result === result) repairCapture.current = null;
        }
      }
      signal.throwIfAborted();
      const capture = { view, ratio, edge, options };
      lastCapture.current = capture;
      if (releaseOnRepair) { setPreviewReady(false); setPreviewReleased(true); }
      persist({ lastCapture: capture, previewReleased: previewReleased || releaseOnRepair });
      const { referenceCrop, ...target } = options;
      return { draft: { ...inputDraft, lastCapture: capture, previewReleased: previewReleased || releaseOnRepair },
        options: { ...target, seed: repairSeed, repair_reference_edge: repairReferenceEdge, repair_prompt: repairPrompt,
          reference_crop: matchCloseup ? referenceCrop : undefined } };
    });
  }

  function refine() {
    const texture = targetMask.current;
    if (!source || !base || !texture || !targetPainted) return;
    const inputDraft: PortraitDraft = { ...snapshot.current, pending: undefined, error: undefined, refined: undefined };
    const referenceTexture = referencePainted ? referenceMask.current : null;
    void queueBatch('refine', async (signal) => {
      const [mask, sourceMask] = await Promise.all([
        canvasPng(texture).then((image) => uploadPortrait('mask', image, signal)),
        referenceTexture ? canvasPng(referenceTexture).then((image) => uploadPortrait('mask', image, signal)) : undefined,
      ]);
      return { draft: inputDraft, options: { source: source.token, base: base.base, mask: mask.token, reference_mask: sourceMask?.token,
        reference: reference?.token, crop, prompt, strength, reference_edge: referenceEdge,
        sample_edge: sampleEdge, expand, feather, color, optimize } };
    });
  }

  async function exportTrajectory(samples: Array<{ view: CameraView; keyframe: boolean }>, mode: 'preview' | 'repair') {
    await perform('frame', async (signal, onProgress) => {
      setFrames([]);
      stopFrames.current = false;
      const time = new Date().toISOString().slice(0, 19).replace(/[-:]/g, '').replace('T', '-');
      const random = Array.from(crypto.getRandomValues(new Uint8Array(4)), (byte) => byte.toString(16).padStart(2, '0')).join('');
      pending.current = { stage: 'frame', startedAt: startedAtRef.current, trajectory: { samples, sequence: `${time}-${random}`, mode, nextIndex: 0 } };
      persist({ frames: [] });
      await processTrajectory(pending.current.trajectory!, signal, onProgress);
    });
  }

  async function processTrajectory(trajectory: PortraitTrajectory, signal: AbortSignal, onProgress: (next: PortraitProgress) => void) {
    const { samples, sequence, mode } = trajectory;
    for (let offset = trajectory.nextIndex; offset < samples.length; offset += 1) {
      let options: Record<string, unknown> | undefined;
      if (!pending.current?.job && !pending.current?.requestId) {
        if (stopFrames.current || pending.current?.trajectory?.stopped) break;
        const deadline = Date.now() + 60000;
        while (!rendererRef.current && Date.now() < deadline) {
          signal.throwIfAborted();
          await new Promise<void>((resolve) => window.setTimeout(resolve, 200));
        }
        const { referenceCrop, ...capture } = await captureOptions(samples[offset].view, signal);
        if (stopFrames.current) break;
        options = {
          ...capture, seed, repair_reference_edge: repairReferenceEdge, repair_prompt: repairPrompt,
          reference_crop: mode === 'repair' && matchCloseup ? referenceCrop : undefined,
          sequence, mode, count: samples.length, index: offset + 1, keyframe: samples[offset].keyframe,
        };
      }
      setFrameIndex({ index: offset + 1, total: samples.length });
      const result = await runTracked('frame', options, onProgress, signal);
      const results = [...(snapshot.current.frames ?? []), result];
      pending.current = { stage: 'frame', startedAt: startedAtRef.current, trajectory: {
        ...trajectory, nextIndex: offset + 1, stopped: stopFrames.current || pending.current?.trajectory?.stopped,
      } };
      persist({ frames: results });
      setFrames(results);
    }
  }

  function stopTrajectory() {
    stopFrames.current = true;
    if (pending.current?.trajectory) {
      pending.current = { ...pending.current, trajectory: { ...pending.current.trajectory, stopped: true } };
      persist();
    }
  }

  resume.current = () => {
    const job = pending.current;
    if (!job) return;
    void perform(job.stage, async (signal, onProgress) => {
      if (job.stage === 'build') completeBuild(await runTracked('build', undefined, onProgress, signal));
      if (job.stage === 'repair') completeRepair(await runTracked('repair', undefined, onProgress, signal));
      if (job.stage === 'refine') completeRefine(await runTracked('refine', undefined, onProgress, signal));
      if (job.stage === 'frame' && job.trajectory) await processTrajectory(job.trajectory, signal, onProgress);
    }, true);
  };

  function navigate(next: typeof page) {
    setPage(next);
    workbench.current?.scrollTo({ top: 0 });
  }

  async function startEngine() {
    setLaunchPending(true);
    setLaunchError(undefined);
    try {
      const { state } = await startPortraitEngine();
      if (state === 'starting') {
        monitorStartup.current = true;
        setAvailable((previous) => previous && { ...previous, code: 'portraitStarting' });
      }
      setHealthVersion((version) => version + 1);
    } catch (problem) {
      setLaunchError(describeError(problem).code);
    } finally {
      setLaunchPending(false);
    }
  }

  const errorKey = error?.code && t(`portrait.errors.${error.code}`, { defaultValue: '' });
  const canCapture = previewReady || (previewReleased && lastCapture.current?.view === view
    && lastCapture.current.ratio === ratio && lastCapture.current.edge === edge);
  const startingEngine = launchPending || available?.code === 'portraitStarting';
  const connectionKey = startingEngine ? 'starting' : !available ? 'checking' : available.ready ? 'connected' : available.missing.length ? 'missing' : 'offline';
  const canStart = canGenerate && available?.can_start
    && (startingEngine || available.code === 'portraitOffline' || available.code === 'portraitStartTimeout');
  const sourceUrl = source?.url ?? galleryPhoto?.full_url ?? galleryPhoto?.preview_url;
  const outputFrame = model && cameraFrame(model.intrinsics, ratio);
  const outputLabel = outputFrame ? [outputFrame.width, outputFrame.height].map((dimension) =>
    Math.max(64, Math.round(dimension * edge / Math.max(outputFrame.width, outputFrame.height) / 32) * 32)).join(' × ') : `${edge} px`;
  const nodeName = progress.node ? nodeNames[progress.node] ?? 'processing' : undefined;

  if (backgroundJob && !active && stage !== 'frame') return null;

  return <div className={styles.workbench} ref={workbench} hidden={!active}>
    <div className={styles.inner}>
      <header className={styles.header}>
        <div className={styles.headerTitle}>
          <nav aria-label={t('portrait.navigation')} className={styles.breadcrumb}>
            <Button variant="ghost" size="sm" type="button" icon={<ArrowLeft size={15} />} onClick={onBack}>{t('photoView')}</Button>
            <ChevronRight size={13} aria-hidden="true" /><span>{t('portrait.title')}</span>
          </nav>
          <h1>{t('portrait.title')}</h1>
        </div>
        <div className={styles.engineActions}>
          {active && <WorkflowInfo workflow="spatial-reframing" title={t('portrait.title')} />}
          <Button variant="ghost" size="sm" type="button" className={styles.connection} data-ready={available?.ready ?? false}
            icon={<i className={styles.connectionDot} />} aria-label={t('portrait.refreshConnection')}
            onClick={() => { setLaunchError(undefined); setHealthVersion((version) => version + 1); }} disabled={busy || launchPending}>
            {t(`portrait.${connectionKey}`)} <RefreshCw size={13} />
          </Button>
          <ReleaseCacheButton disabled={locked} canClearCache={canClearCache}
            onClick={() => void perform('release', async (signal) => {
              const result = await releasePortraitMemory(signal);
              onCacheCleared();
              setCacheRelease(result);
            })} />
        </div>
        <Button variant="secondary" size="sm" type="button" iconOnly icon={<X size={18} />} className={styles.closeWorkspace}
          aria-label={t('portrait.closeWorkspace')} data-tooltip={t('portrait.closeWorkspace')} onClick={() => onClose(workspaceId, true)} />
      </header>
      {!available?.ready && available && <div className={`${styles.banner} ${styles.engineBanner}`}>
        <div>
          <div role="status">
            {t(available.missing.length ? 'portrait.dependencies'
              : startingEngine ? 'portrait.startingHint'
              : available.code === 'portraitStartTimeout' ? 'portrait.startTimeout'
              : canStart ? 'portrait.startHint' : 'portrait.openComfy')}
            {available.missing.length > 0 && <ul>{available.missing.map((name) => <li key={name}>{name}</li>)}</ul>}
          </div>
          {launchError && <div role="alert" className={styles.launchError}>
            {t(`portrait.errors.${launchError}`, { defaultValue: t('portrait.errors.portraitStartFailed') })}
          </div>}
        </div>
        {canStart && <Button variant="primary" size="sm" type="button"
          icon={startingEngine ? <LoaderCircle size={16} className="spin" /> : <Play size={16} />}
          disabled={busy || startingEngine} onClick={() => void startEngine()}>
          {t(startingEngine ? 'portrait.starting' : 'portrait.startComfy')}
        </Button>}
      </div>}
      {!canGenerate && <div className={styles.banner}>{t('portrait.lanAccess')}</div>}
      <div className={styles.workspaceBar}>
        <Segments label={t('portrait.workflowSteps')} value={page} onChange={navigate} options={[
          { value: 'frame', label: t('portrait.camera'), icon: <Camera size={16} /> },
          { value: 'compare', label: t('portrait.repairResult'), icon: <Images size={16} />, disabled: !base },
          { value: 'refine', label: t('portrait.details'), icon: <Sparkles size={16} />, disabled: !base },
        ]} />
        <div className={styles.sourceTools} {...sourceDrop}>
          {sourceUrl && <PhotoSourcePreview src={sourceUrl} name={sourceName} width={galleryPhoto?.width} height={galleryPhoto?.height} />}
          <PhotoSourceDownload photo={galleryPhoto} source={source} name={sourceName} />
          <Button variant="ghost" size="sm" type="button" icon={<CloudUpload size={17} />} disabled={locked} onClick={() => sourceInput.current?.click()}>
            {t(sourceUrl ? 'portrait.replacePhoto' : 'portrait.selectPhoto')}
          </Button>
          <input ref={sourceInput} type="file" accept={workbenchPhotoAccept} hidden onChange={(event) => {
            const file = event.currentTarget.files?.[0];
            if (file && !locked) onChoosePhoto(file);
            event.currentTarget.value = '';
          }} />
        </div>
      </div>
      <div hidden={page !== 'frame'} className={styles.framePage} {...sourceDrop}>
        {model && sourceUrl ? <CameraEditor key={modelVersion} model={model} original={sourceUrl} view={view} onView={setView}
          enabled={active || capturing || stage === 'frame'}
          rendererRef={rendererRef} ratio={ratio} onRatio={setRatio} ready={previewReady} onReady={setPreviewReady}
          released={previewReleased} onRelease={setPreviewReleased} disabled={busy || capturing} outputLabel={outputLabel}
          action={<div className={styles.batchActions}>
            <BatchCount value={batchCount} onChange={setBatchCount} />
            <Button type="button" disabled={!canGenerate || !available?.ready || (busy && stage !== 'repair') || !view || !canCapture}
              onClick={repair} icon={<Sparkles size={17} />}>{t('portrait.repair')}</Button>
            <BatchNotice preparing={preparing} queued={queued} />
          </div>}
          settings={<>
            <PixelChoice label={t('portrait.outputSize')} value={edge} values={outputEdges} alignment={32} disabled={busy || capturing || previewReleased} onChange={setEdge} />
            <PixelChoice label={t('portrait.repairReferenceEdge')} value={repairReferenceEdge} values={outputEdges}
              alignment={32} disabled={busy} onChange={setRepairReferenceEdge} />
            <ToggleField label={t('portrait.matchCloseup')} checked={matchCloseup} disabled={busy} onChange={setMatchCloseup} />
            <ToggleField label={t('portrait.randomRepairSeed')} checked={randomSeed} disabled={busy} onChange={setRandomSeed} />
            {!randomSeed && <NumberField label={t('portrait.seed')} value={seed} min={0} max={Number.MAX_SAFE_INTEGER} steppers={false}
              disabled={busy} onChange={(value) => setSeed(Math.floor(value))} />}
            <ToggleField label={t('portrait.releaseOnRepair')} checked={releaseOnRepair} disabled={busy} onChange={setReleaseOnRepair} />
            <div className={styles.repairPrompt}>
              <label className={styles.prompt}>{t('portrait.repairPrompt')}
                <textarea value={repairPrompt ?? available?.repair_prompt ?? ''} maxLength={4000} disabled={locked}
                  placeholder={t('portrait.repairPromptDefault')}
                  onChange={(event) => setRepairPrompt(event.currentTarget.value)} />
              </label>
              <Button variant="ghost" size="sm" type="button" disabled={locked || repairPrompt === undefined}
                onClick={() => setRepairPrompt(undefined)}>{t('portrait.restoreDefaultPrompt')}</Button>
            </div>
          </>}
          trajectory={<Trajectory view={view} onView={setView} disabled={locked || !previewReady} onExport={exportTrajectory}
            exporting={stage === 'frame'} onStop={stopTrajectory} results={frames} />}
        /> : <div className={styles.startStudio}>
          {sourceUrl ? <img src={sourceUrl} alt={t('portrait.originalAngle')} /> : <div className={styles.startPlaceholder}>
            <CloudUpload size={41} strokeWidth={1.45} /><h2>{t('portrait.startTitle')}</h2><p>{t('portrait.formats')}</p>
            <Button variant="primary" size="lg" icon={<ImageIcon size={18} />} type="button" disabled={locked} onClick={() => sourceInput.current?.click()}>{t('portrait.selectPhoto')}</Button>
          </div>}
          {sourceUrl && <div className={styles.startActions}>
            <Button variant="primary" size="lg" icon={<Scan size={18} />} type="button" disabled={locked} onClick={build}>
              {t(stage === 'build' ? 'portrait.building' : 'portrait.build')}
            </Button>
          </div>}
        </div>}
        {sourceUrl && <div className={styles.sourceSettings}>
          <Button variant="ghost" size="sm" type="button" aria-expanded={sourceSettings} onClick={() => setSourceSettings(!sourceSettings)}>
            {t('portrait.sourceSettings')}
          </Button>
          {sourceSettings && <div className={styles.sourceSettingsFields}>
            <NumberField label={t('portrait.lens')} min={12} max={120} step={0.5} value={lens} disabled={locked}
              onChange={(value) => { setLens(value); setModel(undefined); resetPreview(); }} />
            {model && <Button variant="secondary" size="sm" type="button" disabled={locked} onClick={build}>{t('portrait.rebuild')}</Button>}
          </div>}
        </div>}
      </div>
      {base && source && <>
        <section className={styles.compareCard} hidden={page !== 'compare'} aria-label={t('portrait.repairResult')}>
          <div className={styles.resultHeader}>
            <Segments value={originalComparison ? 'original' : 'rough'} label={t('portrait.compareWith')}
              onChange={(value) => setOriginalComparison(value === 'original')} options={[
                { value: 'original', label: t('portrait.originalAngle') }, { value: 'rough', label: t('portrait.rough') },
              ]} />
            <Button variant="primary" size="sm" type="button" icon={<Sparkles size={17} />} onClick={() => navigate('refine')}>{t('portrait.goRefine')}</Button>
          </div>
          <ImageComparison key={base.base} before={originalComparison ? source.url : base.rough} after={base.image}
            beforeLabel={t(originalComparison ? 'portrait.originalAngle' : 'portrait.rough')} afterLabel={t('portrait.repaired')}
            resultActions={<PhotoResultActions image={base.image} tool="reframe" canUseResult={canGenerate}
              onContinue={(tool, image) => onContinue(tool, image, sourceName)} />} />
        </section>
        <section className={styles.refineWorkspace} hidden={page !== 'refine'} aria-label={t('portrait.details')}>
          <div className={styles.refineCanvas}>
            <Segments value={maskTab} label={t('portrait.maskImages')} onChange={setMaskTab} options={[
              { value: 'target', label: t('portrait.targetImage') }, { value: 'reference', label: t('portrait.reference') },
              { value: 'result', label: t('portrait.refinedResult'), disabled: !refined },
            ]} />
            <div hidden={maskTab !== 'target'}>
              <MaskEditor key={base.base} image={base.image} label={t('portrait.targetMask')}
                onCanvas={(canvas) => { targetMask.current = canvas; }} disabled={locked} onPaint={setTargetPainted} />
            </div>
            <div className={styles.referenceDrop} hidden={maskTab !== 'reference'} {...referenceDrop}>
              <MaskEditor key={reference?.url ?? base.reference} image={reference?.url ?? base.reference} label={t('portrait.reference')}
                onCanvas={(canvas) => { referenceMask.current = canvas; }} reference showResolution
                disabled={locked} crop={crop} onCrop={setCrop} onPaint={setReferencePainted}
                actions={<div className={styles.controlRow}>
                  <Button variant="secondary" size="sm" type="button" icon={<CloudUpload size={16} />} disabled={locked} onClick={() => referenceInput.current?.click()}>{t('portrait.uploadReference')}</Button>
                  {reference && <Button variant="ghost" size="sm" type="button" disabled={locked} onClick={clearReference}>{t('portrait.useOriginal')}</Button>}
                  <input type="file" accept={workbenchPhotoAccept} hidden ref={referenceInput} onChange={(event) => {
                    const file = event.currentTarget.files?.[0]; if (file) pickReference(file); event.currentTarget.value = '';
                  }} />
                </div>} />
            </div>
            {refined && <div hidden={maskTab !== 'result'}>
              <ImageComparison key={refined} before={base.image} after={refined} beforeLabel={t('portrait.repaired')} afterLabel={t('portrait.refined')}
                resultActions={<PhotoResultActions image={refined} tool="reframe" canUseResult={canGenerate}
                  onContinue={(tool, image) => onContinue(tool, image, sourceName)} />} />
            </div>}
          </div>
          <aside className={styles.refineControls}>
            <label className={styles.prompt}>{t('portrait.prompt')}<textarea placeholder={t('portrait.promptHint')} value={prompt} disabled={locked}
              maxLength={4000} onChange={(event) => setPrompt(event.currentTarget.value)} /></label>
            <RangeField label={t('portrait.strength')} min={0.1} max={1} step={0.01} value={strength} disabled={locked}
              display={`${Math.round(strength * 100)}%`} onChange={setStrength} />
            <Button variant="ghost" size="sm" type="button" aria-expanded={refineAdvanced} onClick={() => setRefineAdvanced(!refineAdvanced)}>
              {t('portrait.refineSettings')}
            </Button>
            {refineAdvanced && <div className={styles.refineAdvanced}>
              <PixelChoice label={t('portrait.referenceEdge')} disabled={locked} value={referenceEdge} values={[768, 1024, 1344, 1536, 2048]} onChange={setReferenceEdge} />
              <PixelChoice label={t('portrait.sampleEdge')} disabled={locked} value={sampleEdge} values={[768, 1024, 1536, 2048, 2560, 3072]} onChange={setSampleEdge} />
              <RangeField label={t('portrait.expand')} disabled={locked} min={0} max={30} step={1} value={expand} display={`${expand}%`} onChange={setExpand} />
              <RangeField label={t('portrait.feather')} disabled={locked} min={0} max={30} step={1} value={feather} display={`${feather}%`} onChange={setFeather} />
              <RangeField label={t('portrait.color')} disabled={locked} min={0} max={1} step={0.1} value={color} display={`${Math.round(color * 100)}%`} onChange={setColor} />
              <ToggleField label={t('portrait.optimize')} disabled={locked} checked={optimize} onChange={setOptimize} />
            </div>}
            <div className={styles.batchActions}>
              <BatchCount value={batchCount} onChange={setBatchCount} />
              <Button type="button" disabled={locked || !targetPainted} onClick={refine} icon={<Sparkles size={17} />}>{t('portrait.refine')}</Button>
              <BatchNotice preparing={preparing} queued={queued} />
            </div>
          </aside>
        </section>
      </>}
    </div>
    {(stage || error || cacheRelease) && <aside className={`${styles.statusBar} ${error ? styles.error : ''}`} role={error ? 'alert' : 'status'}>
      {stage && <>
        <div className={styles.statusTitle}><strong>{t(`portrait.progress.${stage}`)}</strong>
          {stage === 'frame' && frameIndex && <span>{frameIndex.index} / {frameIndex.total}</span>}</div>
        {stage !== 'release' && stage !== 'upload' && <WorkflowProgress progress={progress} nodeName={nodeName} />}
      </>}
      {error && <div className={styles.statusTitle}><div><strong>{errorKey || t('portrait.errors.portraitRunError')}</strong>
        {error.message && <small>{error.message}</small>}</div><Button variant="ghost" size="sm" type="button" onClick={() => setError(undefined)}>{t('close')}</Button></div>}
      {cacheRelease && <CacheReleaseStatus result={cacheRelease} onClose={() => setCacheRelease(undefined)} />}
    </aside>}
  </div>;
}
