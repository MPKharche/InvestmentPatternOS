/**
 * Shared E2E helpers — same-origin API via Next rewrite (/api/v1 → backend).
 */
export const UI_BASE = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";
export const API_BASE =
  process.env.E2E_API_BASE ?? `${UI_BASE.replace(/\/$/, "")}/api/v1`;
