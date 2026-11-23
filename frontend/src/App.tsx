import { memo, useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';

import { useTranslation } from 'react-i18next';
import { useShallow } from 'zustand/react/shallow';
import type { TFunction } from 'i18next';

import {
  ApiError,
  fetchAuthStatus,
  fetchModelAssets,
  fetchSettings,
  fetchTasks,
  generateFromImages,
  importModelAssets,
} from '@/api';
import { openPortraitResult, recentPortraitJobs, uploadPortrait } from '@/api/portrait';
import { AccessGate, AccessSetupPrompt } from '@/components/auth';
import { ConfirmDialog, ImageViewer, Loading } from '@/components/common';
import { CloseIcon, CloudUploadIcon } from '@/components/common/Icons';
import { ParticleBackground } from '@/components/common/ParticleBackground';
import { GlobalTooltip } from '@/components/common/Tooltip';
import { Settings, Sidebar } from '@/components/layout';
import { Help } from '@/components/layout/Help/Help';
import {
  ModelAssetImportDialog,
  ModelAssetLibraryView,
  ModelAssetSidebarPanel,
} from '@/components/modelAssets';
import {
  PhotoAlbumList,
  PhotoGalleryView,
  VideoReconstructionDialog,
  VideoReconstructionGuide,
} from '@/components/photoGallery';
import { ViewerCanvas } from '@/components/viewer/ViewerCanvas/ViewerCanvas';
import { PortraitWorkbench } from '@/components/portrait/PortraitWorkbench';
import { restoreCaptureView } from '@/components/portrait/PortraitWorkbench/portraitRenderer';
import { useTaskQueue } from '@/hooks/useTaskQueue';
import { useModelSourceLinks } from '@/hooks/useModelSources';
import { SourceModelPanel } from '@/components/photoGallery/SourceModelPanel';
import { ImageEditWorkbench } from '@/components/photoGallery/ImageEditWorkbench';
import { useAppStore } from '@/store';
import { clearPortraitSession, newPortraitId, readPortraitSession, removePortraitDraft, savePortraitDraft, savePortraitSession } from '@/store/portraitSession';
import type { AngleWorkspace, EnqueuePortraitBatch, PortraitWorkspaceActions } from '@/store/portraitSession';
import { localizeModelAssetError, resolveModelAssetSource } from '@/utils';
import { detectImportedModelOrientation } from '@/utils/importedModelPreview';
import type { PhotoItem } from '@/types';
import type { PhotoTool, PortraitTask, PortraitUpload } from '@/types/portrait';
import type {
  ModelAssetImportFileEntry,
  ModelAssetImportPhase,
} from '@/components/modelAssets';

import './App.css';

const ACCESS_SETUP_PROMPT_SUPPRESSED_KEY = 'sharp-access-setup-prompt-suppressed';
const AngleWorkbench = memo(PortraitWorkbench);
const EditWorkbench = memo(ImageEditWorkbench);
const PHOTO_PICKER_WORKSPACE = 'photo-picker';

type DroppedModelFormat = 'ply' | 'splat' | 'spz' | 'rad';
type ModelAssetImportOrigin = 'library' | 'preview' | 'main-batch';

interface TemporaryModelPreview {
  file: File;
  format: DroppedModelFormat;
  url: string;
  editCandidate?: boolean;
}

interface ModelAssetImportDialogState {
  origin: ModelAssetImportOrigin;
  phase: ModelAssetImportPhase;
  progress: number;
  files: ModelAssetImportFileEntry[];
  importedCount: number;
  failedCount: number;
  errorMessage: string | null;
}

function toFileArray(files: FileList | File[]): File[] {
  return Array.from(files);
}

function getDroppedModelFormat(file: File): DroppedModelFormat | null {
  const name = file.name.toLowerCase();
  if (name.endsWith('.ply')) return 'ply';
  if (name.endsWith('.splat')) return 'splat';
  if (name.endsWith('.spz')) return 'spz';
  if (name.endsWith('.rad')) return 'rad';
  return null;
}

function isImageUpload(file: File): boolean {
  return file.type.startsWith('image/') || /\.(jpe?g|png|webp)$/i.test(file.name);
}

function isVideoUpload(file: File): boolean {
  return file.type.startsWith('video/') || /\.(mp4|m4v|mov|webm|mkv)$/i.test(file.name);
}

function getImportErrorMessage(error: unknown, t: TFunction): string {
  if (error instanceof ApiError) {
    return localizeModelAssetError(t, error.data?.code, error.data?.error ?? error.message);
  }
  return error instanceof Error ? error.message : t('modelAssetGenericError');
}

function createImportFileEntries(files: File[]): ModelAssetImportFileEntry[] {
  return files.map((file, index) => ({
    id: `${index}-${file.name}-${file.size}-${file.lastModified}`,
    name: file.name,
    status: 'pending',
  }));
}

function completeImportFileEntries(
  files: File[],
  failures: Array<{ filename: string; code?: string; error?: string }>,
  t: TFunction,
): ModelAssetImportFileEntry[] {
  const batchFailure = failures.find((failure) => !failure.filename);
  if (batchFailure) {
    return createImportFileEntries(files).map((entry) => ({
      ...entry,
      status: 'error',
      error: localizeModelAssetError(t, batchFailure.code, batchFailure.error),
    }));
  }

  const failuresByName = new Map<string, string[]>();
  failures.forEach((failure) => {
    const queued = failuresByName.get(failure.filename) ?? [];
    queued.push(localizeModelAssetError(t, failure.code, failure.error));
    failuresByName.set(failure.filename, queued);
  });

  return createImportFileEntries(files).map((entry) => {
    const queued = failuresByName.get(entry.name);
    const error = queued?.shift();
    return error
      ? { ...entry, status: 'error', error }
      : { ...entry, status: 'success' };
  });
}

function getImportFailuresFromError(
  error: unknown,
): Array<{ filename: string; code?: string; error?: string }> {
  if (!(error instanceof ApiError) || !Array.isArray(error.data?.failed)) {
    return [];
  }
  return error.data.failed.filter((item): item is { filename: string; code?: string; error?: string } => (
    Boolean(item)
    && typeof item === 'object'
    && typeof (item as { filename?: unknown }).filename === 'string'
  ));
}

function shouldShowAccessSetupPrompt(status: {
  is_owner: boolean;
  setup_recommended: boolean;
}) {
  if (!status.is_owner || !status.setup_recommended) {
    return false;
  }

  try {
    return localStorage.getItem(ACCESS_SETUP_PROMPT_SUPPRESSED_KEY) !== '1';
  } catch {
    return true;
  }
}

function App() {
  const modelReturnToPhotos = useAppStore((state) => state.modelReturnToPhotos);
  const { t } = useTranslation();
  const [showAccessSetupPrompt, setShowAccessSetupPrompt] = useState(false);
  const [modelAssetLibraryOpen, setModelAssetLibraryOpen] = useState(false);
  const [restoredAngles] = useState(readPortraitSession);
  const [angleWorkspaces, setAngleWorkspaces] = useState<AngleWorkspace[]>(restoredAngles.workspaces);
  const [{ active: activeAngleId, tasks: angleTasks }, setAngleQueue] = useState({
    active: restoredAngles.active, tasks: restoredAngles.tasks,
  });
  const [legacyRecoveryDone, setLegacyRecoveryDone] = useState(Boolean(restoredAngles.legacyRecoveryDone || restoredAngles.workspaces.length));
  const angleActions = useRef(new Map<string, PortraitWorkspaceActions>());
  const batchPreparations = useRef(new Map<AbortController, string>());
  const preparationOrder = useRef(Promise.resolve());
  const [preparingBatches, setPreparingBatches] = useState(0);
  const [angleCancellation, setAngleCancellation] = useState<{ task: PortraitTask; fromWorkbench: boolean }>();
  const [cancellingAngle, setCancellingAngle] = useState(false);
  const [angleCancellationError, setAngleCancellationError] = useState<string>();
  const [angleCacheRevision, setAngleCacheRevision] = useState(0);
  const angleTasksActive = preparingBatches > 0 || angleTasks.some(({ status }) => status === 'queued' || status === 'running');
  const nextPortraitSubmission = angleWorkspaces.find((workspace) => workspace.queueState === 'waiting')?.id;
  const clearAnglePreviews = useCallback(() => setAngleCacheRevision((revision) => revision + 1), []);
  const restoredAngleView = useRef(false);
  const hadAngleAccess = useRef(false);
  const [temporaryModelPreview, setTemporaryModelPreview] = useState<TemporaryModelPreview | null>(null);
  const temporaryModelPreviewRef = useRef<TemporaryModelPreview | null>(null);
  const [modelAssetImportDialog, setModelAssetImportDialog] = useState<ModelAssetImportDialogState | null>(null);
  const { 
    isBooting, 
    bootError,
    isLoading,
    loadingText,
    loadingProgress,
    sidebarCollapsed,
    activeView,
    authStatus,
    authPermissionError,
    isAuthenticated,
    isOwnerAccess,
    setBootComplete, 
    setBootError,
    setAuthStatus,
    setModelAssets,
    mergeModelAssetRefresh,
    setTasks,
    upsertTasks,
    setLocalAccess,
    setLoading,
    currentModelUrl,
    setSidebarOpen,
    toggleSidebar,
    setServerModelFormat,
    setCurrentModel,
    setAuthPermissionError,
    setSettingsModalOpen,
    setVideoReconstructionStatus,
    setLoadingProgress,
    modelAssetImporting,
    setModelAssetImporting,
    modelAssetBatchSize,
    preferredModelFormat,
    openVideoReconstructionFileDialog,
  } = useAppStore(
    useShallow((state) => ({
      isBooting: state.isBooting,
      bootError: state.bootError,
      isLoading: state.isLoading,
      loadingText: state.loadingText,
      loadingProgress: state.loadingProgress,
      sidebarCollapsed: state.sidebarCollapsed,
      activeView: state.activeView,
      authStatus: state.authStatus,
      authPermissionError: state.authPermissionError,
      isAuthenticated: state.isAuthenticated,
      isOwnerAccess: state.isOwnerAccess,
      setBootComplete: state.setBootComplete,
      setBootError: state.setBootError,
      setAuthStatus: state.setAuthStatus,
      setModelAssets: state.setModelAssets,
      mergeModelAssetRefresh: state.mergeModelAssetRefresh,
      setTasks: state.setTasks,
      upsertTasks: state.upsertTasks,
      setLocalAccess: state.setLocalAccess,
      setLoading: state.setLoading,
      currentModelUrl: state.currentModelUrl,
      setSidebarOpen: state.setSidebarOpen,
      toggleSidebar: state.toggleSidebar,
      setServerModelFormat: state.setServerModelFormat,
      setCurrentModel: state.setCurrentModel,
      setAuthPermissionError: state.setAuthPermissionError,
      setSettingsModalOpen: state.setSettingsModalOpen,
      setVideoReconstructionStatus: state.setVideoReconstructionStatus,
      setLoadingProgress: state.setLoadingProgress,
      modelAssetImporting: state.modelAssetImporting,
      setModelAssetImporting: state.setModelAssetImporting,
      modelAssetBatchSize: state.modelAssetBatchSize,
      preferredModelFormat: state.localModelFormat ?? state.serverModelFormat,
      openVideoReconstructionFileDialog: state.openVideoReconstructionFileDialog,
    })),
  );
  const canGenerateModels = isOwnerAccess || Boolean(
    authStatus?.access_control_enabled
    && isAuthenticated
    && authStatus.allow_remote_generation,
  );
  const canWriteModelAssets = canGenerateModels;
  const canDeleteModelAssets = isOwnerAccess;
  const angleActive = activeView === 'photos' && activeAngleId !== null;
  const hasPrivateAccess = isAuthenticated || isOwnerAccess;

  const relatedTasks = angleActive ? angleTasks.filter((task) => task.originId === activeAngleId) : [];
  const visibleBatchTask = relatedTasks.find((task) => task.status === 'running')
    ?? relatedTasks.filter((task) => task.status === 'queued').sort((a, b) => a.startedAt - b.startedAt)[0];

  const closeAngle = useCallback(() => setAngleQueue((previous) => ({ ...previous, active: null })), []);

  useEffect(() => {
    if (!authStatus) return;
    if (hasPrivateAccess) {
      hadAngleAccess.current = true;
      if (!restoredAngleView.current) {
        restoredAngleView.current = true;
        if (restoredAngles.active) useAppStore.getState().setActiveView('photos');
      }
    } else if (hadAngleAccess.current) {
      hadAngleAccess.current = false;
      for (const controller of batchPreparations.current.keys()) controller.abort();
      setAngleWorkspaces([]);
      setAngleQueue({ active: null, tasks: [] });
      setLegacyRecoveryDone(false);
      setAngleCancellation(undefined);
      clearPortraitSession();
    }
  }, [authStatus, hasPrivateAccess, restoredAngles.active]);

  useLayoutEffect(() => {
    if (hasPrivateAccess) savePortraitSession({
      workspaces: angleWorkspaces, tasks: angleTasks, active: angleActive ? activeAngleId : null, legacyRecoveryDone,
    });
  }, [activeAngleId, angleActive, angleTasks, angleWorkspaces, hasPrivateAccess, legacyRecoveryDone]);

  useEffect(() => {
    if (!isOwnerAccess || legacyRecoveryDone) return;
    const controller = new AbortController();
    void recentPortraitJobs(controller.signal).then((jobs) => {
      if (controller.signal.aborted) return;
      const workspaces = jobs.map((job, index) => {
        const id = `recovered:${job.id}`;
        savePortraitDraft(id, {
          source: job.source, model: job.model ?? undefined, lens: job.lens, edge: job.edge,
          ...(job.camera && job.model ? restoreCaptureView(job.camera, job.model) : {}),
          pending: { stage: job.stage, startedAt: job.started_at, job: job.job },
        });
        return { id, uploadName: t('portrait.recoveredPhoto', { number: index + 1 }) };
      });
      if (workspaces.length) setAngleWorkspaces((previous) => [...previous, ...workspaces]);
      setLegacyRecoveryDone(true);
    }).catch(() => {});
    return () => controller.abort();
  }, [isOwnerAccess, legacyRecoveryDone, t]);

  const selectAngle = useCallback((id: string) => {
    const store = useAppStore.getState();
    store.setPreviewPhoto(null);
    store.setActiveView('photos');
    setSidebarOpen(false);
    setAngleQueue((previous) => ({ ...previous, active: id }));
  }, [setSidebarOpen]);

  const markPortraitSubmitted = useCallback((id: string) => {
    setAngleWorkspaces((previous) => previous.some((workspace) => workspace.id === id && workspace.queueState === 'waiting')
      ? previous.map((workspace) => workspace.id === id ? { ...workspace, queueState: 'submitted' } : workspace)
      : previous);
  }, []);

  const updateAngleTask = useCallback((task: PortraitTask) => {
    if (task.status === 'completed' || task.status === 'failed') markPortraitSubmitted(task.workspaceId);
    const mayOpenResult = task.status === 'completed' && useAppStore.getState().activeView === 'photos';
    const preparingOrigins = mayOpenResult ? new Set(batchPreparations.current.values()) : undefined;
    setAngleQueue((previous) => {
      const last = previous.tasks.find((item) => item.workspaceId === task.workspaceId);
      if (!last) return { ...previous, tasks: [task, ...previous.tasks] };
      if (last.stage === task.stage && last.status === task.status
          && last.progress?.node === task.progress?.node && last.progress?.value === task.progress?.value
          && last.progress?.max === task.progress?.max
          && last.startedAt === task.startedAt && last.filename === task.filename) return previous;
      const origin = last.originId;
      const openResult = mayOpenResult && origin && origin === previous.active && !preparingOrigins?.has(origin)
        && !previous.tasks.some((item) => item.originId === origin && item.workspaceId !== task.workspaceId
          && (item.status === 'queued' || item.status === 'running'));
      return {
        active: openResult ? task.workspaceId : previous.active,
        tasks: previous.tasks.map((item) => item.workspaceId === task.workspaceId
          ? { ...item, ...task, progress: task.progress } : item),
      };
    });
  }, [markPortraitSubmitted]);

  const enqueuePortraitBatch = useCallback<EnqueuePortraitBatch>(({ stage, filename, count, originId, photo, prepare }) => {
    const controller = new AbortController();
    batchPreparations.current.set(controller, originId);
    setPreparingBatches((previous) => previous + 1);
    const startedAt = Date.now();
    // Start capturing immediately, but append batches in click order even if uploads finish out of order.
    const prepared = prepare(controller.signal);
    void prepared.catch(() => {});
    const queued = preparationOrder.current.then(async () => {
      const { draft, options } = await prepared;
      controller.signal.throwIfAborted();
      const tool = stage === 'edit' || stage === 'extend' ? stage : 'reframe';
      const workspaces: AngleWorkspace[] = [];
      const tasks: PortraitTask[] = [];
      for (let index = 0; index < count; index += 1) {
        const id = newPortraitId();
        const seed = typeof options.seed === 'number' ? Number((BigInt(options.seed) + BigInt(index)) % (1n << 53n)) : undefined;
        const jobOptions = seed === undefined ? options : { ...options, seed };
        const variant = seed === undefined ? draft
          : tool === 'reframe' ? { ...draft, seed } : { ...draft, edit: { ...draft.edit, seed: String(seed) } };
        const initialDraft = { ...variant, pending: { stage, options: jobOptions, startedAt, requestId: id } };
        savePortraitDraft(id, initialDraft);
        workspaces.push({ id, tool, photo, uploadName: filename, queueState: 'waiting', initialDraft });
        tasks.push({ workspaceId: id, originId, filename, stage, tool, status: 'queued', startedAt,
          batch: count > 1 ? { index: index + 1, count } : undefined });
      }
      setAngleWorkspaces((previous) => [...previous, ...workspaces]);
      setAngleQueue((previous) => ({ ...previous, tasks: [...tasks, ...previous.tasks] }));
    }).finally(() => {
      batchPreparations.current.delete(controller);
      setPreparingBatches((previous) => previous - 1);
    });
    preparationOrder.current = queued.catch(() => {});
    return queued;
  }, []);

  const registerAngleActions = useCallback((id: string, actions: PortraitWorkspaceActions) => {
    const registered = angleActions.current;
    registered.set(id, actions);
    return () => { registered.delete(id); };
  }, []);

  const removeAngle = useCallback((id: string) => {
    for (const [controller, originId] of batchPreparations.current) {
      if (originId === id) controller.abort();
    }
    angleActions.current.get(id)?.dispose();
    removePortraitDraft(id);
    setAngleWorkspaces((previous) => previous.filter((workspace) => workspace.id !== id));
    setAngleQueue((previous) => ({
      active: previous.active === id ? null : previous.active,
      tasks: previous.tasks.filter((task) => task.workspaceId !== id),
    }));
  }, []);

  const requestCloseAngle = useCallback((id: string, fromWorkbench = false) => {
    const task = angleTasks.find((item) => item.workspaceId === id);
    if (task && (task.status === 'running' || task.status === 'queued')) {
      setAngleCancellation({ task, fromWorkbench });
      setAngleCancellationError(undefined);
    } else {
      removeAngle(id);
    }
  }, [angleTasks, removeAngle]);

  async function cancelAngleTask() {
    if (!angleCancellation || cancellingAngle) return;
    const id = angleCancellation.task.workspaceId;
    const actions = angleActions.current.get(id);
    if (!actions) {
      setAngleCancellationError(t('portrait.taskQueue.cancelError'));
      return;
    }
    setCancellingAngle(true);
    setAngleCancellationError(undefined);
    try {
      await actions.cancel();
      removeAngle(id);
      setAngleCancellation(undefined);
    } catch (problem) {
      const code = problem instanceof ApiError ? problem.data?.code : undefined;
      setAngleCancellationError(t(code === 'portraitOffline' ? 'portrait.taskQueue.cancelOffline'
        : code === 'portraitExpired' ? 'portrait.taskQueue.cancelUnavailable' : 'portrait.taskQueue.cancelError'));
    } finally {
      setCancellingAngle(false);
    }
  }

  function openPhotoGallery() {
    closeAngle();
    useAppStore.getState().setActiveView('photos');
    setSidebarOpen(false);
  }

  const openPhotoTool = useCallback((tool: PhotoTool, photo?: PhotoItem) => {
    const photoKey = photo ? `gallery:${photo.id}` : PHOTO_PICKER_WORKSPACE;
    const id = tool === 'reframe' ? photoKey : `${tool}:${photoKey}`;
    setAngleWorkspaces((previous) => previous.some((workspace) => workspace.id === id) ? previous : [...previous, { id, tool, photo }]);
    selectAngle(id);
  }, [selectAngle]);

  const openToolSource = useCallback((tool: PhotoTool, filename: string, load: (signal: AbortSignal) => Promise<PortraitUpload>) => {
    const id = `upload:${newPortraitId()}`;
    const startedAt = Date.now();
    const controller = new AbortController();
    const result = load(controller.signal);
    // The receiving workbench handles the error once it mounts.
    void result.catch(() => {});
    setAngleWorkspaces((previous) => [...previous, {
      id, tool, upload: { filename, startedAt, result, abort: () => controller.abort() },
    }]);
    selectAngle(id);
  }, [selectAngle]);
  const openAngleUpload = useCallback((file: File) => {
    openToolSource('reframe', file.name, (signal) => uploadPortrait('source', file, signal));
  }, [openToolSource]);
  const openImageUpload = useCallback((tool: 'edit' | 'extend', file: File) => {
    openToolSource(tool, file.name, (signal) => uploadPortrait(`${tool}-source`, file, signal));
  }, [openToolSource]);
  const openToolResult = useCallback((tool: PhotoTool, image: string, name?: string) => {
    openToolSource(tool, name ?? t('photoTools.result'), (signal) => openPortraitResult(image, signal));
  }, [openToolSource, t]);

  const replaceTemporaryModelPreview = useCallback((next: TemporaryModelPreview | null) => {
    const previous = temporaryModelPreviewRef.current;
    if (previous && previous.url !== next?.url) {
      URL.revokeObjectURL(previous.url);
    }
    temporaryModelPreviewRef.current = next;
    setTemporaryModelPreview(next);
  }, []);

  useEffect(() => () => {
    const preview = temporaryModelPreviewRef.current;
    if (preview) {
      URL.revokeObjectURL(preview.url);
      temporaryModelPreviewRef.current = null;
    }
  }, []);

  const openModelAssetLibrary = useCallback(() => {
    setCurrentModel(null);
    replaceTemporaryModelPreview(null);
    setModelAssetLibraryOpen(true);
    setSidebarOpen(false);
  }, [replaceTemporaryModelPreview, setCurrentModel, setSidebarOpen]);

  const closeModelAssetLibrary = useCallback(() => {
    replaceTemporaryModelPreview(null);
    setModelAssetLibraryOpen(false);
    setSidebarOpen(false);
  }, [replaceTemporaryModelPreview, setSidebarOpen]);

  const loadPrivateData = useCallback(async () => {
    const modelAssets = await fetchModelAssets({ limit: modelAssetBatchSize });
    setModelAssets(modelAssets);

    const tasksData = await fetchTasks();
    setTasks(tasksData.tasks, tasksData.has_active);

    const settings = await fetchSettings();
    setLocalAccess(settings.is_local ?? false);
    if (settings.model_format) {
      setServerModelFormat(settings.model_format);
    }
    setVideoReconstructionStatus(null, settings.video_reconstruction);
  }, [
    modelAssetBatchSize,
    setLocalAccess,
    setModelAssets,
    setServerModelFormat,
    setTasks,
    setVideoReconstructionStatus,
  ]);

  useEffect(() => {
    async function init() {
      try {
        const status = await fetchAuthStatus();
        setAuthStatus(status);

        if (!status.authenticated && !status.is_owner) {
          setBootComplete();
          return;
        }

        await loadPrivateData();
        setShowAccessSetupPrompt(shouldShowAccessSetupPrompt(status));
        setBootComplete();
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) {
          const status = await fetchAuthStatus();
          setAuthStatus(status);
          setBootComplete();
          return;
        }
        const message = error instanceof Error ? error.message : 'Unknown error';
        setBootError(message);
      }
    }
    init();
  }, [loadPrivateData, setAuthStatus, setBootComplete, setBootError]);

  const dismissAccessSetupPrompt = useCallback(() => {
    setShowAccessSetupPrompt(false);
  }, []);

  const suppressAccessSetupPrompt = useCallback(() => {
    try {
      localStorage.setItem(ACCESS_SETUP_PROMPT_SUPPRESSED_KEY, '1');
    } catch {
      // Ignore storage errors and still dismiss for the current render tree.
    }
    setShowAccessSetupPrompt(false);
  }, []);

  const openAccessSettings = useCallback(() => {
    dismissAccessSetupPrompt();
    setSettingsModalOpen(true);
  }, [dismissAccessSetupPrompt, setSettingsModalOpen]);

  const handlePreviewModelFile = useCallback(async (file: File, format: DroppedModelFormat) => {
    console.log('📦 Loading dropped model:', file.name, 'format:', format);
    const blobUrl = URL.createObjectURL(file);
    const preview: TemporaryModelPreview = { file, format, url: blobUrl };
    replaceTemporaryModelPreview(preview);
    const viewerOrientation = await detectImportedModelOrientation(file, format);
    if (temporaryModelPreviewRef.current !== preview) return;
    replaceTemporaryModelPreview({ ...preview, editCandidate: format !== 'rad' && viewerOrientation !== 'default' });
    setModelAssetLibraryOpen(false);
    setCurrentModel({
      id: `temporary:${blobUrl}`,
      url: blobUrl,
      format,
      size: file.size,
      source: 'temporary',
      sourceMediaType: null,
      viewerOrientation,
    });
  }, [replaceTemporaryModelPreview, setCurrentModel]);

  const showGenerationPermissionError = useCallback(() => {
    const message = t('ownerOnlyAction');
    setAuthPermissionError(message);
  }, [t, setAuthPermissionError]);

  const showModelAssetWritePermissionError = useCallback(() => {
    setAuthPermissionError(t('modelAssetWritePermissionRequired'));
  }, [setAuthPermissionError, t]);

  const importModelFileArray = useCallback(async (
    files: File[],
    origin: ModelAssetImportOrigin,
    openEditor = false,
  ) => {
    if (files.length === 0 || useAppStore.getState().modelAssetImporting) {
      return;
    }
    if (!canGenerateModels) {
      showModelAssetWritePermissionError();
      return;
    }

    setModelAssetImporting(true);
    setModelAssetImportDialog({
      origin,
      phase: 'uploading',
      progress: 0,
      files: createImportFileEntries(files),
      importedCount: 0,
      failedCount: 0,
      errorMessage: null,
    });

    try {
      const result = await importModelAssets(files, {
        onUploadProgress: ({ percent }) => {
          setModelAssetImportDialog((current) => {
            if (!current || (percent < 100 && percent - current.progress < 4)) {
              return current;
            }
            return { ...current, progress: percent };
          });
        },
      });
      const completedFiles = completeImportFileEntries(files, result.failed, t);
      const failedCount = completedFiles.filter((entry) => entry.status === 'error').length;

      if (result.assets.length > 0) {
        try {
          const assetState = useAppStore.getState();
          const modelAssets = await fetchModelAssets({
            source: assetState.modelAssetSource,
            format: assetState.modelAssetFormat,
            tag: assetState.modelAssetTag,
            sort: assetState.modelAssetSort,
            limit: modelAssetBatchSize,
          });
          mergeModelAssetRefresh(modelAssets);
        } catch (refreshError) {
          console.warn('Model assets imported, but the library refresh failed:', refreshError);
        }
      }

      const firstAsset = result.assets[0];
      const firstModelSource = firstAsset ? resolveModelAssetSource(firstAsset, preferredModelFormat) : null;
      if (
        firstAsset
        && firstModelSource?.url
        && firstModelSource.format
        && (origin === 'preview' || origin === 'main-batch')
      ) {
        setModelAssetLibraryOpen(false);
        setCurrentModel({
          id: firstAsset.id,
          url: firstModelSource.url,
          format: firstModelSource.format,
          size: firstModelSource.size,
          source: firstAsset.source_type === 'imported' || firstAsset.is_imported
            ? 'model-asset-imported'
            : 'model-asset-generated',
          sourceMediaType: firstModelSource.sourceMediaType,
          viewerOrientation: firstModelSource.viewerOrientation,
          viewerCamera: firstModelSource.viewerCamera,
          viewerTransform: firstModelSource.viewerTransform,
        }, { openEditor: openEditor && firstAsset.editor_supported === true });
        replaceTemporaryModelPreview(null);
      }
      setModelAssetImporting(false);
      setModelAssetImportDialog({
        origin,
        phase: result.assets.length > 0 || failedCount === 0 ? 'complete' : 'error',
        progress: 100,
        files: completedFiles,
        importedCount: result.assets.length,
        failedCount,
        errorMessage: null,
      });
      if (openEditor && firstAsset?.editor_supported && firstModelSource?.url) {
        setModelAssetImportDialog(null);
      } else if (openEditor && firstAsset) {
        setAuthPermissionError(t('modelAssetEditUnsupported'));
      }
    } catch (error) {
      const message = getImportErrorMessage(error, t);
      const failures = getImportFailuresFromError(error);
      const completedFiles = failures.length > 0
        ? completeImportFileEntries(files, failures, t)
        : createImportFileEntries(files).map((entry) => ({
            ...entry,
            status: 'error' as const,
            error: message,
          }));
      if (error instanceof ApiError && error.status === 403) {
        showModelAssetWritePermissionError();
      }
      setModelAssetImporting(false);
      setModelAssetImportDialog({
        origin,
        phase: 'error',
        progress: 0,
        files: completedFiles,
        importedCount: 0,
        failedCount: files.length,
        errorMessage: `${t('modelAssetImportFailed')}: ${message}`,
      });
    } finally {
      setModelAssetImporting(false);
    }
  }, [
    canGenerateModels,
    modelAssetBatchSize,
    mergeModelAssetRefresh,
    preferredModelFormat,
    replaceTemporaryModelPreview,
    setAuthPermissionError,
    setCurrentModel,
    setModelAssetImporting,
    showModelAssetWritePermissionError,
    t,
  ]);

  const closeModelAssetImportDialog = useCallback(() => {
    if (useAppStore.getState().modelAssetImporting) {
      return;
    }
    setModelAssetImportDialog(null);
  }, []);

  const openLibraryFromImportDialog = useCallback(() => {
    if (useAppStore.getState().modelAssetImporting) {
      return;
    }
    setModelAssetImportDialog(null);
    openModelAssetLibrary();
  }, [openModelAssetLibrary]);

  const addTemporaryPreviewToLibrary = useCallback((openEditor = false) => {
    if (!temporaryModelPreview) {
      return;
    }
    void importModelFileArray([temporaryModelPreview.file], 'preview', openEditor);
  }, [importModelFileArray, temporaryModelPreview]);

  // Handle image/video upload or direct model preview
  const handleUpload = useCallback(async (files: FileList | File[]) => {
    const fileArray = toFileArray(files);
    if (fileArray.length === 0) {
      return;
    }

    if (activeView === 'models' && modelAssetLibraryOpen && !currentModelUrl) {
      await importModelFileArray(fileArray, 'library');
      return;
    }

    const modelFiles = fileArray
      .map((file) => ({ file, format: getDroppedModelFormat(file) }))
      .filter((entry): entry is { file: File; format: DroppedModelFormat } => Boolean(entry.format));
    const imageFiles = fileArray.filter(isImageUpload);
    const videoFiles = fileArray.filter(isVideoUpload);

    if (modelFiles.length > 0) {
      if (modelFiles.length !== fileArray.length) {
        setAuthPermissionError(t('unsupportedFormat'));
        return;
      }
      if (modelFiles.length === 1) {
        await handlePreviewModelFile(modelFiles[0].file, modelFiles[0].format);
        return;
      }
      await importModelFileArray(modelFiles.map((entry) => entry.file), 'main-batch');
      return;
    }

    if (videoFiles.length > 0) {
      if (videoFiles.length !== 1 || imageFiles.length > 0 || modelFiles.length > 0 || fileArray.length !== 1) {
        setAuthPermissionError(t('videoReconSingleVideoOnly'));
        return;
      }
      if (!canGenerateModels) {
        showGenerationPermissionError();
        return;
      }
      openVideoReconstructionFileDialog(videoFiles[0]);
      return;
    }

    if (imageFiles.length === 0 || imageFiles.length !== fileArray.length) {
      setAuthPermissionError(t('unsupportedFormat'));
      return;
    }

    if (!canGenerateModels) {
      showGenerationPermissionError();
      return;
    }

    try {
      setLoading(true, t('uploadingFiles', { count: imageFiles.length }));
      const result = await generateFromImages(imageFiles, {
        onUploadProgress: ({ percent }) => setLoadingProgress(percent),
      });
      setLoading(false);
      
      if (result.success && result.tasks) {
        upsertTasks(result.tasks);
      }
    } catch (error) {
      setLoading(false);
      const message = error instanceof Error ? error.message : 'Unknown error';
      if (error instanceof ApiError && error.status === 403) {
        showGenerationPermissionError();
        return;
      }
      setAuthPermissionError(`${t('uploadFailed')}: ${message}`);
    }
  }, [
    activeView,
    canGenerateModels,
    currentModelUrl,
    handlePreviewModelFile,
    importModelFileArray,
    modelAssetLibraryOpen,
    openVideoReconstructionFileDialog,
    showGenerationPermissionError,
    setAuthPermissionError,
    t,
    setLoading,
    setLoadingProgress,
    upsertTasks,
  ]);

  const handleFileDrop = useCallback((e: React.DragEvent) => {
    if (!e.dataTransfer.types.includes('Files')) return;
    e.preventDefault();
    e.stopPropagation();
    if (angleActive) return;
    
    const files = e.dataTransfer?.files;
    if (!files || files.length === 0) return;
    void handleUpload(files);
  }, [angleActive, handleUpload]);

  const handleMainDragOver = useCallback((e: React.DragEvent) => {
    if (!e.dataTransfer.types.includes('Files')) return;
    e.preventDefault();
    e.stopPropagation();
  }, []);

  // Task queue polling (must be called unconditionally before any early returns)
  useTaskQueue();
  useModelSourceLinks();

  // Boot screen
  if (isBooting) {
    return (
      <div className="boot-screen">
        <div className="boot-content">
          {bootError ? (
            <>
              <div className="boot-error-icon">⚠️</div>
              <h3>{t('errorOccurred')}</h3>
              <p className="boot-error-text">{bootError}</p>
            </>
          ) : (
            <>
              <div className="boot-spinner" />
              <h3>{t('loading')}</h3>
            </>
          )}
        </div>
      </div>
    );
  }

  if (!isAuthenticated && !isOwnerAccess) {
    return <AccessGate onUnlocked={loadPrivateData} />;
  }

  return (
    <div className="app-container">
      {/* Mobile menu button */}
      <button className="mobile-menu-btn" onClick={toggleSidebar}>
        <svg width="24" height="24" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>

      {/* Sidebar */}
      <Sidebar
        onOpenGallery={openPhotoGallery}
        angleTasks={angleTasks}
        activeAngleId={angleActive ? activeAngleId : null}
        onOpenAngle={selectAngle}
        onCloseAngle={requestCloseAngle}
        canGenerateModels={canGenerateModels}
        onGenerationBlocked={showGenerationPermissionError}
        onUpload={handleUpload}
      >
        {activeView === 'photos' ? (
          <PhotoAlbumList onOpenAlbum={closeAngle} />
        ) : activeView === 'models' ? (
          <ModelAssetSidebarPanel
            canDeleteAssets={canDeleteModelAssets}
            onOpenLibrary={openModelAssetLibrary}
            onOpenModel={closeModelAssetLibrary}
          />
        ) : null}
      </Sidebar>
      
      {/* Main content */}
      <main 
        className={`main-content ${!sidebarCollapsed ? 'sidebar-expanded' : ''}`}
        onDragOver={handleMainDragOver}
        onDrop={handleFileDrop}
      >
        {activeView === 'models' ? <ParticleBackground /> : null}
        
        {angleWorkspaces.map((workspace) => workspace.tool === 'edit' || workspace.tool === 'extend' ?
          <EditWorkbench key={workspace.id} tool={workspace.tool} workspaceId={workspace.id} active={angleActive && activeAngleId === workspace.id}
            batchTask={visibleBatchTask?.originId === workspace.id ? visibleBatchTask : undefined}
            canGenerate={canGenerateModels} galleryPhoto={workspace.photo} initialUpload={workspace.upload}
            canClearCache={!angleTasksActive} onCacheCleared={clearAnglePreviews}
            uploadName={workspace.uploadName} savedTask={restoredAngles.tasks.find((task) => task.workspaceId === workspace.id)}
            onBack={closeAngle} onClose={requestCloseAngle} onChoosePhoto={openImageUpload} onChooseGalleryPhoto={openPhotoTool}
            onTaskUpdate={updateAngleTask} onContinue={openToolResult} registerActions={registerAngleActions}
            enqueueBatch={enqueuePortraitBatch} onJobSubmitted={markPortraitSubmitted} initialDraft={workspace.initialDraft}
            waitForSubmission={workspace.queueState === 'waiting' && workspace.id !== nextPortraitSubmission} />
          : (
          <AngleWorkbench key={workspace.id} workspaceId={workspace.id} active={angleActive && activeAngleId === workspace.id}
            batchTask={visibleBatchTask?.originId === workspace.id ? visibleBatchTask : undefined}
            canGenerate={canGenerateModels} galleryPhoto={workspace.photo} initialUpload={workspace.upload}
            uploadName={workspace.uploadName} savedTask={restoredAngles.tasks.find((task) => task.workspaceId === workspace.id)}
            previewCacheRevision={angleCacheRevision} canClearCache={!angleTasksActive} onCacheCleared={clearAnglePreviews}
            onBack={closeAngle} onClose={requestCloseAngle} onChoosePhoto={openAngleUpload}
            onTaskUpdate={updateAngleTask} onContinue={openToolResult} registerActions={registerAngleActions}
            enqueueBatch={enqueuePortraitBatch} onJobSubmitted={markPortraitSubmitted} backgroundJob={Boolean(workspace.queueState)}
            initialDraft={workspace.initialDraft}
            waitForSubmission={workspace.queueState === 'waiting' && workspace.id !== nextPortraitSubmission} />
        ))}
        {activeView === 'photos' ? <PhotoGalleryView hidden={angleActive} onPhotoTool={openPhotoTool} /> : (
          modelAssetLibraryOpen && !currentModelUrl ? (
            <ModelAssetLibraryView
              canWriteAssets={canWriteModelAssets}
              canDeleteAssets={canDeleteModelAssets}
              onImportBlocked={showModelAssetWritePermissionError}
              onImportFiles={(files) => void importModelFileArray(files, 'library')}
            />
          ) : (
            <div className="viewer-container">
              {currentModelUrl && (modelAssetLibraryOpen || temporaryModelPreview || modelReturnToPhotos) ? (
                <div className="viewer-library-actions">
                  {modelAssetLibraryOpen || modelReturnToPhotos ? (
                    <button
                      className="viewer-library-back"
                      type="button"
                      onClick={() => {
                        setCurrentModel(null);
                        if (modelReturnToPhotos) {
                          useAppStore.getState().setActiveView('photos');
                          useAppStore.setState({ modelReturnToPhotos: false });
                        }
                      }}
                    >
                      {t(modelReturnToPhotos ? 'sourceBackToPhotos' : 'modelAssetBackToLibrary')}
                    </button>
                  ) : null}
                  {temporaryModelPreview ? (
                    <button
                      className="viewer-library-add"
                      type="button"
                      disabled={modelAssetImporting}
                      onClick={() => addTemporaryPreviewToLibrary()}
                    >
                      <CloudUploadIcon width={16} height={16} aria-hidden="true" />
                      {t('modelAssetAddToLibrary')}
                    </button>
                  ) : null}
                  {temporaryModelPreview?.editCandidate && isOwnerAccess ? (
                    <button
                      className="viewer-library-back"
                      type="button"
                      disabled={modelAssetImporting}
                      onClick={() => addTemporaryPreviewToLibrary(true)}
                    >
                      {t('modelAssetAddAndEdit')}
                    </button>
                  ) : null}
                </div>
              ) : null}

              {!currentModelUrl ? (
                <>
                  <div className="empty-state">
                    <svg className="empty-icon" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M21 7.5l-9-5.25L3 7.5m18 0l-9 5.25m9-5.25v9l-9 5.25M3 7.5l9 5.25M3 7.5v9l9 5.25m0-9v9" />
                    </svg>
                    <h3>{t('emptyStateTitle')}</h3>
                    <p>{t('emptyStateHint')}</p>
                  </div>

                  {!sidebarCollapsed ? (
                    <div className="drag-to-sidebar-hint">
                      <svg className="hint-arrow" viewBox="0 0 60 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M 58 12 L 12 12" strokeDasharray="4 4" />
                        <path d="M 20 4 L 12 12 L 20 20" />
                      </svg>
                      <div className="hint-text">
                        {t('dragToSidebarHint')}
                      </div>
                    </div>
                  ) : null}
                </>
              ) : null}

              <ViewerCanvas />
            </div>
          )
        )}

        {/* Loading overlay */}
        {isLoading && (
          <div className="loading-overlay">
            <Loading 
              text={loadingText} 
              progress={loadingProgress} 
            />
          </div>
        )}
      </main>

      {/* Settings Modal */}
      <Settings />

      <AccessSetupPrompt
        open={showAccessSetupPrompt && isOwnerAccess && Boolean(authStatus?.setup_recommended)}
        onDismiss={dismissAccessSetupPrompt}
        onNeverRemind={suppressAccessSetupPrompt}
        onOpenSettings={openAccessSettings}
      />
      
      {/* Help Panel - always visible */}
      <Help showCloseModel />
      
      {/* Lightbox / Image Viewer */}
      <ImageViewer onPhotoTool={openPhotoTool} />
      <SourceModelPanel />

      <VideoReconstructionDialog />

      <VideoReconstructionGuide />

      {angleCancellation && <ConfirmDialog
        isOpen
        title={t('portrait.taskQueue.cancelTitle')}
        message={angleCancellationError ?? (cancellingAngle ? t('portrait.taskQueue.cancelling')
          : t('portrait.taskQueue.cancelMessage', {
            name: angleCancellation.task.filename, tool: t(!angleCancellation.task.tool || angleCancellation.task.tool === 'reframe'
              ? 'portrait.title' : `photoTools.${angleCancellation.task.tool}`),
          }))}
        confirmLabel={t('portrait.taskQueue.cancelTitle')}
        cancelLabel={t(angleCancellation.fromWorkbench ? 'portrait.taskQueue.backInBackground' : 'portrait.taskQueue.keep')}
        danger
        isBusy={cancellingAngle}
        onConfirm={() => void cancelAngleTask()}
        onClose={() => { if (!cancellingAngle) setAngleCancellation(undefined); }}
        onCancel={() => {
          if (angleCancellation.fromWorkbench) closeAngle();
          setAngleCancellation(undefined);
        }}
      />}

      <ModelAssetImportDialog
        isOpen={Boolean(modelAssetImportDialog)}
        phase={modelAssetImportDialog?.phase ?? 'uploading'}
        progress={modelAssetImportDialog?.progress ?? 0}
        files={modelAssetImportDialog?.files ?? []}
        importedCount={modelAssetImportDialog?.importedCount ?? 0}
        failedCount={modelAssetImportDialog?.failedCount ?? 0}
        errorMessage={modelAssetImportDialog?.errorMessage}
        showViewLibrary={modelAssetImportDialog?.origin !== 'library'}
        onClose={closeModelAssetImportDialog}
        onOpenLibrary={openLibraryFromImportDialog}
      />

      {authPermissionError ? (
        <div className="app-notice app-notice-error" role="alert" aria-live="assertive">
          <span>{authPermissionError}</span>
          <button
            type="button"
            aria-label={t('close')}
            data-tooltip={t('close')}
            onClick={() => setAuthPermissionError(null)}
          >
            <CloseIcon width={14} height={14} />
          </button>
        </div>
      ) : null}

      <GlobalTooltip />
    </div>
  );
}

export default App;
