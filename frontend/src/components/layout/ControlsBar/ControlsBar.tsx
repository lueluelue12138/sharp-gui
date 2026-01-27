import React, { useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useAppStore } from '@/store/useAppStore';
import { exportModel } from '@/api/gallery';
import * as Icons from '@/components/common/Icons';
import styles from './ControlsBar.module.css';

interface ControlsBarProps {
    viewerHook: any; 
}

export const ControlsBar: React.FC<ControlsBarProps> = ({ viewerHook }) => {
    const { t } = useTranslation();
    const { 
        isLimitsOn, 
        isGyroEnabled, 
        toggleLimits,
        currentModelId,
        setLoading,
        setLoadingProgress,
        // toggleGyro is now handled by viewerHook for permissions
    } = useAppStore();
    
    // UI state for collapse
    const [collapsed, setCollapsed] = useState(false);

    // Fullscreen state
    const [isFullscreen, setIsFullscreen] = useState(!!document.fullscreenElement);

    React.useEffect(() => {
        const handleFullscreenChange = () => {
            setIsFullscreen(!!document.fullscreenElement);
        };
        document.addEventListener('fullscreenchange', handleFullscreenChange);
        return () => document.removeEventListener('fullscreenchange', handleFullscreenChange);
    }, []);

    const toggleFullscreen = () => {
        if (!document.fullscreenElement) {
            document.documentElement.requestFullscreen();
        } else {
            document.exitFullscreen();
        }
    };

    // Handle export/share
    const handleExport = useCallback(async () => {
        if (!currentModelId) {
            alert(t('selectModelFirst'));
            return;
        }

        // Start loading with initial progress
        setLoading(true, t('preparingExport'));
        setLoadingProgress(0);

        // Simulate progress (backend conversion takes time)
        let progress = 5;
        setLoadingProgress(progress);
        
        const progressInterval = setInterval(() => {
            progress += (85 - progress) * 0.05; // Gradual progress
            setLoadingProgress(progress);

            // Update text based on progress stage
            if (progress < 20) {
                setLoading(true, t('convertingModel'));
            } else if (progress < 60) {
                setLoading(true, t('optimizingData'));
            } else {
                setLoading(true, t('generatingHtml'));
            }
        }, 200);

        try {
            const blob = await exportModel(currentModelId);
            clearInterval(progressInterval);

            // Final stages
            setLoadingProgress(95);
            setLoading(true, t('downloading'));
            
            // Create download link
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${currentModelId}_share.html`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);

            setLoadingProgress(100);
            setTimeout(() => setLoading(false), 300);
        } catch (e) {
            clearInterval(progressInterval);
            setLoading(false);
            const message = e instanceof Error ? e.message : 'Unknown error';
            alert(`${t('exportFailed')}: ${message}`);
        }
    }, [currentModelId, t, setLoading, setLoadingProgress]);

    return (
        <div className={`${styles.controlsWrapper} ${collapsed ? styles.collapsed : ''}`}>
             {/* Collapse Arrow */}
             <div 
                className={styles.collapseArrow}
                onClick={() => setCollapsed(!collapsed)}
            >
                <Icons.ChevronDownIcon />
            </div>

            {/* Controls Bar */}
            <div className={styles.controlsContainer}>
                <div className={styles.glassPanel}>
                    {/* Front View / Free View */}
                    <button 
                        className={`${styles.controlBtn} ${isLimitsOn ? styles.active : ''}`}
                        onClick={toggleLimits}
                    >
                        <Icons.View360Icon />
                        <span>{t("controls_view_front")}</span>
                    </button>

                    {/* Gyro */}
                    <button 
                        className={`${styles.controlBtn} ${styles.gyroBtn} ${isGyroEnabled ? styles.active : ''}`}
                        onClick={() => viewerHook.toggleGyro()}
                        // id="btn-gyro" - Removed ID styling reliance
                    >
                        <Icons.GyroIcon />
                        <span>{t("controls_gyro")}</span>
                    </button>

                     {/* Move (Joystick) - Touch only */}
                     <button 
                        className={`${styles.controlBtn} ${styles.joystickBtn} ${viewerHook.joystick.isJoystickVisible ? styles.active : ''}`}
                        onClick={() => viewerHook.joystick.toggleJoystick()}
                        id="btn-joystick"
                    >
                        <Icons.JoystickIcon />
                        <span>{t("controls_move")}</span>
                    </button>

                    {/* Reset */}
                    <button 
                        className={styles.controlBtn} 
                        onClick={() => viewerHook.resetCamera()}
                    >
                        <Icons.CameraIcon />
                        <span>{t("controls_reset")}</span>
                    </button>

                     {/* Fullscreen */}
                     <button 
                        className={`${styles.controlBtn} ${isFullscreen ? styles.active : ''}`}
                        onClick={toggleFullscreen}
                    >
                        <Icons.FullscreenIcon />
                        <span>{t("controls_fullscreen")}</span>
                    </button>

                    {/* Share/Export */}
                     <button 
                        className={styles.controlBtn}
                        onClick={handleExport}
                    >
                        <Icons.ShareIcon />
                        <span>{t("controls_share")}</span>
                    </button>
                </div>
            </div>
        </div>
    );
};
