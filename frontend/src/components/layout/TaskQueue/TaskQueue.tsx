import React, { useEffect, useState } from 'react';

import { useTranslation } from 'react-i18next';

import { useAppStore } from '@/store/useAppStore';

import { cancelTask } from '@/api';

import { isActiveTaskStatus } from '@/utils';

import type { Task } from '@/types';

import styles from './TaskQueue.module.css';

// Format an elapsed duration (seconds) as m:ss or h:mm:ss.
function formatElapsed(seconds: number): string {
    const total = Math.max(0, Math.floor(seconds));
    const mins = Math.floor(total / 60);
    const secs = total % 60;
    if (mins < 60) {
        return `${mins}:${String(secs).padStart(2, '0')}`;
    }
    const hours = Math.floor(mins / 60);
    return `${hours}:${String(mins % 60).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
}

// Status icons as inline SVG components
const ClockIcon = () => (
    <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
);

const SpinnerIcon = () => (
    <svg className={styles.spin} width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
    </svg>
);

const CheckIcon = () => (
    <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" />
    </svg>
);

const XIcon = () => (
    <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
    </svg>
);

const CancelIcon = () => (
    <svg width="12" height="12" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
    </svg>
);

// Build a viewer URL that works for both the local machine and LAN clients.
// The backend reports the viewer's listening port; we rebuild the host from the
// address the user actually used to reach Sharp GUI (localhost locally, the
// reconstruction machine's LAN IP for remote clients), since the trainer's
// viewer listens on all interfaces. Falls back to the raw URL when no port.
function resolveViewerUrl(task: Task): string | undefined {
    const port = task.details?.viewer_port;
    if (port && typeof window !== 'undefined' && window.location?.hostname) {
        return `http://${window.location.hostname}:${port}`;
    }
    return task.details?.viewer_url;
}

export const TaskQueue: React.FC = () => {
    const { t } = useTranslation();
    const { tasks, removeTask } = useAppStore();

    // Keep failed tasks visible for diagnostics alongside all active states.
    const activeTasks = tasks.filter(
        (task) => isActiveTaskStatus(task.status) || task.status === 'failed',
    );

    // Tick once per second while a task is running, to keep the elapsed timer live.
    const [nowMs, setNowMs] = useState(() => Date.now());
    const hasProcessing = activeTasks.some(
        (task) => task.status === 'running' || task.status === 'processing',
    );
    useEffect(() => {
        if (!hasProcessing) {
            return;
        }
        const intervalId = window.setInterval(() => setNowMs(Date.now()), 1000);
        return () => window.clearInterval(intervalId);
    }, [hasProcessing]);

    // Handle cancel task
    const handleCancel = async (taskId: string) => {
        try {
            await cancelTask(taskId);
            removeTask(taskId);
        } catch (error) {
            console.error('Failed to cancel task:', error);
        }
    };

    // Get status icon and color
    const getStatusInfo = (status: string) => {
        switch (status) {
            case 'pending':
                return { icon: <ClockIcon />, color: '#f0ad4e' };
            case 'processing':
            case 'running':
                return { icon: <SpinnerIcon />, color: '#0071e3' };
            case 'completed':
                return { icon: <CheckIcon />, color: '#28a745' };
            case 'failed':
                return { icon: <XIcon />, color: '#dc3545' };
            default:
                return { icon: <ClockIcon />, color: '#666' };
        }
    };

    // Don't render if no active tasks
    if (activeTasks.length === 0) {
        return null;
    }

    const getTaskStageText = (task: Task) => {
        if (task.status === 'processing' && task.stage) {
            const key = `taskStage.${task.stage}`;
            const translated = t(key);
            return translated === key ? task.stage : translated;
        }
        const statusKey = `taskStatus.${task.status}`;
        const translatedStatus = t(statusKey);
        return translatedStatus === statusKey ? task.status : translatedStatus;
    };

    const getTaskErrorText = (task: Task) => {
        if (!task.error) {
            return null;
        }
        if (task.error_code) {
            const key = `videoReconError.${task.error_code}`;
            const translated = t(key);
            if (translated !== key) {
                return translated;
            }
        }
        return task.error;
    };

    return (
        <div className={styles.container}>
            <div className={styles.sectionTitle}>{t('processingQueue')}</div>
            
            {activeTasks.map(task => {
                const { icon, color } = getStatusInfo(task.status);
                const showProgress = task.status === 'processing' && task.progress !== undefined;
                const canCancel = isActiveTaskStatus(task.status);
                const errorText = getTaskErrorText(task);
                const stageText = getTaskStageText(task);
                const viewerUrl = task.status === 'processing' ? resolveViewerUrl(task) : undefined;
                const elapsedText =
                    task.status === 'processing' && task.started_at
                        ? formatElapsed(nowMs / 1000 - task.started_at)
                        : null;

                return (
                    <div key={task.id} className={styles.queueItem}>
                        {/* Status Icon */}
                        <div className={styles.statusIcon} style={{ color }}>
                            {icon}
                        </div>

                        {/* Content */}
                        <div className={styles.itemContent}>
                            <div className={styles.filename} data-tooltip={task.filename}>{task.filename}</div>
                            
                            {/* Progress Bar */}
                            {showProgress && (
                                <>
                                    <div className={styles.progressBar}>
                                        <div 
                                            className={styles.progressFill} 
                                            style={{ width: `${task.progress}%` }}
                                        />
                                    </div>
                                    <div className={styles.progressMeta}>
                                        <span className={styles.progressText}>{task.progress}%</span>
                                        {elapsedText ? (
                                            <span className={styles.elapsedText}>{elapsedText}</span>
                                        ) : null}
                                    </div>
                                </>
                            )}
                            {!showProgress && elapsedText ? (
                                <div className={styles.elapsedMeta}>
                                    <span className={styles.elapsedText}>{elapsedText}</span>
                                </div>
                            ) : null}
                            {errorText ? <div className={styles.errorText} data-tooltip={errorText}>{errorText}</div> : null}
                            {viewerUrl ? (
                                <a
                                    className={styles.viewerLink}
                                    href={viewerUrl}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    onClick={(event) => event.stopPropagation()}
                                    data-tooltip={viewerUrl}
                                >
                                    {t('videoReconLiveProgress')}
                                </a>
                            ) : null}
                        </div>

                        {/* Status Text */}
                        <div className={styles.statusText} data-tooltip={stageText}>
                            {stageText}
                        </div>

                        {/* Cancel Button */}
                        {canCancel && (
                            <button 
                                className={styles.cancelBtn}
                                onClick={() => handleCancel(task.id)}
                                data-tooltip={t('cancel')}
                                aria-label={t('cancel')}
                            >
                                <CancelIcon />
                            </button>
                        )}
                    </div>
                );
            })}
        </div>
    );
};
