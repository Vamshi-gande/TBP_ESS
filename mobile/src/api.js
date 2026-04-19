/**
 * API client for SENTINEL backend.
 * Wraps fetch with JWT auth + JSON helpers.
 */
import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

// Web fallback for SecureStore (not supported on web)
const tokenStorage = {
  async get() {
    if (Platform.OS === 'web') {
      return localStorage.getItem('sentinel_token');
    }
    return SecureStore.getItemAsync('sentinel_token');
  },
  async set(token) {
    if (Platform.OS === 'web') {
      localStorage.setItem('sentinel_token', token);
      return;
    }
    return SecureStore.setItemAsync('sentinel_token', token);
  },
  async remove() {
    if (Platform.OS === 'web') {
      localStorage.removeItem('sentinel_token');
      return;
    }
    return SecureStore.deleteItemAsync('sentinel_token');
  },
};

// Change this to your backend URL
const BASE_URL = 'http://localhost:8000';

let _token = null;

export async function loadToken() {
  _token = await tokenStorage.get();
  return _token;
}

export function getToken() {
  return _token;
}

export async function setToken(token) {
  _token = token;
  await tokenStorage.set(token);
}

export async function clearToken() {
  _token = null;
  await tokenStorage.remove();
}

/**
 * Authenticated fetch wrapper.
 */
async function apiFetch(path, options = {}) {
  const headers = {
    ...(options.headers || {}),
  };

  if (_token) {
    headers['Authorization'] = `Bearer ${_token}`;
  }

  // Don't set Content-Type for FormData
  if (!(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }

  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers,
  });

  if (res.status === 401) {
    await clearToken();
    throw new Error('Session expired');
  }

  if (!res.ok) {
    const body = await res.text();
    throw new Error(body || `HTTP ${res.status}`);
  }

  // 204 No Content
  if (res.status === 204) return null;

  return res.json();
}

// ── Auth ──────────────────────────────────────────────────────────────────

export async function login(username, password) {
  const data = await apiFetch('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  });
  await setToken(data.access_token);
  return data;
}

// ── Sources / Camera ──────────────────────────────────────────────────────

export function getSources() {
  return apiFetch('/sources');
}

export function connectCamera(name, sourceType, uri) {
  return apiFetch('/camera/connect', {
    method: 'POST',
    body: JSON.stringify({ name, source_type: sourceType, uri }),
  });
}

export function deleteSource(id) {
  return apiFetch(`/sources/${id}`, { method: 'DELETE' });
}

export function getStreamUrl(sourceId) {
  return `${BASE_URL}/stream/live/${sourceId}?token=${_token || ''}`;
}

export function getPreviewUrl(sourceId) {
  return `${BASE_URL}/source/frame-preview/${sourceId}`;
}

// ── ROI ───────────────────────────────────────────────────────────────────

export function getROIs(sourceId) {
  return apiFetch(`/roi/list/${sourceId}`);
}

export function saveROI(data) {
  return apiFetch('/roi/save', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export function updateROI(id, data) {
  return apiFetch(`/roi/update/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export function deleteROI(id) {
  return apiFetch(`/roi/${id}`, { method: 'DELETE' });
}

// ── Faces ─────────────────────────────────────────────────────────────────

export function getFaces() {
  return apiFetch('/face/list');
}

export function registerFace(name, imageUri) {
  const form = new FormData();
  form.append('name', name);
  form.append('image', {
    uri: imageUri,
    name: 'face.jpg',
    type: 'image/jpeg',
  });
  return apiFetch('/face/register', {
    method: 'POST',
    body: form,
  });
}

export function deleteFace(id) {
  return apiFetch(`/face/${id}`, { method: 'DELETE' });
}

// ── Alerts ────────────────────────────────────────────────────────────────

export function getAlerts(sourceId = null, limit = 50, offset = 0) {
  let q = `/alerts?limit=${limit}&offset=${offset}`;
  if (sourceId) q += `&source_id=${sourceId}`;
  return apiFetch(q);
}

export function getSnapshotUrl(alertId) {
  return `${BASE_URL}/alerts/${alertId}/snapshot?token=${_token || ''}`;
}

// ── History ───────────────────────────────────────────────────────────────

export function getHistory(sourceId = null, limit = 100) {
  let q = `/history?limit=${limit}`;
  if (sourceId) q += `&source_id=${sourceId}`;
  return apiFetch(q);
}

// ── Settings ──────────────────────────────────────────────────────────────

export function getSettings() {
  return apiFetch('/settings');
}

export function updateSetting(key, value) {
  return apiFetch('/settings/update', {
    method: 'POST',
    body: JSON.stringify({ key, value: String(value) }),
  });
}

// ── Health ────────────────────────────────────────────────────────────────

export function healthCheck() {
  return apiFetch('/health');
}

export { BASE_URL };
