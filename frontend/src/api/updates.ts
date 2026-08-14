import { apiGet, apiPost } from '@/api/client';
import type {
  UpdateApplyRequest,
  UpdateChannel,
  UpdateCheckRequest,
  UpdateOperation,
  UpdateStatusResponse,
} from '@/types';

// Mirrors ACTIVE_PHASES in backend/services/self_update.py. The backend only
// ever reports these plus the terminal `completed` / `failed` phases.
const ACTIVE_UPDATE_PHASES = new Set([
  'queued',
  'waiting_for_server',
  'fetching',
  'applying',
  'verifying',
  'rolling_back',
  'restarting',
]);

const DEFAULT_STATUS_TIMEOUT_MS = 2500;

export const UPDATE_POLL_INTERVAL_MS = 1000;
// The server-side worst case is a 180s fetch plus verification (bytecode
// compilation and an import subprocess) plus a 60s restart health wait, so the
// client budget has to stay comfortably above the sum.
export const UPDATE_POLL_TIMEOUT_MS = 600000;

interface FetchUpdateStatusOptions {
  cacheBust?: boolean;
  signal?: AbortSignal;
  timeout?: number;
}

interface PollUpdateStatusOptions {
  initialStatus: UpdateStatusResponse;
  signal?: AbortSignal;
  intervalMs?: number;
  timeoutMs?: number;
  onStatus?: (status: UpdateStatusResponse) => void;
  onTransientError?: (error: unknown) => void;
  shouldStop?: (status: UpdateStatusResponse) => boolean;
}

function abortError(): DOMException {
  return new DOMException('Update polling was aborted', 'AbortError');
}

function delay(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(abortError());
      return;
    }

    const timeoutId = window.setTimeout(() => {
      signal?.removeEventListener('abort', handleAbort);
      resolve();
    }, ms);
    function handleAbort() {
      window.clearTimeout(timeoutId);
      reject(abortError());
    }
    signal?.addEventListener('abort', handleAbort, { once: true });
  });
}

export function isActiveUpdateOperation(operation?: UpdateOperation | null): boolean {
  if (!operation?.id || !operation.phase) {
    return false;
  }
  return ACTIVE_UPDATE_PHASES.has(operation.phase.trim().toLowerCase());
}

export function getExpectedUpdateCommit(operation?: UpdateOperation | null): string | null {
  return operation?.target_sha ?? null;
}

export async function fetchUpdateStatus(
  options: FetchUpdateStatusOptions = {},
): Promise<UpdateStatusResponse> {
  const query = options.cacheBust ? `?poll=${Date.now()}` : '';
  return apiGet<UpdateStatusResponse>(`/api/updates/status${query}`, {
    cache: 'no-store',
    signal: options.signal,
    timeout: options.timeout ?? DEFAULT_STATUS_TIMEOUT_MS,
  });
}

export async function checkForUpdates(channel: UpdateChannel): Promise<UpdateStatusResponse> {
  const request: UpdateCheckRequest = { channel };
  return apiPost<UpdateStatusResponse>('/api/updates/check', request);
}

export async function applyUpdate(request: UpdateApplyRequest): Promise<UpdateStatusResponse> {
  return apiPost<UpdateStatusResponse>('/api/updates/apply', request);
}

export async function pollUpdateStatus({
  initialStatus,
  signal,
  intervalMs = UPDATE_POLL_INTERVAL_MS,
  timeoutMs = UPDATE_POLL_TIMEOUT_MS,
  onStatus,
  onTransientError,
  shouldStop = (status) => !isActiveUpdateOperation(status.operation),
}: PollUpdateStatusOptions): Promise<UpdateStatusResponse> {
  let latestStatus = initialStatus;
  const deadline = Date.now() + timeoutMs;

  while (Date.now() < deadline) {
    if (signal?.aborted) {
      throw abortError();
    }

    try {
      latestStatus = await fetchUpdateStatus({
        cacheBust: true,
        signal,
        timeout: DEFAULT_STATUS_TIMEOUT_MS,
      });
      onStatus?.(latestStatus);
      if (shouldStop(latestStatus)) {
        return latestStatus;
      }
    } catch (error) {
      if (signal?.aborted) {
        throw abortError();
      }
      onTransientError?.(error);
    }

    await delay(intervalMs, signal);
  }

  throw new Error('Update status polling timed out');
}
