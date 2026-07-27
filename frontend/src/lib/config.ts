/**
 * Client configuration. The PWA is served same-origin by its FastAPI backend and
 * sits behind SSO (Authentik forward-auth) in production; in dev the backend uses a
 * DEV_USER env, so the client sends NOTHING for auth — it just calls `/api/...`
 * same-origin and the session cookie (or the dev fallback) carries identity.
 */
export const API_BASE = '/api';
