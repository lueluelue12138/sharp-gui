import { ApiError, apiGet, apiPost, apiPostFormData } from '@/api/client';
import type { PortraitAvailability, PortraitCacheRelease, PortraitCancellation, PortraitJob, PortraitLaunch, PortraitProgress, PortraitStageResults, PortraitUpload, RecoveredPortrait } from '@/types/portrait';

const base = '/api/portrait';

export function portraitAvailability(signal?: AbortSignal) {
  return apiGet<PortraitAvailability>(`${base}/status`, { signal });
}

export function startPortraitEngine() {
  return apiPost<PortraitLaunch>(`${base}/start`);
}

export function recentPortraitJobs(signal: AbortSignal) {
  return apiGet<RecoveredPortrait[]>(`${base}/recent`, { signal });
}

export function uploadPortrait(kind: 'source' | 'reference' | 'mask' | 'capture', image: Blob, signal?: AbortSignal) {
  const form = new FormData();
  form.append('image', image);
  return apiPostFormData<PortraitUpload>(`${base}/uploads/${kind}`, form, { signal, timeout: 120000 });
}

export function openGalleryPhoto(photoId: string, signal: AbortSignal) {
  return apiPost<PortraitUpload>(`${base}/gallery-source/${encodeURIComponent(photoId)}`, {}, { signal, timeout: 120000 });
}

export function releasePortraitMemory(signal: AbortSignal) {
  return apiPost<PortraitCacheRelease>(`${base}/memory/release`, {}, { signal });
}

export function cancelPortraitJob(target: PortraitCancellation) {
  return apiPost<{ ok: true }>(`${base}/jobs/cancel`, target, { timeout: 90000 });
}

export async function runPortrait<S extends keyof PortraitStageResults>(
  stage: S,
  options: Record<string, unknown> | undefined,
  onProgress: (progress: PortraitProgress) => void,
  signal: AbortSignal,
  tracking: { requestId?: string; job?: string; onSubmitted: (job: string) => void },
): Promise<PortraitStageResults[S]> {
  let job = tracking.job;
  while (!signal.aborted) {
    let delay = 950;
    try {
      if (!job) {
        const accepted = await apiPost<{ job: string }>(`${base}/jobs/${stage}`, { ...options, request_id: tracking.requestId }, { signal });
        signal.throwIfAborted();
        job = accepted.job;
        tracking.onSubmitted(job);
        onProgress({ state: 'queued' });
      }
      const result = await apiGet<PortraitJob<PortraitStageResults[S]>>(`${base}/jobs/${job}`, { signal });
      signal.throwIfAborted();
      if (result.state === 'done') return result.result;
      if (result.state === 'error') throw new ApiError(result.message, 422, { code: 'portraitRunError' });
      onProgress(result);
      delay = result.state === 'running' ? 450 : 950;
    } catch (problem) {
      signal.throwIfAborted();
      if (!(problem instanceof TypeError || problem instanceof DOMException
        || (problem instanceof ApiError && (problem.status === 503 || problem.status === 504)))) throw problem;
      delay = 2000;
    }
    await new Promise<void>((resolve) => setTimeout(resolve, delay));
  }
  signal.throwIfAborted();
  throw new Error('Portrait job polling stopped.');
}
