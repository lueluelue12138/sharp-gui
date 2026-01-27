import { useEffect, useRef, useCallback } from 'react';
import { useAppStore } from '@/store/useAppStore';
import { fetchTasks, fetchGallery } from '@/api';

const POLLING_INTERVAL = 3000; // 3 seconds

export const useTaskQueue = () => {
    const { 
        tasks, 
        hasActiveTasks, 
        setTasks, 
        setGalleryItems 
    } = useAppStore();
    
    const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const hasActiveRef = useRef(hasActiveTasks);

    // Keep ref in sync with state
    useEffect(() => {
        hasActiveRef.current = hasActiveTasks;
    }, [hasActiveTasks]);

    // Polling logic
    const poll = useCallback(async () => {
        try {
            const data = await fetchTasks();
            setTasks(data.tasks, data.has_active);

            // If a task just completed (was active, now not), refresh gallery
            if (!data.has_active && hasActiveRef.current) {
                const gallery = await fetchGallery();
                setGalleryItems(gallery);
            }
        } catch (error) {
            console.error('Task polling error:', error);
        }
    }, [setTasks, setGalleryItems]);

    // Start/stop polling based on hasActiveTasks
    useEffect(() => {
        if (hasActiveTasks) {
            // Start polling
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
    }, [hasActiveTasks, poll]);

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
