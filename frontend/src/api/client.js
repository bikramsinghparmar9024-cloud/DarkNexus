import axios from 'axios';

/*
 * API client.
 *
 * Two things changed here. The timeout was 4 seconds, chosen for "fast offline
 * fallback" - it existed so pages could give up quickly and render fabricated
 * demo data. Real requests against a scraping backend legitimately take longer
 * than that, so a slow-but-working call looked like an outage.
 *
 * And every endpoint now requires authentication, so a 401 has to be handled:
 * the refresh token is exchanged once, and if that fails the session is ended
 * rather than leaving the UI in a half-signed-in state.
 */

// Where the API lives.
//
// In development the interface runs on Vite's port and the backend on its
// own, so an absolute URL is needed. In the container image the two are
// served from one origin behind nginx, and the correct base is *empty* -
// requests go to the same host and the proxy forwards /api and /ws.
//
// The check is against `undefined` rather than falsiness on purpose: an empty
// string is the meaningful "same origin" value, and `|| default` would
// discard it and send every request to 127.0.0.1:8000 - the user's own
// machine, where nothing is listening.
const CONFIGURED_BASE = import.meta.env?.VITE_API_BASE_URL;
export const API_BASE_URL =
  CONFIGURED_BASE === undefined || CONFIGURED_BASE === null
    ? 'http://127.0.0.1:8000'
    : CONFIGURED_BASE.replace(/\/+$/, '');

// Same-origin needs a readable name in error messages.
const API_LABEL = API_BASE_URL || 'this server';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

// Set by AuthContext so the client can end a session it cannot rescue.
let onSessionExpired = null;
export function setSessionExpiredHandler(handler) {
  onSessionExpired = handler;
}

apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  // A file upload must not carry the client's default JSON content type.
  // The browser sets `multipart/form-data` together with the boundary that
  // separates the parts, and it can only do that if nothing has already set
  // the header - the default above overrode it, so the server received a
  // multipart body labelled as JSON and rejected it before reading the file.
  if (typeof FormData !== 'undefined' && config.data instanceof FormData) {
    delete config.headers['Content-Type'];
    delete config.headers['content-type'];
  }

  return config;
});

// A single in-flight refresh, shared by every request that hits 401 at once.
// Without this, ten concurrent calls would trigger ten refreshes and the later
// ones would fail against an already-rotated token.
let refreshInFlight = null;

async function refreshAccessToken() {
  const refreshToken = localStorage.getItem('refresh_token');
  if (!refreshToken) return null;

  if (!refreshInFlight) {
    refreshInFlight = axios
      .post(`${API_BASE_URL}/api/auth/refresh`, null, {
        headers: { Authorization: `Bearer ${refreshToken}` },
        timeout: 15000,
      })
      .then((res) => {
        const { access_token, refresh_token } = res.data;
        localStorage.setItem('access_token', access_token);
        if (refresh_token) localStorage.setItem('refresh_token', refresh_token);
        return access_token;
      })
      .catch(() => null)
      .finally(() => { refreshInFlight = null; });
  }

  return refreshInFlight;
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config || {};
    const status = error.response?.status;

    // Never attempt a refresh for the endpoints that establish a session;
    // a 401 from those means the credentials were wrong.
    const isAuthEndpoint = (original.url || '').includes('/api/auth/login')
      || (original.url || '').includes('/api/auth/refresh');

    if (status === 401 && !original._retried && !isAuthEndpoint) {
      original._retried = true;
      const token = await refreshAccessToken();
      if (token) {
        original.headers = { ...(original.headers || {}), Authorization: `Bearer ${token}` };
        return apiClient(original);
      }
      if (onSessionExpired) onSessionExpired();
    }

    return Promise.reject(error);
  },
);

/**
 * Turn an axios failure into something worth showing a user.
 *
 * Pages used to swallow errors and substitute demo data, so an outage, an
 * expired session and an empty database were indistinguishable on screen.
 */
export function describeApiError(error) {
  if (error?.code === 'ECONNABORTED') {
    return { kind: 'timeout', message: 'The request timed out. The backend may be busy or unreachable.' };
  }
  if (!error?.response) {
    return {
      kind: 'offline',
      message: `Cannot reach the backend at ${API_LABEL}. Check that it is running.`,
    };
  }
  const { status, data } = error.response;
  const detail = typeof data?.detail === 'string' ? data.detail : null;

  if (status === 401) return { kind: 'unauthenticated', message: detail || 'Your session has expired. Sign in again.' };
  if (status === 403) return { kind: 'forbidden', message: detail || 'Your role does not permit this action.' };
  if (status === 404) return { kind: 'not_found', message: detail || 'Not found.' };
  if (status === 429) return { kind: 'rate_limited', message: detail || 'Too many attempts. Try again shortly.' };
  if (status >= 500) return { kind: 'server_error', message: detail || 'The backend failed to process this request.' };
  return { kind: 'error', message: detail || `Request failed (HTTP ${status}).` };
}

// Real-time intelligence feed.
export function createWebSocket(onMessage) {
  try {
    // With a same-origin base there is no scheme to rewrite, so the socket
    // URL is built from the page's own location instead.
    const wsUrl = API_BASE_URL
      ? API_BASE_URL.replace(/^http/, 'ws') + '/ws'
      : `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws`;
    const ws = new WebSocket(wsUrl);

    ws.onmessage = (event) => {
      try {
        onMessage(JSON.parse(event.data));
      } catch (e) {
        console.error('[WebSocket] Malformed message:', e);
      }
    };
    ws.onerror = () => console.warn('[WebSocket] Stream unavailable');
    return ws;
  } catch (e) {
    console.warn('[WebSocket] Could not connect:', e);
    return { close: () => {}, send: () => {} };
  }
}
