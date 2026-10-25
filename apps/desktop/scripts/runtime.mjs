import process from "node:process";
import { spawn, execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const desktopRoot = fileURLToPath(new URL("../", import.meta.url));
export const workspaceRoot = path.resolve(desktopRoot, "../..");

export function loadDesktopEnv() {
  const file = path.join(desktopRoot, ".env");
  if (existsSync(file)) process.loadEnvFile(file);
}

export function spawnPnpm(args, options = {}) {
  const cli = process.env.npm_execpath;
  if (!cli) throw new Error("请通过 pnpm 运行桌面端命令。");
  return spawn(process.execPath, [cli, ...args], {
    cwd: workspaceRoot,
    stdio: "inherit",
    ...options,
  });
}

export async function completed(child) {
  return new Promise((resolve, reject) => {
    child.once("error", reject);
    child.once("exit", (code, signal) => {
      if (code === 0) resolve();
      else reject(new Error(`子进程退出：${code ?? signal}`));
    });
  });
}

export function terminate(child) {
  if (!child?.pid || child.exitCode !== null) return;
  try {
    if (process.platform === "win32")
      execFileSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore" });
    else process.kill(-child.pid, "SIGTERM");
  } catch {
    child.kill();
  }
}
