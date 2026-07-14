import { useCallback, useEffect, useState } from 'react';

import { useTranslation } from 'react-i18next';
import { useShallow } from 'zustand/react/shallow';

import {
  ApiError,
  fetchAuthStatus,
  fetchGallery,
  fetchSettings,
  fetchTasks,
  generateFromImages,
} from '@/api';
import { AccessGate, AccessSetupPrompt } from '@/components/auth';
import { GalleryList } from '@/components/gallery';
import { ImageViewer, Loading } from '@/components/common';
import { ParticleBackground } from '@/components/common/ParticleBackground';
import { GlobalTooltip } from '@/components/common/Tooltip';
import { Settings, Sidebar } from '@/components/layout';
import { Help } from '@/components/layout/Help/Help';
import {
  PhotoAlbumList,
  PhotoGalleryView,
  VideoReconstructionDialog,
  VideoReconstructionGuide,
} from '@/components/photoGallery';
import { useTaskQueue } from '@/hooks/useTaskQueue';
import { useAppStore } from '@/store';
import { ViewerCanvas } from '@/components/viewer/ViewerCanvas/ViewerCanvas';

import './App.css';

const ACCESS_SETUP_PROMPT_SUPPRESSED_KEY = 'sharp-access-setup-prompt-suppressed';
type DroppedModelFormat = 'ply' | 'splat' | 'spz' | 'rad';

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
    setTasks,
    setLocalAccess,
    setLoading,
    currentModelUrl,
    toggleSidebar,
    setServerModelFormat,
    setCurrentModel,
    setAuthPermissionError,
    setSettingsModalOpen,
    setVideoReconstructionStatus,
    setLoadingProgress,
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
      setTasks: state.setTasks,
      setLocalAccess: state.setLocalAccess,
      setLoading: state.setLoading,
      currentModelUrl: state.currentModelUrl,
      toggleSidebar: state.toggleSidebar,
      setServerModelFormat: state.setServerModelFormat,
      setCurrentModel: state.setCurrentModel,
      setAuthPermissionError: state.setAuthPermissionError,
      setSettingsModalOpen: state.setSettingsModalOpen,
      setVideoReconstructionStatus: state.setVideoReconstructionStatus,
      setLoadingProgress: state.setLoadingProgress,
      openVideoReconstructionFileDialog: state.openVideoReconstructionFileDialog,
    })),
  );
  const canGenerateModels = isOwnerAccess || Boolean(authStatus?.allow_remote_generation);

  useEffect(() => {
    if (!currentModelUrl?.startsWith('blob:')) {
      return undefined;
    }

    return () => URL.revokeObjectURL(currentModelUrl);
  }, [currentModelUrl]);

  const loadPrivateData = useCallback(async () => {
    const gallery = await fetchGallery();
    setGalleryItems(gallery);

    const tasksData = await fetchTasks();
    setTasks(tasksData.tasks, tasksData.has_active);

    const settings = await fetchSettings();
    setLocalAccess(settings.is_local ?? false);
    if (settings.model_format) {
      setServerModelFormat(settings.model_format);
    }
    setVideoReconstructionStatus(null, settings.video_reconstruction);
  }, [setGalleryItems, setTasks, setLocalAccess, setServerModelFormat, setVideoReconstructionStatus]);

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
    setCurrentModel(file.name, blobUrl, format, file.size);
  }, [setCurrentModel]);

  const showGenerationPermissionError = useCallback(() => {
    const message = t('ownerOnlyAction');
    setAuthPermissionError(message);
    alert(message);
  }, [t, setAuthPermissionError]);

  // Handle image/video upload or direct model preview
  const handleUpload = useCallback(async (files: FileList | File[]) => {
    const fileArray = toFileArray(files);
    if (fileArray.length === 0) {
      return;
    }

    const modelFiles = fileArray
      .map((file) => ({ file, format: getDroppedModelFormat(file) }))
      .filter((entry): entry is { file: File; format: DroppedModelFormat } => Boolean(entry.format));
    const imageFiles = fileArray.filter(isImageUpload);
    const videoFiles = fileArray.filter(isVideoUpload);

    if (fileArray.length === 1 && modelFiles.length === 1) {
      handlePreviewModelFile(modelFiles[0].file, modelFiles[0].format);
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
        setTasks(result.tasks, true);
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
    canGenerateModels,
    handlePreviewModelFile,
    openVideoReconstructionFileDialog,
    showGenerationPermissionError,
    t,
    setLoading,
    setLoadingProgress,
    setTasks,
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
        {activeView === 'photos' ? <PhotoAlbumList /> : <GalleryList />}
      </Sidebar>
      
      {/* Main content */}
      <main 
        className={`main-content ${!sidebarCollapsed ? 'sidebar-expanded' : ''}`}
        onDragOver={handleMainDragOver}
        onDrop={handleFileDrop}
      >
        {activeView === 'models' ? <ParticleBackground /> : null}
        
        {activeView === 'photos' ? <PhotoGalleryView /> : (
        <div className="viewer-container">
          {/* Empty state - shown when no model selected */}
          {!currentModelUrl && (
            <>
              <div className="empty-state">
                <svg className="empty-icon" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M21 7.5l-9-5.25L3 7.5m18 0l-9 5.25m9-5.25v9l-9 5.25M3 7.5l9 5.25M3 7.5v9l9 5.25m0-9v9" />
                </svg>
                <h3>{t('emptyStateTitle')}</h3>
                <p>{t('emptyStateHint')}</p>
              </div>

              {/* PC Desktop Hint for drag & drop model generation */}
              {!sidebarCollapsed && (
                <div className="drag-to-sidebar-hint">
                  <svg className="hint-arrow" viewBox="0 0 60 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M 58 12 L 12 12" strokeDasharray="4 4" />
                    <path d="M 20 4 L 12 12 L 20 20" />
                  </svg>
                  <div className="hint-text">
                    {t('dragToSidebarHint')}
                  </div>
                </div>
              )}
            </>
          )}

          {/* Viewer with internal empty state handling */}
          <ViewerCanvas />
        </div>
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

      <GlobalTooltip />
    </div>
  );
}

export default App;
