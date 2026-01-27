import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useAppStore } from '@/store/useAppStore';
import { fetchSettings, saveSettings, browseFolder, restartServer } from '@/api';
import styles from './Settings.module.css';

// Folder icon
const FolderIcon = () => (
    <svg width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
    </svg>
);

export const Settings: React.FC = () => {
    const { t } = useTranslation();
    const { settingsModalOpen, setSettingsModalOpen, setLoading } = useAppStore();
    const [workspaceFolder, setWorkspaceFolder] = useState('');
    const [isSaving, setIsSaving] = useState(false);

    // Load settings when modal opens
    useEffect(() => {
        if (settingsModalOpen) {
            loadSettings();
        }
    }, [settingsModalOpen]);

    const loadSettings = async () => {
        try {
            const data = await fetchSettings();
            if (data.workspace_folder) {
                setWorkspaceFolder(data.workspace_folder);
            }
        } catch (error) {
            console.error('Failed to load settings:', error);
        }
    };

    const handleClose = () => {
        setSettingsModalOpen(false);
    };

    const handleBackdropClick = (e: React.MouseEvent) => {
        if (e.target === e.currentTarget) {
            handleClose();
        }
    };

    const handleBrowse = async () => {
        try {
            const result = await browseFolder('Select Workspace Folder', workspaceFolder);
            if (result.path) {
                setWorkspaceFolder(result.path);
            }
        } catch (error) {
            console.error('Browse failed:', error);
        }
    };

    const handleSave = async () => {
        setIsSaving(true);
        try {
            const result = await saveSettings({ workspace_folder: workspaceFolder });
            if (result.success) {
                handleClose();
                
                // Show loading overlay
                setLoading(true, 'Restarting server...');
                
                // Trigger backend restart
                try {
                    await restartServer();
                } catch {
                    // Restart will close connection, this is expected
                }
                
                // Reload page after delay (wait for server restart)
                setTimeout(() => {
                    window.location.reload();
                }, 3000);
            } else {
                alert('Error: ' + (result.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Failed to save settings:', error);
            alert('Failed to save settings');
        } finally {
            setIsSaving(false);
        }
    };

    return (
        <div 
            className={`${styles.modal} ${settingsModalOpen ? styles.visible : ''}`}
            onClick={handleBackdropClick}
        >
            <div className={styles.panel}>
                <h3 className={styles.title}>⚙️ {t('settings')}</h3>

                <div className={styles.group}>
                    <label className={styles.label}>
                        Workspace Folder ({t('workspaceFolder') || '工作目录'})
                    </label>
                    <div className={styles.inputWrapper}>
                        <input
                            type="text"
                            className={styles.input}
                            value={workspaceFolder}
                            onChange={(e) => setWorkspaceFolder(e.target.value)}
                            placeholder="/path/to/workspace"
                        />
                        <button 
                            className={styles.browseBtn}
                            onClick={handleBrowse}
                            title="Browse"
                        >
                            <FolderIcon />
                        </button>
                    </div>
                    <p className={styles.hint}>
                        📁 inputs/ ({t('images') || '图片'}) &nbsp;&nbsp; 📁 outputs/ ({t('models') || '模型'})
                    </p>
                </div>

                <p className={styles.warning}>
                    ⚠️ {t('settingsRestartWarning') || '修改后需重启服务器生效'}
                </p>

                <div className={styles.actions}>
                    <button className={styles.cancelBtn} onClick={handleClose}>
                        {t('cancel')}
                    </button>
                    <button 
                        className={styles.saveBtn} 
                        onClick={handleSave}
                        disabled={isSaving}
                    >
                        {isSaving ? '...' : t('save')}
                    </button>
                </div>
            </div>
        </div>
    );
};
