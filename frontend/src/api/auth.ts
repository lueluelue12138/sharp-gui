import type {
  AccessCodeRequest,
  AuthSettingsRequest,
  AuthStatusResponse,
  LoginRequest,
  OwnerBootstrapRequest,
} from '@/types';

import { apiGet, apiPost } from './client';

export async function fetchAuthStatus(): Promise<AuthStatusResponse> {
  return apiGet<AuthStatusResponse>('/api/auth/status');
}

export async function loginWithAccessCode(request: LoginRequest): Promise<AuthStatusResponse> {
  return apiPost<AuthStatusResponse>('/api/auth/login', request);
}

export async function loginWithOwnerToken(request: OwnerBootstrapRequest): Promise<AuthStatusResponse> {
  return apiPost<AuthStatusResponse>('/api/auth/owner-bootstrap', request);
}

export async function logoutAccessSession(): Promise<AuthStatusResponse> {
  return apiPost<AuthStatusResponse>('/api/auth/logout');
}

export async function setAccessCode(request: AccessCodeRequest): Promise<AuthStatusResponse> {
  return apiPost<AuthStatusResponse>('/api/auth/access-code', request);
}

export async function revokeAccessSessions(): Promise<AuthStatusResponse> {
  return apiPost<AuthStatusResponse>('/api/auth/revoke');
}

export async function updateAuthSettings(request: AuthSettingsRequest): Promise<AuthStatusResponse> {
  return apiPost<AuthStatusResponse>('/api/auth/settings', request);
}
