import { defineConfig } from "cf/config";
import * as entrypoint from "./src/index.ts" with { type: "cf-worker" };

// Puts the Cloud Run service on astro.atharvgogia.in. Deploy from this folder with `cf deploy`.
export default defineConfig({
  worker: {
    name: "astro-toolkit-proxy",
    entrypoint,
    compatibilityDate: "2026-11-01",
    domains: ["astro.atharvgogia.in"],
  },
});
