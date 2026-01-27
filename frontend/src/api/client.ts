/**
 * Base API client with error handling
 */

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public data?: unknown
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

interface FetchOptions extends RequestInit {
  timeout?: number;
}

async function fetchWithTimeout(
  url: string,
  options: FetchOptions = {}
): Promise<Response> {
  const { timeout = 30000, ...fetchOptions } = options;

  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeout);

  try {
    const response = await fetch(url, {
      ...fetchOptions,
      signal: controller.signal,
    });
    return response;
  } finally {
    clearTimeout(id);
  }
}

export async function apiGet<T>(url: string): Promise<T> {
  const response = await fetchWithTimeout(url);
  
  if (!response.ok) {
    throw new ApiError(
      `HTTP error! status: ${response.status}`,
      response.status
    );
  }
  
  return response.json();
}

export async function apiPost<T>(
  url: string,
  data?: unknown,
  options?: RequestInit
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
    const errorData = await response.json().catch(() => null);
    throw new ApiError(
      errorData?.error || `HTTP error! status: ${response.status}`,
      response.status,
      errorData
    );
  }
  
  return response.json();
}

export async function apiPostFormData<T>(
  url: string,
  formData: FormData
): Promise<T> {
  const response = await fetchWithTimeout(url, {
    method: 'POST',
    body: formData,
  });
  
  if (!response.ok) {
    const errorData = await response.json().catch(() => null);
    throw new ApiError(
      errorData?.error || `HTTP error! status: ${response.status}`,
      response.status,
      errorData
    );
  }
  
  return response.json();
}

export async function apiDelete<T>(url: string): Promise<T> {
  const response = await fetchWithTimeout(url, {
    method: 'DELETE',
  });
  
  if (!response.ok) {
    const errorData = await response.json().catch(() => null);
    throw new ApiError(
      errorData?.error || `HTTP error! status: ${response.status}`,
      response.status,
      errorData
    );
  }
  
  return response.json();
}
