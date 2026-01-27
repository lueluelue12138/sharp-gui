import { create } from 'zustand';
import type { GalleryItem, Task } from '@/types';

interface AppState {
  // UI State
  sidebarOpen: boolean;
  sidebarCollapsed: boolean;
  controlsCollapsed: boolean;
  helpPanelVisible: boolean;
  settingsModalOpen: boolean;
  
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
  currentModelFormat: 'ply' | 'splat' | null; // Format hint for blob URLs
  
  // Task Queue
  tasks: Task[];
  hasActiveTasks: boolean;
  
  // Viewer
  isLimitsOn: boolean;
  isGyroEnabled: boolean;
  isJoystickEnabled: boolean;
  
  // Settings
  isLocalAccess: boolean;
  
  // Actions
  setSidebarOpen: (open: boolean) => void;
  toggleSidebar: () => void;
  toggleSidebarCollapsed: () => void;
  toggleControlsCollapsed: () => void;
  toggleHelpPanel: () => void;
  setSettingsModalOpen: (open: boolean) => void;
  
  setLoading: (loading: boolean, text?: string) => void;
  setLoadingProgress: (progress: number) => void;
  
  setBootComplete: () => void;
  setBootError: (error: string) => void;
  
  setGalleryItems: (items: GalleryItem[]) => void;
  setCurrentModel: (id: string | null, url: string | null, format?: 'ply' | 'splat' | null) => void;
  
  setTasks: (tasks: Task[], hasActive: boolean) => void;
  
  toggleLimits: () => void;
  toggleGyro: () => void;
  toggleJoystick: () => void;
  
  setLocalAccess: (isLocal: boolean) => void;
}

export const useAppStore = create<AppState>((set) => ({
  // Initial State
  sidebarOpen: false,
  sidebarCollapsed: false,
  controlsCollapsed: false,
  helpPanelVisible: false,
  settingsModalOpen: false,
  
  isLoading: false,
  loadingText: '',
  loadingProgress: 0,
  
  isBooting: true,
  bootError: null,
  
  galleryItems: [],
  currentModelId: null,
  currentModelUrl: null,
  currentModelFormat: null,
  
  tasks: [],
  hasActiveTasks: false,
  
  isLimitsOn: true,
  isGyroEnabled: false,
  isJoystickEnabled: false,
  
  isLocalAccess: false,
  
  // Actions
  setSidebarOpen: (open) => set({ sidebarOpen: open }),
  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
  toggleSidebarCollapsed: () => set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
  toggleControlsCollapsed: () => set((state) => ({ controlsCollapsed: !state.controlsCollapsed })),
  toggleHelpPanel: () => set((state) => ({ helpPanelVisible: !state.helpPanelVisible })),
  setSettingsModalOpen: (open) => set({ settingsModalOpen: open }),
  
  setLoading: (loading, text = '') => set((state) => ({ 
    isLoading: loading, 
    loadingText: text,
    // Only reset progress when starting (from false to true) or completing
    loadingProgress: loading 
      ? (state.isLoading ? state.loadingProgress : 0)  // Keep progress if already loading
      : 0,
  })),
  setLoadingProgress: (progress) => set((state) => ({
    // Only allow progress to increase
    loadingProgress: Math.max(state.loadingProgress, progress),
  })),
  
  setBootComplete: () => set({ isBooting: false }),
  setBootError: (error) => set({ bootError: error }),
  
  setGalleryItems: (items) => set({ galleryItems: items }),
  setCurrentModel: (id, url, format = null) => set({ currentModelId: id, currentModelUrl: url, currentModelFormat: format }),
  
  setTasks: (tasks, hasActive) => set({ tasks, hasActiveTasks: hasActive }),
  
  toggleLimits: () => set((state) => ({ isLimitsOn: !state.isLimitsOn })),
  toggleGyro: () => set((state) => ({ isGyroEnabled: !state.isGyroEnabled })),
  toggleJoystick: () => set((state) => ({ isJoystickEnabled: !state.isJoystickEnabled })),
  
  setLocalAccess: (isLocal) => set({ isLocalAccess: isLocal }),
}));
