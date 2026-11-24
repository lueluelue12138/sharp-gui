import { useEffect, useId, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { createPortal } from 'react-dom';

import { ChevronRight, LoaderCircle, Square, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { useAppStore } from '@/store/useAppStore';

import { cancelTask } from '@/api';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';

import { isActiveTaskStatus } from '@/utils';
import { progressPercent } from '@/utils/portraitProgress';

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

function getStatusInfo(status: string) {
    switch (status) {
        case 'queued':
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
}

function portraitPercent(task: PortraitTask) {
    if (task.status === 'completed' && task.stage !== 'upload') return 100;
    if (task.status === 'running' && task.progress) return progressPercent(task.progress);
}

type ImageTask = { kind: 'portrait'; task: PortraitTask } | { kind: 'model'; task: Task };

function imageTaskStatus(entry: ImageTask): PortraitTask['status'] {
    if (entry.kind === 'portrait') return entry.task.status;
    if (entry.task.status === 'pending') return 'queued';
    return entry.task.status === 'failed' ? 'failed' : 'running';
}

const groupOrder = { running: 0, queued: 1, failed: 2, completed: 3 };
const collapsedQueueKey = 'sharp-gui-task-queue-collapsed';
const dismissedFailuresKey = 'sharp-gui-dismissed-task-failures';

function readDismissedFailures(): string[] {
    try {
        const stored: unknown = JSON.parse(localStorage.getItem(dismissedFailuresKey) ?? '[]');
        return Array.isArray(stored) ? stored.filter((id): id is string => typeof id === 'string') : [];
    } catch {
        return [];
    }
}

function ImageTaskGroup({ name, count, status, percent, selected, onClose, closing, disabled, children }: {
    name: string; count: number; status: PortraitTask['status']; percent: number | undefined;
    onClose: () => void; closing: boolean; disabled: boolean;
    selected: boolean; children: ReactNode;
}) {
    const { t } = useTranslation();
    const [expanded, setExpanded] = useState(false);
    const panelId = useId();
    const { icon, color } = getStatusInfo(status);
    const action = t(isActiveAngle(status) ? 'portrait.taskQueue.cancelGroup' : 'portrait.taskQueue.closeGroup', { name });
    return (
        <div className={`${styles.queueItem} ${styles.imageGroup}`} data-selected={selected}>
            <div className={styles.groupHeader}>
              <button type="button" className={`${styles.angleOpen} ${styles.groupToggle}`}
                aria-expanded={expanded} aria-controls={panelId} onClick={() => setExpanded((value) => !value)}>
                <span className={styles.statusIcon} style={{ color }} aria-hidden="true">{icon}</span>
                <span className={styles.itemContent}>
                    <span className={styles.filename} data-tooltip={name}>{name}</span>
                    <span className={styles.angleStage}>{t('portrait.taskQueue.imageTasks', { count })}</span>
                    {percent !== undefined && <span className={styles.progressBar} aria-hidden="true">
                        <span className={styles.progressFill} style={{ width: `${percent}%` }} />
                    </span>}
                </span>
                <span className={styles.angleStatus}>
                    {t(`portrait.taskQueue.status.${status}`)}
                    {percent !== undefined && <strong>{percent}%</strong>}
                </span>
                <ChevronRight className={styles.groupChevron} size={15} aria-hidden="true" />
              </button>
              <button type="button" className={styles.angleClose} aria-label={action} data-tooltip={action}
                  aria-busy={closing} disabled={disabled} onClick={onClose}>
                  {closing ? <LoaderCircle size={14} className={styles.spin} aria-hidden="true" />
                    : isActiveAngle(status) ? <Square size={12} aria-hidden="true" /> : <X size={15} aria-hidden="true" />}
              </button>
            </div>
            <div id={panelId} className={styles.groupTasks} hidden={!expanded}>{expanded && children}</div>
        </div>
    );
}

export function TaskQueue({ angleTasks, portraitSourceKeys, activeAngleId, onOpenAngle, onCloseAngle, onCloseAngleGroup }: {
    angleTasks: PortraitTask[]; activeAngleId: string | null; onOpenAngle: (id: string) => void;
    portraitSourceKeys: ReadonlyMap<string, string>;
    onCloseAngle: (id: string) => void;
    onCloseAngleGroup: (ids: string[]) => Promise<void>;
}) {
    const { t } = useTranslation();
    const tasks = useAppStore((state) => state.tasks);
    const removeTask = useAppStore((state) => state.removeTask);
    const queueId = useId();
    const [dismissedFailures, setDismissedFailures] = useState(() => new Set(readDismissedFailures()));
    const [groupCancellation, setGroupCancellation] = useState<{ key: string; name: string }>();
    const [closingGroup, setClosingGroup] = useState<string>();
    const [groupCancelError, setGroupCancelError] = useState(false);
    const closing = useRef(false);
    const [collapsed, setCollapsed] = useState(() => {
        try {
            return localStorage.getItem(collapsedQueueKey) === '1';
        } catch {
            return false;
        }
    });

    function toggleQueue() {
        setCollapsed(!collapsed);
        try {
            localStorage.setItem(collapsedQueueKey, collapsed ? '0' : '1');
        } catch {
            // The queue can still be collapsed for this page.
        }
    }

    function dismissFailure(taskId: string) {
        const next = new Set([...readDismissedFailures(), ...dismissedFailures, taskId]);
        setDismissedFailures(next);
        try {
            localStorage.setItem(dismissedFailuresKey, JSON.stringify([...next]));
        } catch {
            // The failed task stays dismissed for this page.
        }
    }

    const activeTasks = tasks.filter(
        (task) => isActiveTaskStatus(task.status) || (task.status === 'failed' && !dismissedFailures.has(task.id)),
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

    if (activeTasks.length === 0 && angleTasks.length === 0) {
        return null;
    }

    const order = { running: 0, queued: 1, completed: 2, failed: 2 };
    const sortedAngles = [...angleTasks].sort((first, second) => order[first.status] - order[second.status]
        || (first.status === 'queued' ? first.startedAt - second.startedAt : second.startedAt - first.startedAt));

    const groups = new Map<string, ImageTask[]>();
    function addImageTask(key: string, entry: ImageTask) {
        const existing = groups.get(key);
        if (existing) existing.push(entry);
        else groups.set(key, [entry]);
    }
    for (const task of sortedAngles) {
        const key = portraitSourceKeys.get(task.workspaceId) ?? `workspace:${task.originId ?? task.workspaceId}`;
        addImageTask(key, { kind: 'portrait', task });
    }
    const videos = activeTasks.filter((task) => task.kind === 'video_3dgs');
    for (const task of activeTasks) {
        if (task.kind === 'video_3dgs') continue;
        const key = task.source_media_id ? `media:${task.source_media_id}` : `model:${task.source_id ?? task.id}`;
        addImageTask(key, { kind: 'model', task });
    }
    const imageGroups = [...groups].map(([key, entries]) => {
        const lead = entries.reduce((current, entry) =>
            groupOrder[imageTaskStatus(entry)] < groupOrder[imageTaskStatus(current)] ? entry : current);
        return { key, entries, lead, status: imageTaskStatus(lead) };
    }).sort((a, b) => groupOrder[a.status] - groupOrder[b.status]);

    async function closeGroup(key: string, name: string) {
        if (closing.current) return;
        closing.current = true;
        setClosingGroup(key);
        setGroupCancelError(false);
        const entries = groups.get(key) ?? [];
        const portraits = entries.flatMap((entry) => entry.kind === 'portrait' ? [entry.task.workspaceId] : []);
        const models = entries.flatMap((entry) => entry.kind === 'model' ? [entry.task] : []);
        const results = await Promise.allSettled([
            onCloseAngleGroup(portraits),
            ...models.map(async (task) => {
                const current = useAppStore.getState().tasks.find((item) => item.id === task.id);
                if (isActiveTaskStatus(current?.status)) await cancelTask(task.id);
                if (current?.status === 'failed') dismissFailure(task.id);
                else removeTask(task.id);
            }),
        ]);
        if (results.some((result) => result.status === 'rejected')) {
            setGroupCancellation({ key, name });
            setGroupCancelError(true);
        } else {
            setGroupCancellation(undefined);
        }
        setClosingGroup(undefined);
        closing.current = false;
    }

    function requestCloseGroup(key: string, name: string, status: PortraitTask['status']) {
        setGroupCancelError(false);
        if (isActiveAngle(status)) setGroupCancellation({ key, name });
        else void closeGroup(key, name);
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

    function renderPortraitRow(task: PortraitTask) {
        const { icon, color } = getStatusInfo(task.status);
        const selected = task.workspaceId === activeAngleId;
        const stage = t(`portrait.taskQueue.stage.${task.stage}`) + (task.batch ? ` · ${task.batch.index}/${task.batch.count}` : '');
        const status = t(`portrait.taskQueue.status.${task.status}`);
        const active = isActiveAngle(task.status);
        const percent = portraitPercent(task);
        const tool = t(!task.tool || task.tool === 'reframe' ? 'portrait.title' : `photoTools.${task.tool}`);
        const action = t(active ? 'portrait.taskQueue.cancel' : 'portrait.taskQueue.close', { name: task.filename, tool });
        return (
            <div key={`portrait:${task.workspaceId}`} className={styles.taskRow} data-selected={selected}>
                <button type="button" className={styles.angleOpen} onClick={() => onOpenAngle(task.workspaceId)}
                    aria-current={selected ? 'true' : undefined}
                    aria-label={t('portrait.taskQueue.open', { name: task.filename, tool, stage, status })}>
                    <span className={styles.statusIcon} style={{ color }} aria-hidden="true">{icon}</span>
                    <span className={styles.itemContent}>
                        <span className={styles.angleStage} data-tooltip={`${tool} · ${stage}`}>{tool} · {stage}</span>
                        {percent !== undefined && <span className={styles.progressBar} aria-hidden="true">
                            <span className={styles.progressFill} style={{ width: `${percent}%` }} />
                        </span>}
                    </span>
                    <span className={styles.angleStatus}>{status}{percent !== undefined && <strong>{percent}%</strong>}</span>
                    <ChevronRight className={styles.angleChevron} size={14} aria-hidden="true" />
                </button>
                <button type="button" className={styles.angleClose} aria-label={action} data-tooltip={action}
                    disabled={closingGroup !== undefined}
                    onClick={() => onCloseAngle(task.workspaceId)}>
                    {active ? <Square size={12} aria-hidden="true" /> : <X size={15} aria-hidden="true" />}
                </button>
            </div>
        );
    }

    function renderModelRow(task: Task, grouped: boolean) {
        const { icon, color } = getStatusInfo(task.status);
        const showProgress = task.status === 'processing' && task.progress !== undefined;
        const canCancel = isActiveTaskStatus(task.status);
        const failed = task.status === 'failed';
        const actionLabel = t(failed ? 'dismissFailedTask' : 'cancel');
        const errorText = getTaskErrorText(task);
        const stageText = getTaskStageText(task);
        const elapsedText = task.status === 'processing' && task.started_at
            ? formatElapsed(nowMs / 1000 - task.started_at)
            : null;
        const label = grouped ? t('photoConvertOne') : task.filename;
        return (
            <div key={`model:${task.id}`} className={grouped ? `${styles.taskRow} ${styles.modelTaskRow}` : styles.queueItem}>
                <div className={styles.statusIcon} style={{ color }}>{icon}</div>
                <div className={styles.itemContent}>
                    <div className={styles.filename} data-tooltip={label}>{label}</div>
                    {showProgress && (
                        <>
                            <div className={styles.progressBar}>
                                <div className={styles.progressFill} style={{ width: `${task.progress}%` }} />
                            </div>
                            <div className={styles.progressMeta}>
                                <span className={styles.progressText}>{task.progress}%</span>
                                {elapsedText && <span className={styles.elapsedText}>{elapsedText}</span>}
                            </div>
                        </>
                    )}
                    {!showProgress && elapsedText && (
                        <div className={styles.elapsedMeta}><span className={styles.elapsedText}>{elapsedText}</span></div>
                    )}
                    {errorText && <div className={styles.errorText} data-tooltip={errorText}>{errorText}</div>}
                </div>
                <div className={styles.statusText} data-tooltip={stageText}>{stageText}</div>
                {(canCancel || failed) && (
                    <button type="button" className={styles.cancelBtn}
                        disabled={closingGroup !== undefined}
                        onClick={() => { if (failed) dismissFailure(task.id); else void handleCancel(task.id); }}
                        data-tooltip={actionLabel} aria-label={actionLabel}>
                        <CancelIcon />
                    </button>
                )}
            </div>
        );
    }

    return (
        <section className={styles.container} aria-label={t('processingQueue')}>
            <button type="button" className={styles.sectionTitle} aria-label={t('processingQueue')}
                aria-expanded={!collapsed} aria-controls={queueId} onClick={toggleQueue}>
                <span>{t('processingQueue')}</span>
                <span className={styles.queueCount}>{activeTasks.length + angleTasks.length}</span>
                <ChevronRight className={styles.groupChevron} size={14} aria-hidden="true" />
            </button>
            <div id={queueId} className={styles.queueContents} hidden={collapsed}>
                {imageGroups.map(({ key, entries, lead, status }) => (
                    <ImageTaskGroup key={key} name={entries[0].task.filename} count={entries.length} status={status}
                        percent={lead.kind === 'portrait' ? portraitPercent(lead.task) : status === 'running' ? lead.task.progress : undefined}
                        onClose={() => requestCloseGroup(key, entries[0].task.filename, status)}
                        closing={closingGroup === key} disabled={closingGroup !== undefined}
                        selected={entries.some((entry) => entry.kind === 'portrait' && entry.task.workspaceId === activeAngleId)}>
                        {entries.map((entry) => entry.kind === 'portrait' ? renderPortraitRow(entry.task) : renderModelRow(entry.task, true))}
                    </ImageTaskGroup>
                ))}
                {videos.map((task) => renderModelRow(task, false))}
            </div>
            {groupCancellation && createPortal(<ConfirmDialog isOpen
                title={t('portrait.taskQueue.cancelGroupTitle')}
                message={t(groupCancelError ? 'portrait.taskQueue.cancelGroupError'
                    : closingGroup ? 'portrait.taskQueue.cancelling' : 'portrait.taskQueue.cancelGroupMessage', { name: groupCancellation.name })}
                confirmLabel={t('portrait.taskQueue.cancelGroupTitle')} cancelLabel={t('portrait.taskQueue.keep')}
                danger isBusy={closingGroup !== undefined}
                onConfirm={() => void closeGroup(groupCancellation.key, groupCancellation.name)}
                onClose={() => { if (!closing.current) setGroupCancellation(undefined); }}
            />, document.body)}
        </section>
    );
}
