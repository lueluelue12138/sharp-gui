import { create } from 'zustand';
import { getLodPresetConfig } from '@/constants/spark';
import { getGalleryModelSource, reconcileGalleryItems } from '@/utils';
import {
  DEFAULT_REVEAL_EFFECT_PREFERENCE_ID,
  REVEAL_EFFECT_NONE_ID,
  isRevealEffectPreferenceId,
  type RevealEffectPreferenceId,
} from '@/utils/viewerRevealEffects';
import type {
  AppView,
  AuthStatusResponse,
  GalleryItem,
  ModelFormat,
  PhotoAlbum,
  PhotoItem,
  PhotoMediaCounts,
  PhotoMediaType,
  Task,
  VideoReconstructionConfig,
  VideoReconstructionDependencies,
  ViewerInteractionState,
  ViewerOrientationPreset,
  ViewerQualityState,
  ViewerQuickControlsOverride,
  ViewerTransformState,
} from '@/types';
import type {
  LodCompareMode,
  LodPresetKey,
  QuickPresetMode,
  XrUpdateMode,
  ViewerModelFormat,
} from '@/constants/spark';

// localStorage keys for client-side preference overrides
const LOCAL_FORMAT_KEY = 'sharp-model-format';
const LOCAL_LOD_KEY = 'sharp-lod-enabled';
const LOCAL_HF_KEY = 'sharp-high-fidelity';
const LOCAL_LOD_PRESET_KEY = 'sharp-lod-preset';
const LOCAL_QUICK_PRESET_KEY = 'sharp-quick-preset-mode';
const LOCAL_LOD_COMPARE_KEY = 'sharp-lod-compare-mode';
const LOCAL_RAD_MODE_KEY = 'sharp-rad-mode-enabled';
const LOCAL_RAD_PAGED_KEY = 'sharp-rad-paged-enabled';
const LOCAL_XR_UPDATE_MODE_KEY = 'sharp-xr-update-mode';
const LOCAL_QUICK_OVERRIDES_KEY = 'sharp-viewer-quick-overrides-v1';
const LOCAL_DEFAULT_REVEAL_EFFECT_KEY = 'sharp-default-reveal-effect';
const DEFAULT_PHOTO_MEDIA_COUNTS: PhotoMediaCounts = {
  all: 0,
  image: 0,
  photo: 0,
  video: 0,
};
const DEFAULT_VIDEO_RECONSTRUCTION_CONFIG: VideoReconstructionConfig = {
  default_quality: 'high',
  default_engine: 'auto',
  vram_budget: '12gb',
  keep_intermediate_files: false,
};

const QUALITY_LIMITS = {
  lodScale: { min: 0.2, max: 3.0 },
  coneFoveate: { min: 0, max: 1 },
  behindFoveate: { min: 0, max: 1 },
};

const DEFAULT_VIEWER_TRANSFORM: ViewerTransformState = {
  positionX: 0,
  positionY: 0,
  positionZ: 0,
  rotationX: Math.PI,
  rotationY: 0,
  rotationZ: 0,
  scale: 2,
};

const DEFAULT_VIEWER_INTERACTION: ViewerInteractionState = {
  reversePointerDirection: false,
  reversePointerSlide: false,
};

function clampNumber(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function safeNumber(value: unknown, fallback: number): number {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  return fallback;
}

function normalizeRadians(value: number): number {
  let angle = value;
  while (angle > Math.PI) angle -= 2 * Math.PI;
  while (angle < -Math.PI) angle += 2 * Math.PI;
  return angle;
}

function getViewerQualityFromPreset(
  preset: LodPresetKey,
  lodEnabled: boolean,
): ViewerQualityState {
  const presetConfig = getLodPresetConfig(preset);
  return {
    lodEnabled,
    lodScale: presetConfig.lodSplatScale,
    coneFoveate: presetConfig.coneFoveate,
    behindFoveate: presetConfig.behindFoveate,
  };
}

function sanitizeViewerTransform(
  value?: Partial<ViewerTransformState>,
): ViewerTransformState {
  return {
    positionX: safeNumber(value?.positionX, DEFAULT_VIEWER_TRANSFORM.positionX),
    positionY: safeNumber(value?.positionY, DEFAULT_VIEWER_TRANSFORM.positionY),
    positionZ: safeNumber(value?.positionZ, DEFAULT_VIEWER_TRANSFORM.positionZ),
    rotationX: normalizeRadians(safeNumber(value?.rotationX, DEFAULT_VIEWER_TRANSFORM.rotationX)),
    rotationY: normalizeRadians(safeNumber(value?.rotationY, DEFAULT_VIEWER_TRANSFORM.rotationY)),
    rotationZ: normalizeRadians(safeNumber(value?.rotationZ, DEFAULT_VIEWER_TRANSFORM.rotationZ)),
    scale: clampNumber(safeNumber(value?.scale, DEFAULT_VIEWER_TRANSFORM.scale), 0.05, 20),
  };
}

function sanitizeViewerInteraction(
  value?: Partial<ViewerInteractionState>,
): ViewerInteractionState {
  return {
    reversePointerDirection: Boolean(value?.reversePointerDirection),
    reversePointerSlide: Boolean(value?.reversePointerSlide),
  };
}

function sanitizeViewerQuality(
  value: Partial<ViewerQualityState> | undefined,
  fallback: ViewerQualityState,
): ViewerQualityState {
  return {
    lodEnabled: typeof value?.lodEnabled === 'boolean' ? value.lodEnabled : fallback.lodEnabled,
    lodScale: clampNumber(
      safeNumber(value?.lodScale, fallback.lodScale),
      QUALITY_LIMITS.lodScale.min,
      QUALITY_LIMITS.lodScale.max,
    ),
    coneFoveate: clampNumber(
      safeNumber(value?.coneFoveate, fallback.coneFoveate),
      QUALITY_LIMITS.coneFoveate.min,
      QUALITY_LIMITS.coneFoveate.max,
    ),
    behindFoveate: clampNumber(
      safeNumber(value?.behindFoveate, fallback.behindFoveate),
      QUALITY_LIMITS.behindFoveate.min,
      QUALITY_LIMITS.behindFoveate.max,
    ),
  };
}

function getDefaultViewerOverride(
  quality: ViewerQualityState,
): ViewerQuickControlsOverride {
  return {
    transform: { ...DEFAULT_VIEWER_TRANSFORM },
    interaction: { ...DEFAULT_VIEWER_INTERACTION },
    quality: { ...quality },
  };
}

function sanitizeViewerOverride(
  value: unknown,
  fallbackQuality: ViewerQualityState,
): ViewerQuickControlsOverride {
  if (!value || typeof value !== 'object') {
    return getDefaultViewerOverride(fallbackQuality);
  }

  const candidate = value as Partial<ViewerQuickControlsOverride>;
  return {
    transform: sanitizeViewerTransform(candidate.transform),
    interaction: sanitizeViewerInteraction(candidate.interaction),
    quality: sanitizeViewerQuality(candidate.quality, fallbackQuality),
  };
}

function getLocalQuickOverrides(
  fallbackQuality: ViewerQualityState,
): Record<string, ViewerQuickControlsOverride> {
  try {
    const raw = localStorage.getItem(LOCAL_QUICK_OVERRIDES_KEY);
    if (!raw) return {};

    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== 'object') return {};

    const result: Record<string, ViewerQuickControlsOverride> = {};
    for (const [modelId, overrideValue] of Object.entries(
      parsed as Record<string, unknown>,
    )) {
      if (!modelId) continue;
      result[modelId] = sanitizeViewerOverride(overrideValue, fallbackQuality);
    }

    return result;
  } catch {
    return {};
  }
}

