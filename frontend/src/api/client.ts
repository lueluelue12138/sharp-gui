/**
 * Base API client with error handling
 */

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public data?: ApiErrorData | null
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export interface ApiErrorData {
  error?: string;
  code?: string;
  [key: string]: unknown;
}

interface FetchOptions extends RequestInit {
  timeout?: number;
}

interface UploadProgress {
  loaded: number;
  total: number | null;
  percent: number;
  lengthComputable: boolean;
}

interface FormDataUploadOptions {
  headers?: HeadersInit;
  timeout?: number;
  onUploadProgress?: (progress: UploadProgress) => void;
}

async function fetchWithTimeout(
  url: string,
  options: FetchOptions = {}
): Promise<Response> {
  const { timeout = 30000, signal: externalSignal, ...fetchOptions } = options;

  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeout);
  const forwardAbort = () => controller.abort();

  if (externalSignal?.aborted) {
    controller.abort();
  } else {
    externalSignal?.addEventListener('abort', forwardAbort, { once: true });
  }

  try {
    const response = await fetch(url, {
      credentials: fetchOptions.credentials ?? 'same-origin',
      ...fetchOptions,
      signal: controller.signal,
    });
    return response;
  } finally {
    clearTimeout(id);
    externalSignal?.removeEventListener('abort', forwardAbort);
  }
}

async function readErrorData(response: Response): Promise<ApiErrorData | null> {
  const errorData = await response.json().catch(() => null);
  return errorData && typeof errorData === 'object' ? errorData as ApiErrorData : null;
}

async function throwApiError(response: Response): Promise<never> {
  const errorData = await readErrorData(response);
  throw new ApiError(
    errorData?.error || `HTTP error! status: ${response.status}`,
    response.status,
    errorData
  );
}

export async function apiGet<T>(url: string, options?: FetchOptions): Promise<T> {
  const response = await fetchWithTimeout(url, options);
  
  if (!response.ok) {
    await throwApiError(response);
  }
  
  return response.json();
}

export async function apiPost<T>(
  url: string,
  data?: unknown,
  options?: RequestInit & { timeout?: number }
): Promise<T> {
  const response = await fetchWithTimeout(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
    body: data ? JSON.stringify(data) : undefined,
    ...options,
  });
  
  if (!response.ok) {
    await throwApiError(response);
  }
  
  return response.json();
}

export async function apiPostBlob(
  url: string,
  data?: unknown,
  options?: RequestInit & { timeout?: number }
): Promise<{ blob: Blob; response: Response }> {
  const { headers, ...restOptions } = options ?? {};
  const response = await fetchWithTimeout(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...headers,
    },
    body: data ? JSON.stringify(data) : undefined,
    ...restOptions,
  });

  if (!response.ok) {
    await throwApiError(response);
  }

  return {
    blob: await response.blob(),
    response,
  };
}

export async function apiPostFormData<T>(
  url: string,
  formData: FormData,
  options?: RequestInit & { timeout?: number }
): Promise<T> {
  const { headers, ...restOptions } = options ?? {};
  const response = await fetchWithTimeout(url, {
    method: 'POST',
    body: formData,
    headers,
    ...restOptions,
  });
  
  if (!response.ok) {
    await throwApiError(response);
  }
  
  return response.json();
}

export async function apiPostFormDataWithProgress<T>(
  url: string,
  formData: FormData,
  options: FormDataUploadOptions = {}
): Promise<T> {
  const { headers, timeout = 30000, onUploadProgress } = options;

  return new Promise<T>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', url, true);
    xhr.timeout = timeout;
    xhr.withCredentials = true;

    if (headers) {
      const normalizedHeaders = new Headers(headers);
      normalizedHeaders.forEach((value, key) => {
        xhr.setRequestHeader(key, value);
      });
    }

    xhr.upload.onprogress = (event) => {
      if (!onUploadProgress) {
        return;
      }
      const total = event.lengthComputable ? event.total : null;
      const percent = total ? Math.min(100, Math.max(0, (event.loaded / total) * 100)) : 0;
      onUploadProgress({
        loaded: event.loaded,
        total,
        percent,
        lengthComputable: event.lengthComputable,
      });
    };

    xhr.onload = () => {
      const rawText = xhr.responseText || '';
      let data: T | ApiErrorData | null = null;
      try {
        data = rawText ? JSON.parse(rawText) as T : ({} as T);
      } catch {
        data = null;
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        onUploadProgress?.({
          loaded: 1,
          total: 1,
          percent: 100,
          lengthComputable: true,
        });
        resolve((data ?? {}) as T);
        return;
      }
      const errorData = data && typeof data === 'object' ? data as ApiErrorData : null;
      reject(new ApiError(
        errorData?.error || `HTTP error! status: ${xhr.status}`,
        xhr.status,
        errorData,
      ));
    };

    xhr.onerror = () => reject(new ApiError('Network request failed', 0, null));
    xhr.ontimeout = () => reject(new ApiError('Request timed out', 0, null));
    xhr.onabort = () => reject(new ApiError('Request aborted', 0, null));

    xhr.send(formData);
  });
}

export async function apiDelete<T>(url: string): Promise<T> {
  const response = await fetchWithTimeout(url, {
    method: 'DELETE',
  });
  
  if (!response.ok) {
    await throwApiError(response);
  }
  
  return response.json();
}
