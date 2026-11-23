import { ApiError, apiGet, apiPost, apiPostFormData } from '@/api/client';
import type { PortraitAvailability, PortraitCacheRelease, PortraitCancellation, PortraitJob, PortraitLaunch, PortraitProgress, PortraitStageResults, PortraitUpload, RecoveredPortrait } from '@/types/portrait';
import type { VisualWorkflowDependencies, VisualWorkflowName } from '@/types/portrait';
import { downloadFile } from '@/utils/fileDownload';

const base = '/api/portrait';

export function getVisualWorkflow(name: VisualWorkflowName, signal: AbortSignal) {
  return apiGet<VisualWorkflowDependencies>(`${base}/workflows/${name}`, { signal });
}

export function downloadVisualWorkflow(name: VisualWorkflowName) {
  return downloadFile(`${base}/workflows/${name}/download`, {
    fallbackFilename: `SharpGUI-${name}.json`, mimeType: 'application/json',
  });
}

export function portraitAvailability(signal?: AbortSignal, tool?: 'edit' | 'extend') {
  return apiGet<PortraitAvailability>(`${base}${tool ? `/${tool}` : ''}/status`, { signal });
}

export function startPortraitEngine() {
  return apiPost<PortraitLaunch>(`${base}/start`);
}

export function recentPortraitJobs(signal: AbortSignal) {
  return apiGet<RecoveredPortrait[]>(`${base}/recent`, { signal });
}

export function uploadPortrait(kind: 'source' | 'reference' | 'mask' | 'capture' | 'edit-source' | 'extend-source', image: Blob, signal?: AbortSignal) {
  const form = new FormData();
  form.append('image', image);
  return apiPostFormData<PortraitUpload>(`${base}/uploads/${kind}`, form, { signal, timeout: 120000 });
}

export function openGalleryPhoto(photoId: string, signal: AbortSignal, kind: 'source' | 'reference' | 'edit-source' | 'extend-source' = 'source') {
  return apiPost<PortraitUpload>(`${base}/gallery-source/${encodeURIComponent(photoId)}?kind=${kind}`, {}, { signal, timeout: 120000 });
}

export function prepareEditMask(source: string, image: Blob, signal: AbortSignal, tool: 'edit' | 'extend' = 'edit') {
  const form = new FormData();
  form.append('source', source);
  form.append('image', image);
  return apiPostFormData<{ token: string }>(`${base}/${tool}/mask`, form, { signal, timeout: 120000 });
}

function resultToken(image: string) {
  const url = new URL(image, window.location.origin);
  const prefix = `${base}/media/`;
  if (url.origin !== window.location.origin || !url.pathname.startsWith(prefix)) {
    throw new Error('Invalid workbench output.');
  }
  return url.pathname.slice(prefix.length);
}

export async function openPortraitResult(image: string, signal: AbortSignal) {
  return apiPost<PortraitUpload>(`${base}/result/source`, { result: resultToken(image) }, { signal, timeout: 120000 });
}

export async function savePortraitResult(image: string, albumId: string) {
  return apiPost<{ uploaded: number }>(`${base}/result/save`, { result: resultToken(image), album_id: albumId }, { timeout: 120000 });
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