function persistQuickOverrides(
  overrides: Record<string, ViewerQuickControlsOverride>,
): void {
  try {
    localStorage.setItem(LOCAL_QUICK_OVERRIDES_KEY, JSON.stringify(overrides));
  } catch {
    // ignore storage errors
  }
}

function getLocalFormatOverride(): ModelFormat | null {
  try {
    const v = localStorage.getItem(LOCAL_FORMAT_KEY);
    if (v === 'ply' || v === 'spz') return v;
  } catch { /* ignore */ }
  return null;
}

function getLocalLodSetting(): boolean {
  try {
    return localStorage.getItem(LOCAL_LOD_KEY) === 'true';
  } catch { /* ignore */ }
  return false;
}

function getLocalHfSetting(): boolean {
  try {
    return localStorage.getItem(LOCAL_HF_KEY) === 'true';
  } catch { /* ignore */ }
  return false;
}

function getLocalLodPreset(): LodPresetKey {
  try {
    const v = localStorage.getItem(LOCAL_LOD_PRESET_KEY);
    if (v === 'performance' || v === 'balanced' || v === 'detail') {
      return v;
    }
  } catch { /* ignore */ }
  return 'balanced';
}

function getLocalQuickPresetMode(): QuickPresetMode {
  try {
    const v = localStorage.getItem(LOCAL_QUICK_PRESET_KEY);
    if (v === 'performance' || v === 'balanced' || v === 'detail' || v === 'manual') {
      return v;
    }
  } catch { /* ignore */ }
  return 'balanced';
}

function getLocalLodCompareMode(): LodCompareMode {
  try {
    const v = localStorage.getItem(LOCAL_LOD_COMPARE_KEY);
    if (v === 'lod' || v === 'non-lod') return v;
  } catch { /* ignore */ }
  return 'lod';
}

function getLocalRadModeEnabled(): boolean {
  try {
    return localStorage.getItem(LOCAL_RAD_MODE_KEY) === 'true';
  } catch { /* ignore */ }
  return false;
}

function getLocalRadPagedEnabled(): boolean {
  try {
    const v = localStorage.getItem(LOCAL_RAD_PAGED_KEY);
    if (v === null) return true;
    return v === 'true';
  } catch { /* ignore */ }
  return true;
}

function getLocalXrUpdateMode(): XrUpdateMode {
  try {
    const v = localStorage.getItem(LOCAL_XR_UPDATE_MODE_KEY);
    if (v === 'auto' || v === 'manual') return v;
  } catch { /* ignore */ }
  return 'auto';
}

function persistDefaultRevealEffect(effectId: RevealEffectPreferenceId): void {
  try {
    localStorage.setItem(LOCAL_DEFAULT_REVEAL_EFFECT_KEY, effectId);
  } catch {
    // ignore storage errors
  }
}

function getLocalDefaultRevealEffect(): RevealEffectPreferenceId {
  try {
    const value = localStorage.getItem(LOCAL_DEFAULT_REVEAL_EFFECT_KEY);
    if (isRevealEffectPreferenceId(value)) return value;
    if (value === REVEAL_EFFECT_NONE_ID) {
      persistDefaultRevealEffect(DEFAULT_REVEAL_EFFECT_PREFERENCE_ID);
    }
  } catch { /* ignore */ }

  return DEFAULT_REVEAL_EFFECT_PREFERENCE_ID;
}

interface QuickPresetState {
  isLodEnabled: boolean;
  lodPreset: LodPresetKey;
  lodCompareMode: LodCompareMode;
  radModeEnabled: boolean;
  radPagedEnabled: boolean;
  xrUpdateMode: XrUpdateMode;
  isHighFidelity: boolean;
}

function getQuickPresetState(mode: LodPresetKey): QuickPresetState {
  if (mode === 'performance') {
    return {
      isLodEnabled: false,
      lodPreset: 'performance',
      lodCompareMode: 'lod',
      radModeEnabled: false,
      radPagedEnabled: false,
      xrUpdateMode: 'auto',
      isHighFidelity: false,
    };
  }

  if (mode === 'balanced') {
    return {
      isLodEnabled: false,
      lodPreset: 'balanced',
      lodCompareMode: 'lod',
      radModeEnabled: false,
      radPagedEnabled: true,
      xrUpdateMode: 'auto',
      isHighFidelity: false,
    };
  }

  return {
    isLodEnabled: false,
    lodPreset: 'detail',
    lodCompareMode: 'lod',
    radModeEnabled: false,
    radPagedEnabled: false,
    xrUpdateMode: 'auto',
    isHighFidelity: true,
  };
}

