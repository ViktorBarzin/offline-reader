// SPA mode: render entirely on the client (adapter-static fallback: index.html).
// The Reader reads captures from IndexedDB, so nothing here may be prerendered or
// server-rendered.
export const ssr = false;
export const prerender = false;
