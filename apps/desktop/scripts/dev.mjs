import process from "node:process";
import { spawn } from "node:child_process";
import { setTimeout as delay } from "node:timers/promises";
import electron from "electron";
import { desktopRoot, loadDesktopEnv, spawnPnpm, terminate } from "./runtime.mjs";

loadDesktopEnv();
const url = new URL(process.env.DESKTOP_WEB_URL ?? "http://localhost:3000/");
if (
  url.protocol !== "http:" ||
  !["localhost", "127.0.0.1", "[::1]"].includes(url.hostname) ||
  url.username ||
  url.password
)
  throw new Error("DESKTOP_WEB_URL 只允许本机 HTTP 开发地址。");
let web;
let desktop;
let stopped = false;

async function ready() {
  try {
    const response = await globalThis.fetch(url, { signal: globalThis.AbortSignal.timeout(1500) });
    await response.body?.cancel();
    return response.status < 500;
  } catch {
    return false;
  }
}

function cleanup() {
  stopped = true;
  desktop?.kill();
  terminate(web);
}
process.once("SIGINT", cleanup);
process.once("SIGTERM", cleanup);

try {
  if (!(await ready())) {
    console.info("启动 Web 开发服务…");
    web = spawnPnpm(
      ["--filter", "@dp-work/web", "dev", "--host", url.hostname, "--port", url.port || "80"],
      {
        detached: process.platform !== "win32",
        env: { ...process.env, PORT: url.port || "80" },
      },
    );
    web.once("error", (cause) => {
      console.error(cause);
      cleanup();
    });
    web.once("exit", () => {
      if (!stopped) cleanup();
    });
  } else {
    console.info(`复用现有 Web 服务：${url.origin}`);
  }
  const deadline = Date.now() + 90_000;
  while (!stopped && !(await ready())) {
    if (Date.now() > deadline) throw new Error("等待 Web 服务超时。");
    await delay(300);
  }
  if (!stopped) {
    const env = { ...process.env, DESKTOP_WEB_URL: url.href };
    delete env.ELECTRON_RUN_AS_NODE;
    desktop = spawn(electron, ["."], { cwd: desktopRoot, stdio: "inherit", env });
    desktop.once("error", (cause) => {
      console.error(cause);
      cleanup();
      process.exitCode = 1;
    });
    desktop.once("exit", (code) => {
      cleanup();
      process.exitCode = code ?? 0;
    });
  }
} catch (cause) {
  cleanup();
  throw cause;
}