function getInitialViewerPresetState(): { quickPresetMode: QuickPresetMode } & QuickPresetState {
  const quickPresetMode = getLocalQuickPresetMode();
  if (quickPresetMode !== 'manual') {
    return {
      quickPresetMode,
      ...getQuickPresetState(quickPresetMode),
    };
  }

  return {
    quickPresetMode,
    isLodEnabled: getLocalLodSetting(),
    lodPreset: getLocalLodPreset(),
    lodCompareMode: getLocalLodCompareMode(),
    radModeEnabled: getLocalRadModeEnabled(),
    radPagedEnabled: getLocalRadPagedEnabled(),
    xrUpdateMode: getLocalXrUpdateMode(),
    isHighFidelity: getLocalHfSetting(),
  };
}

const initialViewerPresetState = getInitialViewerPresetState();
const initialViewerQualityState = getViewerQualityFromPreset(
  initialViewerPresetState.lodPreset,
  initialViewerPresetState.isLodEnabled,
);
const initialModelViewerOverrides = getLocalQuickOverrides(initialViewerQualityState);

interface AppState {
  // UI State
  sidebarOpen: boolean;
  sidebarCollapsed: boolean;
  controlsCollapsed: boolean;
  helpPanelVisible: boolean;
  settingsModalOpen: boolean;
  videoReconstructionGuideOpen: boolean;

  // Loading State
  isLoading: boolean;
  loadingText: string;
  loadingProgress: number;

  // Boot State
  isBooting: boolean;
  bootError: string | null;

  // Gallery
  galleryItems: GalleryItem[];
  currentModelId: string | null;
  currentModelUrl: string | null;
  currentModelFormat: ViewerModelFormat; // Format hint for blob URLs
  currentModelSize: number | null;
  previewImage: GalleryItem | null; // For image lightbox

  // Photo Gallery
  activeView: AppView;
  photoAlbums: PhotoAlbum[];
  photoAlbumsLoaded: boolean;
  photoAlbumsLoading: boolean;
  currentPhotoAlbumId: string | null;
  photoItems: PhotoItem[];
  photoNextCursor: string | null;
  photoSnapshot: string | null;
  photoTotal: number;
  photoMediaType: PhotoMediaType;
  photoMediaCounts: PhotoMediaCounts;
  photoSelectionMode: boolean;
  selectedPhotoIds: string[];
  previewPhoto: PhotoItem | null;
  videoReconstructionDialogOpen: boolean;
  videoReconstructionTarget: PhotoItem | null;
  videoReconstructionFileTarget: File | null;
  videoReconstructionDependencies: VideoReconstructionDependencies | null;
  videoReconstructionConfig: VideoReconstructionConfig;
  videoReconstructionSubmitting: boolean;

  // Model Format Preference
  serverModelFormat: ModelFormat;        // Host default from config.json
  localModelFormat: ModelFormat | null;  // Client override via localStorage

  // Task Queue
  tasks: Task[];
  hasActiveTasks: boolean;

  // Viewer
  isLimitsOn: boolean;
  isGyroEnabled: boolean;
  isJoystickEnabled: boolean;
  viewerDefaultRevealEffect: RevealEffectPreferenceId;
  quickPresetMode: QuickPresetMode;
  isLodEnabled: boolean;
  lodPreset: LodPresetKey;
  lodCompareMode: LodCompareMode;
  canCompareLod: boolean;
  radModeEnabled: boolean;
  radPagedEnabled: boolean;
  usedRadLastLoad: boolean;
  xrUpdateMode: XrUpdateMode;
  isHighFidelity: boolean;
  quickControlsOpen: boolean;
  viewerTransformDraft: ViewerTransformState;
  viewerTransformApplied: ViewerTransformState;
  viewerInteractionDraft: ViewerInteractionState;
  viewerInteractionApplied: ViewerInteractionState;
  viewerQualityDraft: ViewerQualityState;
  viewerQualityApplied: ViewerQualityState;
  modelViewerOverrides: Record<string, ViewerQuickControlsOverride>;

  // Settings
  isLocalAccess: boolean;
  authStatus: AuthStatusResponse | null;
  isAuthenticated: boolean;
  isOwnerAccess: boolean;
  authSetupRequired: boolean;
  authPermissionError: string | null;

  // Computed
  /** Effective format: client override > server default */
  effectiveModelFormat: () => ModelFormat;

  // Actions
  setSidebarOpen: (open: boolean) => void;
  toggleSidebar: () => void;
  toggleSidebarCollapsed: () => void;
  toggleControlsCollapsed: () => void;
  toggleHelpPanel: () => void;
  setSettingsModalOpen: (open: boolean) => void;
  openVideoReconstructionGuide: () => void;
  closeVideoReconstructionGuide: () => void;

  setLoading: (loading: boolean, text?: string) => void;
  resetLoadingProgress: () => void;
  setLoadingProgress: (progress: number) => void;

  setBootComplete: () => void;
  setBootError: (error: string) => void;

  setGalleryItems: (items: GalleryItem[]) => void;
  removeGalleryItem: (id: string) => void;
  setCurrentModel: (
    id: string | null,
    url: string | null,
    format?: ViewerModelFormat,
    size?: number | null,
  ) => void;
  setPreviewImage: (item: GalleryItem | null) => void;

