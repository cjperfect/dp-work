import process from "node:process";
import path from "node:path";
import { cp, rm, writeFile } from "node:fs/promises";
import { desktopRoot, workspaceRoot, completed, spawnPnpm, loadDesktopEnv } from "./runtime.mjs";

loadDesktopEnv();
await completed(spawnPnpm(["--filter", "@dp-work/web", "build"]));
const web = path.join(workspaceRoot, "apps/web");
const output = path.join(desktopRoot, "build/web");
await rm(output, { recursive: true, force: true });
await cp(path.join(web, "dist"), output, { recursive: true });
const { loadEnv } = await import("vite");
const env = loadEnv("production", web, "");
const apiBaseUrl =
  process.env.DESKTOP_API_BASE_URL ??
  process.env.API_BASE_URL ??
  env.API_BASE_URL ??
  "http://127.0.0.1:8000";
await writeFile(
  path.join(desktopRoot, "build/web-config.json"),
  JSON.stringify({ apiBaseUrl }, null, 2),
);
console.info("桌面 Web 静态资源已准备：apps/desktop/build/web");
