import createClient from "openapi-fetch";
import type { paths } from "./generated/schema";

// Relative baseUrl, not an absolute http://127.0.0.1:8787: in production
// the SPA is served BY the FastAPI app itself (main.py's StaticFiles
// mount), same origin as the API, so a relative URL just works. In dev
// (`pnpm dev`, port 5173) it works too, via vite.config.ts's `/api` proxy
// to 127.0.0.1:8787 -- without that proxy, an absolute cross-origin URL
// would hit the backend's missing CORS headers (found while manually
// smoke-testing T031/T032/T102 in a browser).
export const apiClient = createClient<paths>({ baseUrl: "" });
