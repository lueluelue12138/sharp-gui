import { useRef, useState } from 'react';

import { useTranslation } from 'react-i18next';
import { useShallow } from 'zustand/react/shallow';

import { useAppStore } from '@/store';
import { toggleLanguage } from '@/i18n';
import {
  PlusIcon,
  SettingsIcon,
  ChevronLeftIcon,
  GalleryIcon,
  FolderIcon,
} from '@/components/common/Icons';
import { Button } from '@/components/common/Button';
import { TaskQueue } from '@/components/layout/TaskQueue';
import styles from './Sidebar.module.css';

interface SidebarProps {
  canGenerateModels: boolean;
  onGenerationBlocked: () => void;
  onUpload: (files: FileList) => void;
  children?: React.ReactNode;
}

export function Sidebar({ canGenerateModels, onGenerationBlocked, onUpload, children }: SidebarProps) {
  const { t, i18n } = useTranslation();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragOver, setIsDragOver] = useState(false);

  const {
    sidebarOpen,
    sidebarCollapsed,
    toggleSidebar,
    toggleSidebarCollapsed,
    setSettingsModalOpen,
    activeView,
    setActiveView,
  } = useAppStore(
    useShallow((state) => ({
      sidebarOpen: state.sidebarOpen,
      sidebarCollapsed: state.sidebarCollapsed,
      toggleSidebar: state.toggleSidebar,
      toggleSidebarCollapsed: state.toggleSidebarCollapsed,
      setSettingsModalOpen: state.setSettingsModalOpen,
      activeView: state.activeView,
      setActiveView: state.setActiveView,
    })),
  );

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      if (!canGenerateModels) {
        onGenerationBlocked();
        e.target.value = '';
        return;
      }
      onUpload(e.target.files);
      e.target.value = ''; // Reset input
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    // Only remove if leaving sidebar, not entering child
    const relatedTarget = e.relatedTarget as Node | null;
    if (relatedTarget && !e.currentTarget.contains(relatedTarget)) {
      setIsDragOver(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      onUpload(e.dataTransfer.files);
    }
  };

  const handleGenerateClick = () => {
    if (!canGenerateModels) {
      onGenerationBlocked();
      return;
    }
    fileInputRef.current?.click();
  };

  const handleLangToggle = () => {
    toggleLanguage();
  };

  return (
    <>
      {/* Mobile overlay */}
      <div
        className={`${styles.overlay} ${sidebarOpen ? styles.visible : ''}`}
        onClick={toggleSidebar}
      />

      {/* Sidebar */}
      <aside
        className={`${styles.sidebar} ${sidebarOpen ? styles.open : ''} ${sidebarCollapsed ? styles.collapsed : ''} ${isDragOver ? styles.dragOver : ''}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        {/* Header */}
        <div className={styles.header}>
          <div className={styles.title}>
            <a
              href="https://lueluelue12138.github.io/sharp-gui/"
              target="_blank"
              rel="noopener noreferrer"
              style={{ display: 'flex', alignItems: 'center', gap: '8px', textDecoration: 'none', color: 'inherit' }}
            >
              <img
                src="/logo.png"
                alt="Sharp GUI Logo"
                width={30}
                height={30}
                style={{ imageRendering: 'crisp-edges' }}
              />
              <span>{t('appTitle')}</span>
            </a>

            {/* Settings button */}
            <button
              className={styles.settingsBtn}
              onClick={() => setSettingsModalOpen(true)}
              data-tooltip={t('settings')}
            >
              <SettingsIcon width={16} height={16} />
            </button>

            {/* Language toggle */}
            <button className={styles.langBtn} onClick={handleLangToggle}>
              {i18n.language === 'en' ? '中文' : 'EN'}
            </button>
          </div>

          {/* Upload button */}
          <Button
            variant="primary"
            icon={<PlusIcon />}
            onClick={handleGenerateClick}
            className={styles.uploadBtn}
            aria-disabled={!canGenerateModels}
            data-tooltip={!canGenerateModels ? t('ownerOnlyAction') : undefined}
          >
            {activeView === 'models' ? t('modelAssetGenerateImport') : t('generateNew')}
          </Button>

          <input
            ref={fileInputRef}
            type="file"
            accept="image/*,video/mp4,video/quicktime,video/webm,video/x-matroska,.mp4,.m4v,.mov,.webm,.mkv,.ply,.spz,.splat,.rad"
            multiple
            hidden
            onChange={handleFileChange}
          />

          <div className={styles.viewTabs} role="tablist" aria-label={t('appViewTabs')}>
            <button
              className={[
                styles.viewTab,
                activeView === 'models' ? styles.viewTabActive : '',
              ].filter(Boolean).join(' ')}
              onClick={() => setActiveView('models')}
              role="tab"
              aria-selected={activeView === 'models'}
              type="button"
            >
              <GalleryIcon width={14} height={14} />
              <span>{t('modelView')}</span>
            </button>
            <button
              className={[
                styles.viewTab,
                activeView === 'photos' ? styles.viewTabActive : '',
              ].filter(Boolean).join(' ')}
              onClick={() => setActiveView('photos')}
              role="tab"
              aria-selected={activeView === 'photos'}
              type="button"
            >
              <FolderIcon width={14} height={14} />
              <span>{t('photoView')}</span>
            </button>
          </div>
        </div>

        {/* Content (Queue + Gallery) */}
        <div className={styles.content}>
          {activeView === 'models' ? <TaskQueue /> : null}
          <div className={styles.galleryPane}>
            {children}
          </div>
        </div>
      </aside>

      {/* Collapse toggle button (desktop) */}
      <button
        className={`${styles.toggleBtn} ${sidebarCollapsed ? styles.toggleCollapsed : ''}`}
        onClick={toggleSidebarCollapsed}
        aria-label={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
      >
        <ChevronLeftIcon width={14} height={14} />
      </button>
    </>
  );
}
