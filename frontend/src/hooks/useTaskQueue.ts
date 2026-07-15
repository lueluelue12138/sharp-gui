import { useCallback, useEffect, useRef } from 'react';

import { useShallow } from 'zustand/react/shallow';

import { useAppStore } from '@/store/useAppStore';

import { fetchTasks, fetchModelAssets } from '@/api';
import {
    createTaskStatusMap,
    hasActiveTask,
    hasNewlyCompletedTask,
    reconcileTaskSnapshot,
} from '@/utils';

const POLLING_INTERVAL = 3000; // 3 seconds

export const useTaskQueue = () => {
    const tasks = useAppStore((state) => state.tasks);
    const hasActiveTasks = useAppStore((state) => state.hasActiveTasks);
    const canUsePrivateApi = useAppStore((state) => state.isAuthenticated || state.isOwnerAccess);
    const {
        setTasks,
        mergeModelAssetRefresh,
        modelAssetBatchSize,
        modelAssetSource,
        modelAssetFormat,
        modelAssetTag,
        modelAssetSort,
    } = useAppStore(
        useShallow((state) => ({
            setTasks: state.setTasks,
            mergeModelAssetRefresh: state.mergeModelAssetRefresh,
            modelAssetBatchSize: state.modelAssetBatchSize,
            modelAssetSource: state.modelAssetSource,
            modelAssetFormat: state.modelAssetFormat,
            modelAssetTag: state.modelAssetTag,
            modelAssetSort: state.modelAssetSort,
        })),
    );
    
    const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const pollInFlightRef = useRef(false);
    const taskStatusesRef = useRef(createTaskStatusMap(tasks));

    // Keep locally queued tasks visible to the transition detector before the
    // first server poll observes them.
    useEffect(() => {
        taskStatusesRef.current = createTaskStatusMap(tasks);
    }, [tasks]);

    // Polling logic
    const poll = useCallback(async () => {
        if (!canUsePrivateApi || pollInFlightRef.current) {
            return;
        }

        pollInFlightRef.current = true;
        const tasksAtRequestStart = useAppStore.getState().tasks;
        try {
            const data = await fetchTasks();
            const shouldRefreshGallery = hasNewlyCompletedTask(
                taskStatusesRef.current,
                data.tasks,
            );

            // A completed model is publishable independently of other queued
            // tasks, so refresh even while the queue remains active. The
            // backend refreshes the durable asset catalog before publishing
            // the completed state, so this stays a warm catalog read.
            if (shouldRefreshGallery) {
                const modelAssets = await fetchModelAssets({
                    source: modelAssetSource,
                    format: modelAssetFormat,
                    tag: modelAssetTag,
                    sort: modelAssetSort,
                    limit: modelAssetBatchSize,
                });
                mergeModelAssetRefresh(modelAssets);
            }

            const nextTasks = reconcileTaskSnapshot(
                useAppStore.getState().tasks,
                data.tasks,
                tasksAtRequestStart,
            );
            taskStatusesRef.current = createTaskStatusMap(nextTasks);
            setTasks(nextTasks, hasActiveTask(nextTasks));
        } catch (error) {
            console.error('Task polling error:', error);
        } finally {
            pollInFlightRef.current = false;
        }
    }, [
        canUsePrivateApi,
        mergeModelAssetRefresh,
        modelAssetBatchSize,
        modelAssetFormat,
        modelAssetSort,
        modelAssetSource,
        modelAssetTag,
        setTasks,
    ]);

    // Start/stop polling based on hasActiveTasks
    useEffect(() => {
        if (hasActiveTasks && canUsePrivateApi) {
            void poll();
            if (!pollingRef.current) {
                pollingRef.current = setInterval(poll, POLLING_INTERVAL);
            }
        } else {
            // Stop polling
            if (pollingRef.current) {
                clearInterval(pollingRef.current);
                pollingRef.current = null;
            }
        }

        return () => {
            if (pollingRef.current) {
                clearInterval(pollingRef.current);
                pollingRef.current = null;
            }
        };
    }, [canUsePrivateApi, hasActiveTasks, poll]);

    // Force refresh
    const forceRefresh = useCallback(async () => {
        await poll();
    }, [poll]);

    return {
        tasks,
        hasActiveTasks,
        forceRefresh
    };
};
