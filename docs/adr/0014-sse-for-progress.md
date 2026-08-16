# Progress streaming via Server-Sent Events

Long-running work (sync sessions up to 1.000 tracks, enrichment runs of
hours) reports progress to the SPA over one Server-Sent Events channel
(`/api/events`); everything else is plain request/response. Considered
alternatives: WebSockets (rejected: nothing flows client-to-server during a
run, so bidirectionality buys complexity and no capability), polling
(rejected: for multi-hour enrichment it either lags or spams, and it turns
progress into extra query endpoints). SSE is one-directional, reconnects
natively in the browser, and costs nothing extra over localhost. Decided in
phase 4, 2026-08-16 (research R4).
