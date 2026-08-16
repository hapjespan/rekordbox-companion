# Frontend client generated from the OpenAPI export

The FastAPI OpenAPI export is the schema of record for the engine/SPA seam
(project rule 4); the TypeScript client is generated with `openapi-typescript`
(types) plus `openapi-fetch` (runtime) via `pnpm openapi`, and is never edited
by hand. Considered alternatives: orval (rejected: generates TanStack Query
hooks that would fight the hand-wired Query/Zustand split, and is a heavier
dependency), a hand-written fetch layer (rejected: schema drift is exactly
what rule 4 exists to prevent). Contract tests pin the guard refusal codes of
the two apply endpoints, because those codes encode constitution Principle II
at this seam. Decided in phase 4, 2026-08-16 (research R5).
