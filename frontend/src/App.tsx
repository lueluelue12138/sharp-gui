import { useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useAppStore } from '@/store'
import { fetchGallery, fetchSettings, fetchTasks, generateFromImages } from '@/api'
import { Sidebar, Settings } from '@/components/layout'
import { GalleryList } from '@/components/gallery'
import { Loading } from '@/components/common'
import { ParticleBackground } from '@/components/common/ParticleBackground'
import { ViewerCanvas } from '@/components/viewer/ViewerCanvas/ViewerCanvas'
import { Help } from '@/components/layout/Help/Help'
import { useTaskQueue } from '@/hooks/useTaskQueue'
import type { GalleryItem } from '@/types'
import './App.css'

function App() {
  const { t } = useTranslation()
  const { 
    isBooting, 
    bootError,
    isLoading,
    loadingText,
    loadingProgress,
    galleryItems,
    sidebarOpen,
    setBootComplete, 
    setBootError,
    setGalleryItems,
    setTasks,
    setLocalAccess,
    setCurrentModel,
    setLoading,
    currentModelUrl,
    toggleSidebar,
  } = useAppStore()

  // Initial data fetch
  useEffect(() => {
    async function init() {
      try {
        // Fetch gallery
        const gallery = await fetchGallery()
        setGalleryItems(gallery)

        // Fetch tasks
        const tasksData = await fetchTasks()
        setTasks(tasksData.tasks, tasksData.has_active)

        // Check local access
        const settings = await fetchSettings()
        setLocalAccess(settings.is_local ?? false)

        setBootComplete()
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Unknown error'
        setBootError(message)
      }
    }
    init()
  }, [setBootComplete, setBootError, setGalleryItems, setTasks, setLocalAccess])

  // Handle file upload
  const handleUpload = useCallback(async (files: FileList) => {
    try {
      setLoading(true, t('uploadingFiles', { count: files.length }))
      const result = await generateFromImages(files)
      setLoading(false)
      
      if (result.success && result.tasks) {
        setTasks(result.tasks, true)
      }
    } catch (error) {
      setLoading(false)
      const message = error instanceof Error ? error.message : 'Unknown error'
      alert(`${t('uploadFailed')}: ${message}`)
    }
  }, [t, setLoading, setTasks])

  // Handle model selection
  const handleSelectModel = useCallback((item: GalleryItem) => {
    setCurrentModel(item.id, item.model_url)
    
    // On mobile, close sidebar after selection
    if (window.innerWidth <= 768 && sidebarOpen) {
      toggleSidebar()
    }
    
    // TODO: Integrate with actual 3D viewer
    console.log('Selected model:', item.model_url)
  }, [setCurrentModel, sidebarOpen, toggleSidebar])

  // Handle model file drop (.ply / .splat) for direct preview
  const handleModelDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    
    const files = e.dataTransfer?.files
    if (!files || files.length === 0) return
    
    const file = files[0]
    const name = file.name.toLowerCase()
    
    // Check for supported model formats and extract format
    let format: 'ply' | 'splat' | null = null
    if (name.endsWith('.ply')) {
      format = 'ply'
    } else if (name.endsWith('.splat')) {
      format = 'splat'
    } else {
      alert('Unsupported format. Please drop .ply or .splat files.')
      return
    }
    
    console.log('📦 Loading dropped model:', file.name, 'format:', format)
    
    // Create Blob URL and set as current model with format hint
    const blobUrl = URL.createObjectURL(file)
    setCurrentModel(file.name, blobUrl, format)
  }, [setCurrentModel])

  const handleMainDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
  }, [])

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
    )
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
      <Sidebar onUpload={handleUpload}>
        <GalleryList 
          items={galleryItems} 
          onSelectModel={handleSelectModel}
        />
      </Sidebar>
      
      {/* Main content */}
      <main 
        className="main-content"
        onDragOver={handleMainDragOver}
        onDrop={handleModelDrop}
      >
        {/* Particle Background */}
        <ParticleBackground />
        
        <div className="viewer-container">
          {/* Empty state - shown when no model selected */}
          {!currentModelUrl && (
            <div className="empty-state">
              <svg className="empty-icon" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M21 7.5l-9-5.25L3 7.5m18 0l-9 5.25m9-5.25v9l-9 5.25M3 7.5l9 5.25M3 7.5v9l9 5.25m0-9v9" />
              </svg>
              <h3>{t('emptyStateTitle')}</h3>
              <p>{t('emptyStateHint')}</p>
            </div>
          )}

          {/* Viewer with internal empty state handling */}
          <ViewerCanvas />
        </div>

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
      
      {/* Help Panel - always visible */}
      <Help />
    </div>
  )
}

export default App
