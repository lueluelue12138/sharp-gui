import { apiGet, apiPost, apiPostFormDataWithProgress } from '@/api/client';
import type {
  VideoReconstructionConfig,
  VideoReconstructionCustomOptions,
  VideoReconstructionEngine,
  VideoReconstructionRequest,
  VideoReconstructionResponse,
  VideoReconstructionStatusResponse,
} from '@/types';

export function normalizeVideoReconstructionConfig(
  config: VideoReconstructionConfig,
): VideoReconstructionConfig {
  const savedEngine = String(config.default_engine);
  return {
    ...config,
    default_engine: savedEngine === 'splatfacto' || savedEngine === 'stable' ? 'splatfacto' : 'brush',
  };
}

function selectCustomOptions(
  engine: VideoReconstructionEngine,
  options: VideoReconstructionCustomOptions,
): VideoReconstructionCustomOptions {
  return {
    frame_count: options.frame_count,
    max_num_iterations: options.max_num_iterations,
    matching_method: options.matching_method,
    ...(engine === 'brush'
      ? { max_resolution: options.max_resolution }
      : { downscale_factor: options.downscale_factor, cache_images: options.cache_images }),
  };
}

interface UploadProgress {
  loaded: number;
  total: number | null;
  percent: number;
  lengthComputable: boolean;
}

export async function fetchVideoReconstructionStatus(options?: {
  refresh?: boolean;
}): Promise<VideoReconstructionStatusResponse> {
  const query = options?.refresh ? '?refresh=1' : '';
  const status = await apiGet<VideoReconstructionStatusResponse>(`/api/video-reconstructions/status${query}`);
  return { ...status, config: normalizeVideoReconstructionConfig(status.config) };
}

export async function createVideoReconstruction(
  request: VideoReconstructionRequest,
): Promise<VideoReconstructionResponse> {
  return apiPost<VideoReconstructionResponse>(
    '/api/video-reconstructions',
    {
      ...request,
      custom_options: request.quality === 'custom' && request.custom_options
        ? selectCustomOptions(request.engine, request.custom_options)
        : undefined,
    },
    { timeout: 300000 },
  );
}

export async function createVideoReconstructionFromFile(
  file: File,
  options?: Omit<VideoReconstructionRequest, 'video_id'>,
  uploadOptions?: {
    onUploadProgress?: (progress: UploadProgress) => void;
  },
): Promise<VideoReconstructionResponse> {
  const formData = new FormData();
  formData.append('file', file);
  if (options?.mode) {
    formData.append('mode', options.mode);
  }
  if (options?.quality) {
    formData.append('quality', options.quality);
  }
  if (options?.quality === 'custom' && options.custom_options) {
    formData.append('custom_options', JSON.stringify(selectCustomOptions(options.engine, options.custom_options)));
  }
  if (options?.engine) {
    formData.append('engine', options.engine);
  }
  if (options?.output_name) {
    formData.append('output_name', options.output_name);
  }
  if (typeof options?.keep_intermediate_files === 'boolean') {
    formData.append('keep_intermediate_files', String(options.keep_intermediate_files));
  }

  return apiPostFormDataWithProgress<VideoReconstructionResponse>(
    '/api/video-reconstructions/upload',
    formData,
    {
      timeout: 300000,
      onUploadProgress: uploadOptions?.onUploadProgress,
    },
  );
}
