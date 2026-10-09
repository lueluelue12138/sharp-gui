// Task status enum
export type TaskStatus = 'pending' | 'running' | 'processing' | 'completed' | 'failed' | 'cancelled';

// Task from API
export interface Task {
  id: string;
  filename: string;
  status: TaskStatus;
  kind?: 'image_sharp' | 'video_3dgs' | string;
  progress?: number;
  stage?: string; // e.g., "preprocessing", "training", etc.
  error?: string;
  error_code?: string | null;
  created_at?: string;
  source_media_id?: string;
  source_name?: string;
  mode?: string;
  quality?: string;
  custom_options?: {
    frame_count?: number;
    max_num_iterations?: number;
    max_resolution?: number;
    downscale_factor?: number;
    matching_method?: string;
    cache_images?: string;
  };
  engine?: string;
  resolved_engine?: string;
  vram_budget?: string;
  output_name?: string;
  started_at?: number;
  completed_at?: number;
  details?: {
    warnings?: Array<{
      code: string;
      message: string;
    }>;
    viewer_url?: string;
    viewer_port?: number;
  };
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
