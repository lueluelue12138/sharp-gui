import { useEffect, useState } from 'react';

import { ChevronRight, Square, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { useAppStore } from '@/store/useAppStore';

import { cancelTask } from '@/api';

import { isActiveTaskStatus } from '@/utils';

import type { Task } from '@/types';
import type { PortraitTask } from '@/types/portrait';

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

function isActiveAngle(status: PortraitTask['status']) {
    return status === 'queued' || status === 'running';
}

export function TaskQueue({ angleTasks, activeAngleId, onOpenAngle, onCloseAngle }: {
    angleTasks: PortraitTask[]; activeAngleId: string | null; onOpenAngle: (id: string) => void;
    onCloseAngle: (id: string) => void;
}) {
    const { t } = useTranslation();
    const tasks = useAppStore((state) => state.tasks);
    const removeTask = useAppStore((state) => state.removeTask);

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

    if (activeTasks.length === 0 && angleTasks.length === 0) {
        return null;
    }

    const sortedAngles = [...angleTasks].sort((first, second) => (
        Number(isActiveAngle(second.status)) - Number(isActiveAngle(first.status)) || second.startedAt - first.startedAt
    ));

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
        <section className={styles.container} aria-label={t('processingQueue')}>
            <div className={styles.sectionTitle}>{t('processingQueue')}</div>

            {sortedAngles.map(task => {
                const { icon, color } = getStatusInfo(task.status === 'queued' ? 'pending' : task.status);
                const selected = task.workspaceId === activeAngleId;
                const stage = t(`portrait.taskQueue.stage.${task.stage}`);
                const status = t(`portrait.taskQueue.status.${task.status}`);
                const active = isActiveAngle(task.status);
                const action = t(active ? 'portrait.taskQueue.cancel' : 'portrait.taskQueue.close', { name: task.filename });
                return (
                    <div key={task.workspaceId} className={`${styles.queueItem} ${styles.angleTask}`} data-selected={selected}>
                        <button type="button" className={styles.angleOpen} onClick={() => onOpenAngle(task.workspaceId)}
                            aria-current={selected ? 'true' : undefined}
                            aria-label={t('portrait.taskQueue.open', { name: task.filename, stage, status })}>
                            <span className={styles.statusIcon} style={{ color }} aria-hidden="true">{icon}</span>
                            <span className={styles.itemContent}>
                                <span className={styles.filename} data-tooltip={task.filename}>{task.filename}</span>
                                <span className={styles.angleStage}>{t('portrait.title')} · {stage}</span>
                                {task.percent !== undefined && <span className={styles.progressBar} aria-hidden="true">
                                    <span className={styles.progressFill} style={{ width: `${task.percent}%` }} />
                                </span>}
                            </span>
                            <span className={styles.angleStatus}>{status}{task.percent !== undefined && <strong>{task.percent}%</strong>}</span>
                            <ChevronRight className={styles.angleChevron} size={14} aria-hidden="true" />
                        </button>
                        <button type="button" className={styles.angleClose} aria-label={action} data-tooltip={action}
                            onClick={() => onCloseAngle(task.workspaceId)}>
                            {active ? <Square size={12} aria-hidden="true" /> : <X size={15} aria-hidden="true" />}
                        </button>
                    </div>
                );
            })}
            
            {activeTasks.map(task => {
                const { icon, color } = getStatusInfo(task.status);
                const showProgress = task.status === 'processing' && task.progress !== undefined;
                const canCancel = isActiveTaskStatus(task.status);
                const errorText = getTaskErrorText(task);
                const stageText = getTaskStageText(task);
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
        </section>
    );
}
