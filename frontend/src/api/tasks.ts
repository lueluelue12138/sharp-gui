import { apiGet, apiPost, apiPostFormData } from './client';
import type { TasksResponse, GenerateResponse } from '@/types';

/**
 * Fetch all tasks with status
 */
export async function fetchTasks(): Promise<TasksResponse> {
  return apiGet<TasksResponse>('/api/tasks');
}

/**
 * Cancel a specific task
 */
export async function cancelTask(
  taskId: string
): Promise<{ success: boolean; error?: string }> {
  return apiPost(`/api/task/${taskId}/cancel`);
}

/**
 * Upload images to generate 3D models
 */
export async function generateFromImages(
  files: FileList | File[]
): Promise<GenerateResponse> {
  const formData = new FormData();
  
  for (const file of files) {
    if (file.type.startsWith('image/')) {
      formData.append('file', file);
    }
  }
  
  return apiPostFormData<GenerateResponse>('/api/generate', formData);
}
