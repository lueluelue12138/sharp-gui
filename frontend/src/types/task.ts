// Task status enum
export type TaskStatus = 'pending' | 'running' | 'processing' | 'completed' | 'failed' | 'cancelled';

// Task from API
export interface Task {
  id: string;
  filename: string;
  status: TaskStatus;
  progress?: number;
  stage?: string; // e.g., "preprocessing", "training", etc.
  error?: string;
  created_at?: string;
}

// API response for tasks
export interface TasksResponse {
  tasks: Task[];
  has_active: boolean;
}

// Generate API response
export interface GenerateResponse {
  success: boolean;
  tasks?: Task[];
  error?: string;
}
