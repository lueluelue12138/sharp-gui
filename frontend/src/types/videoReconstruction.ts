import type { Task } from '@/types/task';

export type VideoReconstructionMode = 'auto' | 'object' | 'environment';
export type VideoReconstructionPresetQuality = 'preview' | 'high' | 'extreme';
export type VideoReconstructionQuality = VideoReconstructionPresetQuality | 'custom';
export type VideoReconstructionEngine = 'brush' | 'splatfacto';
export type VideoReconstructionVramBudget = 'auto' | '8gb' | '12gb' | '16gb' | '24gb';
export type VideoReconstructionMatchingMethod = 'sequential' | 'exhaustive';
export type VideoReconstructionCacheImages = 'gpu' | 'cpu';

export interface VideoReconstructionCustomOptions {
  frame_count: number;
  max_num_iterations: number;
  matching_method: VideoReconstructionMatchingMethod;
  max_resolution?: number;
  downscale_factor?: 1 | 2 | 4;
  cache_images?: VideoReconstructionCacheImages;
}

export interface VideoReconstructionConfig {
  default_quality: VideoReconstructionPresetQuality;
  default_engine: VideoReconstructionEngine;
  vram_budget: VideoReconstructionVramBudget;
  keep_intermediate_files: boolean;
}

export interface VideoReconstructionToolStatus {
  name: string;
  category: 'required' | 'stable' | string;
  required: boolean;
  available: boolean;
  version?: string | null;
  message?: string | null;
}

export interface VideoReconstructionDependencyGroup {
  available: boolean;
  tools: VideoReconstructionToolStatus[];
  message?: string | null;
}

export interface VideoReconstructionDependencies {
  required: VideoReconstructionDependencyGroup;
  brush: VideoReconstructionDependencyGroup;
  splatfacto: VideoReconstructionDependencyGroup;
  stable?: VideoReconstructionDependencyGroup;
  summary: {
    available: boolean;
    brush_available: boolean;
    splatfacto_available: boolean;
    stable_available?: boolean;
    checking?: boolean;
    checked_at?: number | null;
    cached?: boolean;
  };
}

export interface VideoReconstructionStatusResponse {
  config: VideoReconstructionConfig;
  dependencies: VideoReconstructionDependencies;
}

export interface VideoReconstructionRequest {
  video_id: string;
  mode: VideoReconstructionMode;
  quality: VideoReconstructionQuality;
  custom_options?: VideoReconstructionCustomOptions;
  engine: VideoReconstructionEngine;
  output_name?: string;
  keep_intermediate_files?: boolean;
}

export interface VideoReconstructionResponse {
  success: boolean;
  task?: Task;
  error?: string;
  code?: string;
  dependencies?: VideoReconstructionDependencies;
}
