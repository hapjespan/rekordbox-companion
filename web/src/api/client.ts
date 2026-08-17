import createClient from "openapi-fetch";
import type { paths } from "./generated/schema";

// Typed against the placeholder schema until T015+ land real endpoints;
// regenerate ./generated/schema.d.ts with `pnpm openapi` as they do.
export const apiClient = createClient<paths>({ baseUrl: "http://127.0.0.1:8787" });
