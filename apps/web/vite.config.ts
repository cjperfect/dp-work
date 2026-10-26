import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import { TanStackRouterVite } from "@tanstack/router-plugin/vite";
import path from "node:path";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, import.meta.dirname, "");
  const apiBase = process.env.API_BASE_URL ?? env.API_BASE_URL ?? "http://127.0.0.1:8000";
  const target = new URL(apiBase);
  const local = ["localhost", "127.0.0.1", "[::1]"].includes(target.hostname);
  if (
    target.username ||
    target.password ||
    (target.protocol !== "https:" && !(target.protocol === "http:" && local))
  )
    throw new Error("API_BASE_URL 必须使用 HTTPS；本机回环地址允许 HTTP。");
  const proxy = { "/api": { target: apiBase, changeOrigin: true, ws: true } };
  return {
    plugins: [
      TanStackRouterVite({
        routesDirectory: "./src/routes",
        generatedRouteTree: "./src/routeTree.gen.ts",
        autoCodeSplitting: false,
      }),
      react(),
    ],
    resolve: {
      dedupe: ["yjs", "y-protocols", "y-prosemirror"],
      alias: { "@": path.resolve(import.meta.dirname, "src") },
    },
    server: { port: Number(process.env.PORT ?? 3000), strictPort: true, proxy },
    preview: { proxy },
    build: { target: "es2022" },
  };
});
