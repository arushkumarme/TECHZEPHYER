/// <reference types="vitest/config" />
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// The dashboard is a separate app (decision CD-3). In development it proxies /api to the
// FastAPI backend started with `uv run fastapi dev` (port 8000).
// On Vercel (which sets VERCEL during builds) vercel.json mounts it at /dashboard/. A Vercel
// service looks files up by the full request path, so the files must also sit in
// dist/dashboard/. Everywhere else, including NETCOOP_DASHBOARD_DIST and the UI tests, it is
// served from /.
export default defineConfig(({ mode }) => {
  const onVercel = Boolean(loadEnv(mode, ".", "VERCEL").VERCEL);
  return {
    base: onVercel ? "/dashboard/" : "/",
    build: { outDir: onVercel ? "dist/dashboard" : "dist" },
    plugins: [react()],
    server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8000" } },
    test: { environment: "jsdom", setupFiles: ["./src/test-setup.ts"] },
  };
});
