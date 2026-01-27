import React from 'react';
import { useTranslation } from 'react-i18next';
import { useAppStore } from '@/store/useAppStore';
import { cancelTask } from '@/api';
import styles from './TaskQueue.module.css';

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

export const TaskQueue: React.FC = () => {
    const { t } = useTranslation();
    const { tasks, setTasks } = useAppStore();

    // Filter active tasks (pending, processing, failed)
    const activeTasks = tasks.filter(task => 
        task.status === 'pending' || 
        task.status === 'processing' || 
        task.status === 'failed'
    );

    // Handle cancel task
    const handleCancel = async (taskId: string) => {
        try {
            await cancelTask(taskId);
            // Remove from local state
            setTasks(
                tasks.filter(t => t.id !== taskId),
                tasks.some(t => t.id !== taskId && (t.status === 'pending' || t.status === 'processing'))
            );
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

    return (
        <div className={styles.container}>
            <div className={styles.sectionTitle}>{t('processingQueue')}</div>
            
            {activeTasks.map(task => {
                const { icon, color } = getStatusInfo(task.status);
                const showProgress = task.status === 'processing' && task.progress !== undefined;
                const canCancel = task.status === 'pending' || task.status === 'processing';

                return (
                    <div key={task.id} className={styles.queueItem}>
                        {/* Status Icon */}
                        <div className={styles.statusIcon} style={{ color }}>
                            {icon}
                        </div>

                        {/* Content */}
                        <div className={styles.itemContent}>
                            <div className={styles.filename}>{task.filename}</div>
                            
                            {/* Progress Bar */}
                            {showProgress && (
                                <>
                                    <div className={styles.progressBar}>
                                        <div 
                                            className={styles.progressFill} 
                                            style={{ width: `${task.progress}%` }}
                                        />
                                    </div>
                                    <div className={styles.progressText}>{task.progress}%</div>
                                </>
                            )}
                        </div>

                        {/* Status Text */}
                        <div className={styles.statusText}>
                            {task.status === 'processing' && task.stage ? task.stage : task.status}
                        </div>

                        {/* Cancel Button */}
                        {canCancel && (
                            <button 
                                className={styles.cancelBtn}
                                onClick={() => handleCancel(task.id)}
                                title="Cancel"
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
