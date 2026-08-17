// Placeholder until the backend's OpenAPI schema exists (T015, GET
// /api/health, is the first endpoint). Regenerate with `pnpm openapi` once
// the engine is running, then commit the result — this file is checked in,
// not gitignored, per project rule 4 (API changes start in the schema; the
// generated client is regenerated and re-committed, never hand-edited past
// this point).

// Empty interface (not `Record<string, never>`) on purpose: openapi-fetch's
// `PathsWithMethod` resolves an empty interface to `never`, so every
// `apiClient.GET(...)` call is a compile error until the real schema lands.
// `Record<string, never>` would silently accept any path string instead
// (standards-review finding).
export interface paths {}

export interface components {
  schemas: Record<string, never>;
}