  setActiveView: (view: AppView) => void;
  setPhotoAlbums: (albums: PhotoAlbum[]) => void;
  setPhotoAlbumsLoading: (loading: boolean) => void;
  resetPhotoAlbumsLoaded: () => void;
  setCurrentPhotoAlbum: (albumId: string | null) => void;
  setPhotoMediaType: (mediaType: PhotoMediaType) => void;
  setPhotoItems: (
    items: PhotoItem[],
    nextCursor: string | null,
    total: number,
    append?: boolean,
    mediaCounts?: PhotoMediaCounts,
    snapshot?: string | null,
  ) => void;
  clearPhotoItems: () => void;
  setPhotoSelectionMode: (enabled: boolean) => void;
  toggleSelectedPhoto: (photoId: string) => void;
  clearSelectedPhotos: () => void;
  setPreviewPhoto: (item: PhotoItem | null) => void;
  openVideoReconstructionDialog: (item: PhotoItem) => void;
  openVideoReconstructionFileDialog: (file: File) => void;
  closeVideoReconstructionDialog: () => void;
  setVideoReconstructionStatus: (
    dependencies: VideoReconstructionDependencies | null,
    config?: VideoReconstructionConfig,
  ) => void;
  setVideoReconstructionSubmitting: (submitting: boolean) => void;

  setServerModelFormat: (format: ModelFormat) => void;
  setLocalModelFormat: (format: ModelFormat | null) => void;
  toggleLocalModelFormat: () => void;

  setTasks: (tasks: Task[], hasActive: boolean) => void;

  toggleLimits: () => void;
  toggleGyro: () => void;
  toggleJoystick: () => void;
  setViewerDefaultRevealEffect: (effectId: RevealEffectPreferenceId) => void;
  setQuickPresetMode: (mode: QuickPresetMode) => void;
  applyQuickPreset: (mode: LodPresetKey) => void;
  toggleLod: () => void;
  setLodEnabled: (enabled: boolean) => void;
  setLodPreset: (preset: LodPresetKey) => void;
  setLodCompareMode: (mode: LodCompareMode) => void;
  setCanCompareLod: (canCompare: boolean) => void;
  setRadModeEnabled: (enabled: boolean) => void;
  setRadPagedEnabled: (enabled: boolean) => void;
  setUsedRadLastLoad: (used: boolean) => void;
  setXrUpdateMode: (mode: XrUpdateMode) => void;
  toggleHighFidelity: () => void;

  setQuickControlsOpen: (open: boolean) => void;
  toggleQuickControls: () => void;
  setViewerTransformDraft: (patch: Partial<ViewerTransformState>) => void;
  applyViewerTransformDraft: () => void;
  setViewerInteractionDraft: (patch: Partial<ViewerInteractionState>) => void;
  applyViewerInteractionDraft: () => void;
  setViewerQualityDraft: (patch: Partial<ViewerQualityState>) => void;
  applyViewerQualityDraft: () => void;
  applyOrientationPreset: (preset: ViewerOrientationPreset) => void;
  restoreViewerQuickControlsForModel: (modelId: string | null) => void;
  saveViewerQuickControlsForCurrentModel: () => void;
  resetViewerQuickControlsForCurrentModel: () => void;

  setLocalAccess: (isLocal: boolean) => void;
  setAuthStatus: (status: AuthStatusResponse) => void;
  setAuthPermissionError: (message: string | null) => void;
}

