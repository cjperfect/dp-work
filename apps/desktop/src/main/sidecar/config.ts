import { existsSync } from "node:fs";
import path from "node:path";

export type SidecarOptions = {
  command: string;
  args: string[];
  cwd: string;
  port: number;
  logFile: string;
  env?: NodeJS.ProcessEnv;
  startupTimeout?: number;
  healthInterval?: number;
  healthTimeout?: number;
  healthFailures?: number;
  shutdownTimeout?: number;
  restartDelay?: number;
  maxRestarts?: number;
  restartWindow?: number;
};

/** 开发时使用项目虚拟环境，安装版使用内置程序，以 stdio 模式启动。 */
export function sidecarOptions(
  packaged: boolean,
  workspace: string,
  resources: string,
  logs: string,
  env = process.env,
): SidecarOptions | null {
  const enabled = env.DESKTOP_SIDECAR_ENABLED ?? "1";
  if (!["0", "1"].includes(enabled)) throw new Error("DESKTOP_SIDECAR_ENABLED 只能为 0 或 1。");
  if (enabled === "0") return null;
  const rawPort = env.DESKTOP_SIDECAR_PORT ?? "8001";
  const port = Number(rawPort);
  if (!/^\d+$/.test(rawPort) || !Number.isInteger(port) || port < 1024 || port > 65535)
    throw new Error("DESKTOP_SIDECAR_PORT 必须为 1024～65535 的整数。");
  const cwd = path.resolve(
    env.DESKTOP_SIDECAR_ROOT ??
      (packaged ? path.join(resources, "sidecar") : path.join(workspace, "services/sidecar")),
  );
  const executable =
    env.DESKTOP_SIDECAR_EXECUTABLE ??
    (packaged
      ? path.join(
          resources,
          "sidecar",
          process.platform === "win32" ? "dp-work-sidecar.exe" : "dp-work-sidecar",
        )
      : undefined);
  const command = executable
    ? path.resolve(executable)
    : path.resolve(
        env.DESKTOP_SIDECAR_PYTHON ??
          path.join(
            cwd,
            ".venv",
            process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
          ),
      );
  return {
    command,
    args: executable ? ["--stdio"] : ["desktop_entry.py", "--stdio"],
    cwd,
    port,
    logFile: path.join(logs, "sidecar.log"),
    env,
  };
}

/** 启动托管子进程前检查运行环境。 */
export function validateSidecarExecutable(options: SidecarOptions): void {
  if (!existsSync(options.command) || !existsSync(options.cwd))
    throw new Error(
      "找不到 Sidecar 运行环境，请安装 services/sidecar 的 Python 依赖，或配置 DESKTOP_SIDECAR_EXECUTABLE / DESKTOP_SIDECAR_PYTHON。",
    );
}
