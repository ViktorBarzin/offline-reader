/**
 * Client configuration. The PWA is served same-origin by its FastAPI backend and
 * sits behind SSO (Authentik forward-auth) in production; in dev the backend uses a
 * DEV_USER env, so the client sends NOTHING for auth — it just calls `/api/...`
 * same-origin and the session cookie (or the dev fallback) carries identity.
 */
export const API_BASE = '/api';

/**
 * Where the "Sign in" link goes when the SSO session has lapsed. It is a full
 * navigation under /api, so the service worker sends it to the network (every
 * other navigation is answered from the precache) and forward-auth bounces it to
 * Authentik; once signed in, the backend redirects back to the app.
 */
export const SIGNIN_URL = `${API_BASE}/signin`;
