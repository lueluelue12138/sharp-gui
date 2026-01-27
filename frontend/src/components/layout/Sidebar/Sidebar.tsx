import { useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useAppStore } from '@/store';
import { toggleLanguage } from '@/i18n';
import { 
  GalleryIcon, 
  PlusIcon, 
  SettingsIcon, 
  ChevronLeftIcon 
} from '@/components/common/Icons';
import { Button } from '@/components/common/Button';
import { TaskQueue } from '@/components/layout/TaskQueue';
import styles from './Sidebar.module.css';

interface SidebarProps {
  onUpload: (files: FileList) => void;
  children?: React.ReactNode;
}

export function Sidebar({ onUpload, children }: SidebarProps) {
  const { t, i18n } = useTranslation();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  
  const {
    sidebarOpen,
    sidebarCollapsed,
    isLocalAccess,
    toggleSidebar,
    toggleSidebarCollapsed,
    setSettingsModalOpen,
  } = useAppStore();

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
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
            <GalleryIcon width={20} height={20} />
            <span>{t('appTitle')}</span>
            
            {/* Settings button (local only) */}
            {isLocalAccess && (
              <button 
                className={styles.settingsBtn} 
                onClick={() => setSettingsModalOpen(true)}
                title={t('settings')}
              >
                <SettingsIcon width={16} height={16} />
              </button>
            )}
            
            {/* Language toggle */}
            <button className={styles.langBtn} onClick={handleLangToggle}>
              {i18n.language === 'en' ? '中文' : 'EN'}
            </button>
          </div>

          {/* Upload button */}
          <Button 
            variant="primary" 
            icon={<PlusIcon />}
            onClick={() => fileInputRef.current?.click()}
            className={styles.uploadBtn}
          >
            {t('generateNew')}
          </Button>
          
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            multiple
            hidden
            onChange={handleFileChange}
          />
        </div>

        {/* Content (Queue + Gallery) */}
        <div className={styles.content}>
          <TaskQueue />
          {children}
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
