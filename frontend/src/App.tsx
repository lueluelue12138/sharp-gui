import { useCallback, useEffect, useRef, useState } from 'react';

import { useTranslation } from 'react-i18next';
import { useShallow } from 'zustand/react/shallow';

import {
  ApiError,
  fetchAuthStatus,
  fetchGallery,
  fetchModelAssets,
  fetchSettings,
  fetchTasks,
  generateFromImages,
  importModelAssets,
} from '@/api';
import { AccessGate, AccessSetupPrompt } from '@/components/auth';
import { ImageViewer, Loading } from '@/components/common';
import { CloudUploadIcon } from '@/components/common/Icons';
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
import { useTaskQueue } from '@/hooks/useTaskQueue';
import { useAppStore } from '@/store';
import { resolveModelAssetSource } from '@/utils';
import type {
  ModelAssetImportFileEntry,
  ModelAssetImportPhase,
} from '@/components/modelAssets';

import './App.css';

const ACCESS_SETUP_PROMPT_SUPPRESSED_KEY = 'sharp-access-setup-prompt-suppressed';
type DroppedModelFormat = 'ply' | 'splat' | 'spz' | 'rad';
type ModelAssetImportOrigin = 'library' | 'preview' | 'main-batch';

interface TemporaryModelPreview {
  file: File;
  format: DroppedModelFormat;
  url: string;
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
  return file.type.startsWith('video/') || /\.(mp4|m4v|mov|webm)$/i.test(file.name);
}

function getImportErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.data?.error ?? error.message;
  }
  return error instanceof Error ? error.message : 'Unknown error';
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
  failures: Array<{ filename: string; error: string }>,
): ModelAssetImportFileEntry[] {
  const batchFailure = failures.find((failure) => !failure.filename);
  if (batchFailure) {
    return createImportFileEntries(files).map((entry) => ({
      ...entry,
      status: 'error',
      error: batchFailure.error,
    }));
  }

  const failuresByName = new Map<string, string[]>();
  failures.forEach((failure) => {
    const queued = failuresByName.get(failure.filename) ?? [];
    queued.push(failure.error);
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
  const { t } = useTranslation();
  const [showAccessSetupPrompt, setShowAccessSetupPrompt] = useState(false);
  const [modelAssetLibraryOpen, setModelAssetLibraryOpen] = useState(false);
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
    isAuthenticated,
    isOwnerAccess,
    setBootComplete, 
    setBootError,
    setAuthStatus,
    setGalleryItems,
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
      isAuthenticated: state.isAuthenticated,
      isOwnerAccess: state.isOwnerAccess,
      setBootComplete: state.setBootComplete,
      setBootError: state.setBootError,
      setAuthStatus: state.setAuthStatus,
      setGalleryItems: state.setGalleryItems,
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
  const canGenerateModels = isOwnerAccess || Boolean(authStatus?.allow_remote_generation);

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
    setCurrentModel(null, null);
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
    const gallery = await fetchGallery();
    setGalleryItems(gallery);

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
    setGalleryItems,
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

  const handlePreviewModelFile = useCallback((file: File, format: DroppedModelFormat) => {
    console.log('📦 Loading dropped model:', file.name, 'format:', format);
    const blobUrl = URL.createObjectURL(file);
    replaceTemporaryModelPreview({ file, format, url: blobUrl });
    setModelAssetLibraryOpen(false);
    setCurrentModel(file.name, blobUrl, format, file.size, 'temporary');
  }, [replaceTemporaryModelPreview, setCurrentModel]);

  const showGenerationPermissionError = useCallback(() => {
    const message = t('ownerOnlyAction');
    setAuthPermissionError(message);
    alert(message);
  }, [t, setAuthPermissionError]);

  const importModelFileArray = useCallback(async (
    files: File[],
    origin: ModelAssetImportOrigin,
  ) => {
    if (files.length === 0 || useAppStore.getState().modelAssetImporting) {
      return;
    }
    if (!canGenerateModels) {
      showGenerationPermissionError();
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
      const completedFiles = completeImportFileEntries(files, result.failed);
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
        setCurrentModel(
          firstAsset.id,
          firstModelSource.url,
          firstModelSource.format,
          firstModelSource.size,
          firstAsset.is_imported ? 'model-asset-imported' : 'model-asset-generated',
        );
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
    } catch (error) {
      const message = getImportErrorMessage(error);
      if (error instanceof ApiError && error.status === 403) {
        showGenerationPermissionError();
      }
      setModelAssetImporting(false);
      setModelAssetImportDialog({
        origin,
        phase: 'error',
        progress: 0,
        files: createImportFileEntries(files).map((entry) => ({
          ...entry,
          status: 'error',
          error: message,
        })),
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
    setCurrentModel,
    setModelAssetImporting,
    showGenerationPermissionError,
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

  const addTemporaryPreviewToLibrary = useCallback(() => {
    if (!temporaryModelPreview) {
      return;
    }
    void importModelFileArray([temporaryModelPreview.file], 'preview');
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
        alert(t('unsupportedFormat'));
        return;
      }
      if (modelFiles.length === 1) {
        handlePreviewModelFile(modelFiles[0].file, modelFiles[0].format);
        return;
      }
      await importModelFileArray(modelFiles.map((entry) => entry.file), 'main-batch');
      return;
    }

    if (videoFiles.length > 0) {
      if (videoFiles.length !== 1 || imageFiles.length > 0 || modelFiles.length > 0 || fileArray.length !== 1) {
        alert(t('videoReconSingleVideoOnly'));
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
      alert(t('unsupportedFormat'));
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
      alert(`${t('uploadFailed')}: ${message}`);
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
    t,
    setLoading,
    setLoadingProgress,
    upsertTasks,
  ]);

  const handleFileDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    
    const files = e.dataTransfer?.files;
    if (!files || files.length === 0) return;
    void handleUpload(files);
  }, [handleUpload]);

  const handleMainDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  }, []);

  // Task queue polling (must be called unconditionally before any early returns)
  useTaskQueue();

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
        canGenerateModels={canGenerateModels}
        onGenerationBlocked={showGenerationPermissionError}
        onUpload={handleUpload}
      >
        {activeView === 'photos' ? (
          <PhotoAlbumList />
        ) : (
          <ModelAssetSidebarPanel
            onOpenLibrary={openModelAssetLibrary}
            onOpenModel={closeModelAssetLibrary}
          />
        )}
      </Sidebar>
      
      {/* Main content */}
      <main 
        className={`main-content ${!sidebarCollapsed ? 'sidebar-expanded' : ''}`}
        onDragOver={handleMainDragOver}
        onDrop={handleFileDrop}
      >
        {activeView === 'models' ? <ParticleBackground /> : null}
        
        {activeView === 'photos' ? <PhotoGalleryView /> : (
          modelAssetLibraryOpen && !currentModelUrl ? (
            <ModelAssetLibraryView
              canImportAssets={canGenerateModels}
              onImportBlocked={showGenerationPermissionError}
              onImportFiles={(files) => void importModelFileArray(files, 'library')}
            />
          ) : (
            <div className="viewer-container">
              {currentModelUrl && (modelAssetLibraryOpen || temporaryModelPreview) ? (
                <div className="viewer-library-actions">
                  {modelAssetLibraryOpen ? (
                    <button
                      className="viewer-library-back"
                      type="button"
                      onClick={() => setCurrentModel(null, null)}
                    >
                      {t('modelAssetBackToLibrary')}
                    </button>
                  ) : null}
                  {temporaryModelPreview ? (
                    <button
                      className="viewer-library-add"
                      type="button"
                      disabled={modelAssetImporting}
                      onClick={addTemporaryPreviewToLibrary}
                    >
                      <CloudUploadIcon width={16} height={16} aria-hidden="true" />
                      {t('modelAssetAddToLibrary')}
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
      <ImageViewer />

      <VideoReconstructionDialog />

      <VideoReconstructionGuide />

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

      <GlobalTooltip />
    </div>
  );
}

export default App;
