import { useCallback, useEffect, useRef } from 'react';

import { useShallow } from 'zustand/react/shallow';

import { fetchTasks, fetchGallery } from '@/api';
import { useAppStore } from '@/store/useAppStore';
import { createTaskStatusMap, hasNewlyCompletedTask } from '@/utils';

const POLLING_INTERVAL = 3000; // 3 seconds

export const useTaskQueue = () => {
    const tasks = useAppStore((state) => state.tasks);
    const hasActiveTasks = useAppStore((state) => state.hasActiveTasks);
    const canUsePrivateApi = useAppStore((state) => state.isAuthenticated || state.isOwnerAccess);
    const { setTasks, setGalleryItems } = useAppStore(
        useShallow((state) => ({
            setTasks: state.setTasks,
            setGalleryItems: state.setGalleryItems,
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
        try {
            const data = await fetchTasks();
            const shouldRefreshGallery = hasNewlyCompletedTask(
                taskStatusesRef.current,
                data.tasks,
            );

            // A completed model is publishable independently of other queued
            // tasks, so refresh even while the queue remains active. Fetch it
            // before committing the completed state so a transient gallery
            // error leaves polling active and can be retried automatically.
            if (shouldRefreshGallery) {
                const gallery = await fetchGallery();
                setGalleryItems(gallery);
            }

            taskStatusesRef.current = createTaskStatusMap(data.tasks);
            setTasks(data.tasks, data.has_active);
        } catch (error) {
            console.error('Task polling error:', error);
        } finally {
            pollInFlightRef.current = false;
        }
    }, [canUsePrivateApi, setTasks, setGalleryItems]);

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