export const useAppStore = create<AppState>((set, get) => ({
  // Initial State
  sidebarOpen: false,
  sidebarCollapsed: false,
  controlsCollapsed: false,
  helpPanelVisible: false,
  settingsModalOpen: false,
  videoReconstructionGuideOpen: false,

  isLoading: false,
  loadingText: '',
  loadingProgress: 0,

  isBooting: true,
  bootError: null,

  galleryItems: [],
  currentModelId: null,
  currentModelUrl: null,
  currentModelFormat: null,
  currentModelSize: null,
  previewImage: null,

  activeView: 'models',
  photoAlbums: [],
  photoAlbumsLoaded: false,
  photoAlbumsLoading: false,
  currentPhotoAlbumId: null,
  photoItems: [],
  photoNextCursor: null,
  photoSnapshot: null,
  photoTotal: 0,
  photoMediaType: 'all',
  photoMediaCounts: { ...DEFAULT_PHOTO_MEDIA_COUNTS },
  photoSelectionMode: false,
  selectedPhotoIds: [],
  previewPhoto: null,
  videoReconstructionDialogOpen: false,
  videoReconstructionTarget: null,
  videoReconstructionFileTarget: null,
  videoReconstructionDependencies: null,
  videoReconstructionConfig: { ...DEFAULT_VIDEO_RECONSTRUCTION_CONFIG },
  videoReconstructionSubmitting: false,

  // Model Format Preference
  serverModelFormat: 'spz',
  localModelFormat: getLocalFormatOverride(),

  tasks: [],
  hasActiveTasks: false,

  isLimitsOn: true,
  isGyroEnabled: false,
  isJoystickEnabled: false,
  viewerDefaultRevealEffect: getLocalDefaultRevealEffect(),
  quickPresetMode: initialViewerPresetState.quickPresetMode,
  isLodEnabled: initialViewerPresetState.isLodEnabled,
  lodPreset: initialViewerPresetState.lodPreset,
  lodCompareMode: initialViewerPresetState.lodCompareMode,
  canCompareLod: false,
  radModeEnabled: initialViewerPresetState.radModeEnabled,
  radPagedEnabled: initialViewerPresetState.radPagedEnabled,
  usedRadLastLoad: false,
  xrUpdateMode: initialViewerPresetState.xrUpdateMode,
  isHighFidelity: initialViewerPresetState.isHighFidelity,
  quickControlsOpen: false,
  viewerTransformDraft: { ...DEFAULT_VIEWER_TRANSFORM },
  viewerTransformApplied: { ...DEFAULT_VIEWER_TRANSFORM },
  viewerInteractionDraft: { ...DEFAULT_VIEWER_INTERACTION },
  viewerInteractionApplied: { ...DEFAULT_VIEWER_INTERACTION },
  viewerQualityDraft: { ...initialViewerQualityState },
  viewerQualityApplied: { ...initialViewerQualityState },
  modelViewerOverrides: initialModelViewerOverrides,

  isLocalAccess: false,
  authStatus: null,
  isAuthenticated: false,
  isOwnerAccess: false,
  authSetupRequired: false,
  authPermissionError: null,

  // Computed: client override > server default
  effectiveModelFormat: () => {
    const state = get();
    return state.localModelFormat ?? state.serverModelFormat;
  },

  // Actions
  setSidebarOpen: (open) => set({ sidebarOpen: open }),
  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
  toggleSidebarCollapsed: () => set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
  toggleControlsCollapsed: () => set((state) => ({ controlsCollapsed: !state.controlsCollapsed })),
  toggleHelpPanel: () => set((state) => ({ helpPanelVisible: !state.helpPanelVisible })),
  setSettingsModalOpen: (open) => set({ settingsModalOpen: open }),
  openVideoReconstructionGuide: () => set({ videoReconstructionGuideOpen: true }),
  closeVideoReconstructionGuide: () => set({ videoReconstructionGuideOpen: false }),

  setLoading: (loading, text = '') => set((state) => ({
    isLoading: loading,
    loadingText: text,
    loadingProgress: loading
      ? (state.isLoading ? state.loadingProgress : 0)
      : 0,
  })),
  resetLoadingProgress: () => set({ loadingProgress: 0 }),
  setLoadingProgress: (progress) => set((state) => ({
    loadingProgress: Math.max(state.loadingProgress, progress),
  })),

  setBootComplete: () => set({ isBooting: false }),
  setBootError: (error) => set({ bootError: error }),

  setGalleryItems: (items) => set((state) => {
    const nextGalleryItems = reconcileGalleryItems(state.galleryItems, items);
    const selectedItem = state.currentModelId
      ? nextGalleryItems.find((item) => item.id === state.currentModelId) ?? null
      : null;
    const previewImage = state.previewImage
      ? nextGalleryItems.find((item) => item.id === state.previewImage?.id) ?? null
      : null;

    let currentModelId = state.currentModelId;
    let currentModelUrl = state.currentModelUrl;
    let currentModelFormat = state.currentModelFormat;
    let currentModelSize = state.currentModelSize;

    if (state.currentModelId && !selectedItem) {
      currentModelId = null;
      currentModelUrl = null;
      currentModelFormat = null;
      currentModelSize = null;
    } else if (
      selectedItem &&
      state.currentModelFormat !== 'splat' &&
      state.currentModelFormat !== 'rad' &&
      !state.currentModelUrl?.startsWith('blob:')
    ) {
      const preferredFormat =
        state.currentModelFormat === 'spz' || state.currentModelFormat === 'ply'
          ? state.currentModelFormat
          : state.localModelFormat ?? state.serverModelFormat;
      const nextModel = getGalleryModelSource(selectedItem, preferredFormat);
      currentModelId = selectedItem.id;
      currentModelUrl = nextModel.url;
      currentModelFormat = nextModel.format;
      currentModelSize = nextModel.size;
    }

    const galleryUnchanged = nextGalleryItems === state.galleryItems;
    const selectionUnchanged =
      currentModelId === state.currentModelId &&
      currentModelUrl === state.currentModelUrl &&
      currentModelFormat === state.currentModelFormat &&
      currentModelSize === state.currentModelSize;
    const previewUnchanged = previewImage === state.previewImage;

    if (galleryUnchanged && selectionUnchanged && previewUnchanged) {
      return state;
    }

    return {
      galleryItems: nextGalleryItems,
      currentModelId,
      currentModelUrl,
      currentModelFormat,
      currentModelSize,
      previewImage,
    };
  }),
  removeGalleryItem: (id) => set((state) => {
    if (!state.galleryItems.some((item) => item.id === id)) {
      return state;
    }

    const nextGalleryItems = state.galleryItems.filter((item) => item.id !== id);
    const previewImage = state.previewImage?.id === id ? null : state.previewImage;

    if (state.currentModelId === id) {
      return {
        galleryItems: nextGalleryItems,
        currentModelId: null,
        currentModelUrl: null,
        currentModelFormat: null,
        currentModelSize: null,
        previewImage,
      };
    }

    return {
      galleryItems: nextGalleryItems,
      previewImage,
    };
  }),
  setCurrentModel: (id, url, format = null, size = null) => set((state) => {
    const fallbackQuality = getViewerQualityFromPreset(state.lodPreset, state.isLodEnabled);
    const fallbackOverride = getDefaultViewerOverride(fallbackQuality);
    const override = id ? state.modelViewerOverrides[id] : undefined;
    const resolved = override
      ? sanitizeViewerOverride(override, fallbackQuality)
      : fallbackOverride;

    return {
      currentModelId: id,
      currentModelUrl: url,
      currentModelFormat: format,
      currentModelSize: typeof size === 'number' && Number.isFinite(size) && size > 0
        ? size
        : null,
      viewerTransformDraft: resolved.transform,
      viewerTransformApplied: resolved.transform,
      viewerInteractionDraft: resolved.interaction,
      viewerInteractionApplied: resolved.interaction,
      viewerQualityDraft: resolved.quality,
      viewerQualityApplied: resolved.quality,
      isLodEnabled: resolved.quality.lodEnabled,
    };
  }),
  setPreviewImage: (item) => set({ previewImage: item }),

  setActiveView: (view) => set({ activeView: view }),
  setPhotoAlbums: (albums) => set((state) => {
    const currentExists = state.currentPhotoAlbumId
      ? albums.some((album) => album.id === state.currentPhotoAlbumId)
      : false;
    const currentPhotoAlbumId = currentExists
      ? state.currentPhotoAlbumId
      : albums[0]?.id ?? null;

    return {
      photoAlbums: albums,
      photoAlbumsLoaded: true,
      photoAlbumsLoading: false,
      currentPhotoAlbumId,
      photoItems: currentPhotoAlbumId === state.currentPhotoAlbumId ? state.photoItems : [],
      photoNextCursor: currentPhotoAlbumId === state.currentPhotoAlbumId ? state.photoNextCursor : null,
      photoSnapshot: currentPhotoAlbumId === state.currentPhotoAlbumId ? state.photoSnapshot : null,
      photoTotal: currentPhotoAlbumId === state.currentPhotoAlbumId ? state.photoTotal : 0,
      photoMediaCounts: currentPhotoAlbumId === state.currentPhotoAlbumId
        ? state.photoMediaCounts
        : { ...DEFAULT_PHOTO_MEDIA_COUNTS },
      selectedPhotoIds: currentPhotoAlbumId === state.currentPhotoAlbumId ? state.selectedPhotoIds : [],
      previewPhoto: currentPhotoAlbumId === state.previewPhoto?.album_id ? state.previewPhoto : null,
    };
  }),
  setPhotoAlbumsLoading: (loading) => set({ photoAlbumsLoading: loading }),
  resetPhotoAlbumsLoaded: () => set({ photoAlbumsLoaded: false }),
  setCurrentPhotoAlbum: (albumId) => set((state) => {
    if (state.currentPhotoAlbumId === albumId) {
      return state;
    }

    return {
      currentPhotoAlbumId: albumId,
      photoItems: [],
      photoNextCursor: null,
      photoSnapshot: null,
      photoTotal: 0,
      photoMediaCounts: { ...DEFAULT_PHOTO_MEDIA_COUNTS },
      selectedPhotoIds: [],
      photoSelectionMode: false,
      previewPhoto: null,
    };
  }),
  setPhotoMediaType: (mediaType) => set((state) => {
    if (state.photoMediaType === mediaType) {
      return state;
    }

    return {
      photoMediaType: mediaType,
      photoItems: [],
      photoNextCursor: null,
      photoSnapshot: null,
      photoTotal: 0,
      selectedPhotoIds: [],
      photoSelectionMode: false,
      previewPhoto: null,
    };
  }),
  setPhotoItems: (items, nextCursor, total, append = false, mediaCounts, snapshot) => set((state) => {
    const nextItems = append
      ? [
          ...state.photoItems,
          ...items.filter((item) => !state.photoItems.some((existing) => existing.id === item.id)),
        ]
      : items;

    return {
      photoItems: nextItems,
      photoNextCursor: nextCursor,
      photoSnapshot: snapshot ?? (append ? state.photoSnapshot : null),
      photoTotal: total,
      photoMediaCounts: mediaCounts ?? state.photoMediaCounts,
      selectedPhotoIds: state.selectedPhotoIds.filter((photoId) =>
        nextItems.some((item) => item.id === photoId),
      ),
    };
  }),
  clearPhotoItems: () => set({
    photoItems: [],
    photoNextCursor: null,
    photoSnapshot: null,
    photoTotal: 0,
    photoMediaCounts: { ...DEFAULT_PHOTO_MEDIA_COUNTS },
    selectedPhotoIds: [],
    photoSelectionMode: false,
    previewPhoto: null,
  }),
  setPhotoSelectionMode: (enabled) => set({
    photoSelectionMode: enabled,
    selectedPhotoIds: enabled ? get().selectedPhotoIds : [],
  }),
  toggleSelectedPhoto: (photoId) => set((state) => {
    const exists = state.selectedPhotoIds.includes(photoId);
    return {
      selectedPhotoIds: exists
        ? state.selectedPhotoIds.filter((id) => id !== photoId)
        : [...state.selectedPhotoIds, photoId],
    };
  }),
  clearSelectedPhotos: () => set({
    selectedPhotoIds: [],
    photoSelectionMode: false,
  }),
  setPreviewPhoto: (item) => set({ previewPhoto: item }),
  openVideoReconstructionDialog: (item) => set({
    videoReconstructionDialogOpen: true,
    videoReconstructionTarget: item,
    videoReconstructionFileTarget: null,
  }),
  openVideoReconstructionFileDialog: (file) => set({
    videoReconstructionDialogOpen: true,
    videoReconstructionTarget: null,
    videoReconstructionFileTarget: file,
  }),
  closeVideoReconstructionDialog: () => set({
    videoReconstructionDialogOpen: false,
    videoReconstructionTarget: null,
    videoReconstructionFileTarget: null,
    videoReconstructionSubmitting: false,
  }),
  setVideoReconstructionStatus: (dependencies, config) => set((state) => ({
    videoReconstructionDependencies: dependencies,
    videoReconstructionConfig: config ?? state.videoReconstructionConfig,
  })),
  setVideoReconstructionSubmitting: (submitting) => set({ videoReconstructionSubmitting: submitting }),

  setServerModelFormat: (format) => set({ serverModelFormat: format }),
  setLocalModelFormat: (format) => {
    if (format) {
      try { localStorage.setItem(LOCAL_FORMAT_KEY, format); } catch { /* ignore */ }
    } else {
      try { localStorage.removeItem(LOCAL_FORMAT_KEY); } catch { /* ignore */ }
    }
    set({ localModelFormat: format });
  },
  toggleLocalModelFormat: () => {
    const state = get();
    const current = state.localModelFormat ?? state.serverModelFormat;
    const next: ModelFormat = current === 'spz' ? 'ply' : 'spz';
    // Set as local override
    try { localStorage.setItem(LOCAL_FORMAT_KEY, next); } catch { /* ignore */ }
    set({ localModelFormat: next });
  },

  setTasks: (tasks, hasActive) => set({ tasks, hasActiveTasks: hasActive }),

  toggleLimits: () => set((state) => ({ isLimitsOn: !state.isLimitsOn })),
  toggleGyro: () => set((state) => ({ isGyroEnabled: !state.isGyroEnabled })),
  toggleJoystick: () => set((state) => ({ isJoystickEnabled: !state.isJoystickEnabled })),
  setViewerDefaultRevealEffect: (effectId) => {
    persistDefaultRevealEffect(effectId);
    set({ viewerDefaultRevealEffect: effectId });
  },
  setQuickPresetMode: (mode) => {
    try { localStorage.setItem(LOCAL_QUICK_PRESET_KEY, mode); } catch { /* ignore */ }
    set({ quickPresetMode: mode });
  },
  applyQuickPreset: (mode) => {
    const next = getQuickPresetState(mode);
    const nextQuality = getViewerQualityFromPreset(mode, next.isLodEnabled);

    try { localStorage.setItem(LOCAL_QUICK_PRESET_KEY, mode); } catch { /* ignore */ }
    try { localStorage.setItem(LOCAL_LOD_KEY, String(next.isLodEnabled)); } catch { /* ignore */ }
    try { localStorage.setItem(LOCAL_LOD_PRESET_KEY, next.lodPreset); } catch { /* ignore */ }
    try { localStorage.setItem(LOCAL_LOD_COMPARE_KEY, next.lodCompareMode); } catch { /* ignore */ }
    try { localStorage.setItem(LOCAL_RAD_MODE_KEY, String(next.radModeEnabled)); } catch { /* ignore */ }
    try { localStorage.setItem(LOCAL_RAD_PAGED_KEY, String(next.radPagedEnabled)); } catch { /* ignore */ }
    try { localStorage.setItem(LOCAL_XR_UPDATE_MODE_KEY, next.xrUpdateMode); } catch { /* ignore */ }
    try { localStorage.setItem(LOCAL_HF_KEY, String(next.isHighFidelity)); } catch { /* ignore */ }

    set({
      quickPresetMode: mode,
      isLodEnabled: next.isLodEnabled,
      lodPreset: next.lodPreset,
      lodCompareMode: next.lodCompareMode,
      radModeEnabled: next.radModeEnabled,
      radPagedEnabled: next.radPagedEnabled,
      xrUpdateMode: next.xrUpdateMode,
      isHighFidelity: next.isHighFidelity,
      viewerQualityDraft: nextQuality,
      viewerQualityApplied: nextQuality,
    });
  },
  toggleLod: () => {
    const next = !get().isLodEnabled;
    try { localStorage.setItem(LOCAL_LOD_KEY, String(next)); } catch { /* ignore */ }
    set((state) => ({
      isLodEnabled: next,
      viewerQualityDraft: {
        ...state.viewerQualityDraft,
        lodEnabled: next,
      },
      viewerQualityApplied: {
        ...state.viewerQualityApplied,
        lodEnabled: next,
      },
    }));
  },
  setLodEnabled: (enabled) => {
    try { localStorage.setItem(LOCAL_LOD_KEY, String(enabled)); } catch { /* ignore */ }
    set((state) => ({
      isLodEnabled: enabled,
      viewerQualityDraft: {
        ...state.viewerQualityDraft,
        lodEnabled: enabled,
      },
      viewerQualityApplied: {
        ...state.viewerQualityApplied,
        lodEnabled: enabled,
      },
    }));
  },
  setLodPreset: (preset) => {
    try { localStorage.setItem(LOCAL_LOD_PRESET_KEY, preset); } catch { /* ignore */ }
    set((state) => {
      const nextQuality = getViewerQualityFromPreset(
        preset,
        state.viewerQualityApplied.lodEnabled,
      );
      return {
        lodPreset: preset,
        viewerQualityDraft: nextQuality,
        viewerQualityApplied: nextQuality,
      };
    });
  },
  setLodCompareMode: (mode) => {
    const canCompareLod = get().canCompareLod;
    const nextMode: LodCompareMode = canCompareLod ? mode : 'lod';
    try { localStorage.setItem(LOCAL_LOD_COMPARE_KEY, nextMode); } catch { /* ignore */ }
    set({ lodCompareMode: nextMode });
  },
  setCanCompareLod: (canCompare) => {
    set((state) => ({
      canCompareLod: canCompare,
      lodCompareMode: canCompare ? state.lodCompareMode : 'lod',
    }));
    if (!canCompare) {
      try { localStorage.setItem(LOCAL_LOD_COMPARE_KEY, 'lod'); } catch { /* ignore */ }
    }
  },
  setRadModeEnabled: (enabled) => {
    try { localStorage.setItem(LOCAL_RAD_MODE_KEY, String(enabled)); } catch { /* ignore */ }
    set({ radModeEnabled: enabled });
  },
  setRadPagedEnabled: (enabled) => {
    try { localStorage.setItem(LOCAL_RAD_PAGED_KEY, String(enabled)); } catch { /* ignore */ }
    set({ radPagedEnabled: enabled });
  },
  setUsedRadLastLoad: (used) => set({ usedRadLastLoad: used }),
  setXrUpdateMode: (mode) => {
    try { localStorage.setItem(LOCAL_XR_UPDATE_MODE_KEY, mode); } catch { /* ignore */ }
    set({ xrUpdateMode: mode });
  },
  toggleHighFidelity: () => {
    const next = !get().isHighFidelity;
    try { localStorage.setItem(LOCAL_HF_KEY, String(next)); } catch { /* ignore */ }
    set({ isHighFidelity: next });
  },

  setQuickControlsOpen: (open) => set({ quickControlsOpen: open }),
  toggleQuickControls: () => set((state) => ({ quickControlsOpen: !state.quickControlsOpen })),
  setViewerTransformDraft: (patch) => set((state) => ({
    viewerTransformDraft: sanitizeViewerTransform({
      ...state.viewerTransformDraft,
      ...patch,
    }),
  })),
  applyViewerTransformDraft: () => set((state) => {
    const transform = sanitizeViewerTransform(state.viewerTransformDraft);
    const nextState = {
      viewerTransformDraft: transform,
      viewerTransformApplied: transform,
    };

    if (!state.currentModelId) {
      return nextState;
    }

    const nextOverrides = {
      ...state.modelViewerOverrides,
      [state.currentModelId]: {
        transform,
        interaction: state.viewerInteractionApplied,
        quality: state.viewerQualityApplied,
      },
    };
    persistQuickOverrides(nextOverrides);

    return {
      ...nextState,
      modelViewerOverrides: nextOverrides,
    };
  }),
  setViewerInteractionDraft: (patch) => set((state) => ({
    viewerInteractionDraft: sanitizeViewerInteraction({
      ...state.viewerInteractionDraft,
      ...patch,
    }),
  })),
  applyViewerInteractionDraft: () => set((state) => {
    const interaction = sanitizeViewerInteraction(state.viewerInteractionDraft);
    const nextState = {
      viewerInteractionDraft: interaction,
      viewerInteractionApplied: interaction,
    };

    if (!state.currentModelId) {
      return nextState;
    }

    const nextOverrides = {
      ...state.modelViewerOverrides,
      [state.currentModelId]: {
        transform: state.viewerTransformApplied,
        interaction,
        quality: state.viewerQualityApplied,
      },
    };
    persistQuickOverrides(nextOverrides);

    return {
      ...nextState,
      modelViewerOverrides: nextOverrides,
    };
  }),
  setViewerQualityDraft: (patch) => set((state) => ({
    viewerQualityDraft: sanitizeViewerQuality(
      {
        ...state.viewerQualityDraft,
        ...patch,
      },
      state.viewerQualityDraft,
    ),
  })),
  applyViewerQualityDraft: () => set((state) => {
    const quality = sanitizeViewerQuality(
      state.viewerQualityDraft,
      state.viewerQualityApplied,
    );
    try { localStorage.setItem(LOCAL_LOD_KEY, String(quality.lodEnabled)); } catch { /* ignore */ }

    const nextState = {
      isLodEnabled: quality.lodEnabled,
      viewerQualityDraft: quality,
      viewerQualityApplied: quality,
    };

    if (!state.currentModelId) {
      return nextState;
    }

    const nextOverrides = {
      ...state.modelViewerOverrides,
      [state.currentModelId]: {
        transform: state.viewerTransformApplied,
        interaction: state.viewerInteractionApplied,
        quality,
      },
    };
    persistQuickOverrides(nextOverrides);

    return {
      ...nextState,
      modelViewerOverrides: nextOverrides,
    };
  }),
  applyOrientationPreset: (preset) => set((state) => {
    const nextTransform = { ...state.viewerTransformDraft };

    if (preset === 'default' || preset === 'openCv') {
      nextTransform.rotationX = Math.PI;
      nextTransform.rotationY = 0;
      nextTransform.rotationZ = 0;
    } else if (preset === 'openGl') {
      nextTransform.rotationX = 0;
      nextTransform.rotationY = 0;
      nextTransform.rotationZ = 0;
    } else if (preset === 'zUp') {
      nextTransform.rotationX = -Math.PI / 2;
      nextTransform.rotationY = 0;
      nextTransform.rotationZ = 0;
    } else if (preset === 'flipUpsideDown') {
      nextTransform.rotationZ = normalizeRadians(nextTransform.rotationZ + Math.PI);
    }

    const transform = sanitizeViewerTransform(nextTransform);
    const nextState = {
      viewerTransformDraft: transform,
      viewerTransformApplied: transform,
    };

    if (!state.currentModelId) {
      return nextState;
    }

    const nextOverrides = {
      ...state.modelViewerOverrides,
      [state.currentModelId]: {
        transform,
        interaction: state.viewerInteractionApplied,
        quality: state.viewerQualityApplied,
      },
    };
    persistQuickOverrides(nextOverrides);

    return {
      ...nextState,
      modelViewerOverrides: nextOverrides,
    };
  }),
  restoreViewerQuickControlsForModel: (modelId) => set((state) => {
    const fallbackQuality = getViewerQualityFromPreset(state.lodPreset, state.isLodEnabled);
    const fallbackOverride = getDefaultViewerOverride(fallbackQuality);
    const override = modelId ? state.modelViewerOverrides[modelId] : undefined;
    const resolved = override
      ? sanitizeViewerOverride(override, fallbackQuality)
      : fallbackOverride;

    return {
      viewerTransformDraft: resolved.transform,
      viewerTransformApplied: resolved.transform,
      viewerInteractionDraft: resolved.interaction,
      viewerInteractionApplied: resolved.interaction,
      viewerQualityDraft: resolved.quality,
      viewerQualityApplied: resolved.quality,
      isLodEnabled: resolved.quality.lodEnabled,
    };
  }),
  saveViewerQuickControlsForCurrentModel: () => set((state) => {
    if (!state.currentModelId) {
      return {};
    }

    const nextOverrides = {
      ...state.modelViewerOverrides,
      [state.currentModelId]: {
        transform: sanitizeViewerTransform(state.viewerTransformApplied),
        interaction: sanitizeViewerInteraction(state.viewerInteractionApplied),
        quality: sanitizeViewerQuality(
          state.viewerQualityApplied,
          state.viewerQualityApplied,
        ),
      },
    };
    persistQuickOverrides(nextOverrides);

    return {
      modelViewerOverrides: nextOverrides,
    };
  }),
  resetViewerQuickControlsForCurrentModel: () => set((state) => {
    const fallbackQuality = getViewerQualityFromPreset(state.lodPreset, state.isLodEnabled);
    const fallbackOverride = getDefaultViewerOverride(fallbackQuality);

    const nextOverrides = { ...state.modelViewerOverrides };
    if (state.currentModelId && state.currentModelId in nextOverrides) {
      delete nextOverrides[state.currentModelId];
      persistQuickOverrides(nextOverrides);
    }

    try { localStorage.setItem(LOCAL_LOD_KEY, String(fallbackOverride.quality.lodEnabled)); } catch { /* ignore */ }

    return {
      isLodEnabled: fallbackOverride.quality.lodEnabled,
      viewerTransformDraft: fallbackOverride.transform,
      viewerTransformApplied: fallbackOverride.transform,
      viewerInteractionDraft: fallbackOverride.interaction,
      viewerInteractionApplied: fallbackOverride.interaction,
      viewerQualityDraft: fallbackOverride.quality,
      viewerQualityApplied: fallbackOverride.quality,
      modelViewerOverrides: nextOverrides,
    };
  }),

  setLocalAccess: (isLocal) => set({ isLocalAccess: isLocal, isOwnerAccess: isLocal }),
  setAuthStatus: (status) => set({
    authStatus: status,
    isAuthenticated: status.authenticated,
    isOwnerAccess: status.is_owner,
    authSetupRequired: status.setup_required,
    isLocalAccess: status.is_owner,
  }),
  setAuthPermissionError: (message) => set({ authPermissionError: message }),
}));
