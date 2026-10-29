import { spawn, execFile, execFileSync, type ChildProcess } from "node:child_process";
import { randomUUID } from "node:crypto";
import { createWriteStream, mkdirSync, type WriteStream } from "node:fs";
import path from "node:path";
import net from "node:net";
import { setTimeout as delay } from "node:timers/promises";
import { SidecarRpc } from "./rpc";
import { validateSidecarExecutable, type SidecarOptions } from "./config";

import type { RpcHealth as Health, SidecarJob } from "@dp-work/protocols";

/** Electron 通过管道管理自己创建的 Sidecar 进程组。 */
export class SidecarManager {
  private child: ChildProcess | null = null;
  private log: WriteStream | null = null;
  private instance = "";
  private stopped = false;
  private rpc: SidecarRpc | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private checking: Promise<void> | null = null;
  private starting: Promise<void> | null = null;
  private stopping: Promise<void> | null = null;
  private terminating: Promise<void> | null = null;
  private abort = new AbortController();
  private failures = 0;
  private restarts: number[] = [];

  constructor(
    private readonly options: SidecarOptions,
    private readonly onFailure: (error: Error) => void = console.error,
  ) {}

  get state() {
    return {
      mode: this.stopped ? "stopped" : "managed",
      pid: this.child?.pid ?? null,
      restarts: this.restarts.length,
    };
  }

  /** 检查是否存在阻止更新安装的本地转写任务。 */
  async assertIdleForUpdate(): Promise<void> {
    if (!this.rpc || this.stopped) throw new Error("本机服务未就绪。");
    const state = (await this.rpc.health(AbortSignal.timeout(3000))) as {
      ok?: boolean;
      active_asr_sessions?: number;
    };
    if (!state.ok || state.active_asr_sessions !== 0) throw new Error("请先结束会议转写。");
  }

  /** 启动子进程，并等待正确的 RPC 健康回执。 */
  start(): Promise<void> {
    if (this.stopped) return Promise.reject(new Error("Sidecar 管理器已停止。"));
    this.starting ??= this.initialize();
    return this.starting;
  }

  private async health(): Promise<Health | null> {
    try {
      if (!this.rpc) return null;
      const body = (await this.rpc.health(
        AbortSignal.any([
          this.abort.signal,
          AbortSignal.timeout(this.options.healthTimeout ?? 1500),
        ]),
      )) as Partial<Health>;
      return body.ok === true && body.service === "dp-work-sidecar" ? (body as Health) : null;
    } catch {
      return null;
    }
  }

  /** 普通业务通过当前子进程管道执行，进程重启后不重放旧调用。 */
  request(job: SidecarJob, signal: AbortSignal): Promise<Response> {
    if (!this.rpc || this.stopped) return Promise.reject(new Error("Sidecar 未连接。"));
    return this.rpc.request(job, signal);
  }

  private async occupied(): Promise<boolean> {
    return new Promise((resolve) => {
      const socket = net.connect({ host: "127.0.0.1", port: this.options.port });
      const done = (open: boolean) => {
        socket.destroy();
        resolve(open);
      };
      socket.once("connect", () => done(true));
      socket.once("error", () => done(false));
      socket.setTimeout(1000, () => done(true));
    });
  }

  private async initialize(): Promise<void> {
    if (await this.occupied())
      throw new Error(`Sidecar ASR 端口 ${this.options.port} 已被占用，请关闭手动服务后重试。`);
    if (this.stopped) return;
    try {
      await this.launch();
    } catch (cause) {
      await this.terminate();
      throw cause;
    }
    this.schedule();
  }

  private async launch(): Promise<void> {
    if (this.stopped) return;
    validateSidecarExecutable(this.options);
    this.instance = randomUUID();
    mkdirSync(path.dirname(this.options.logFile), { recursive: true, mode: 0o700 });
    this.log = createWriteStream(this.options.logFile, { flags: "a", mode: 0o600 });
    this.log.on("error", () => {
      if (!this.stopped) this.onFailure(new Error("Sidecar 日志写入失败。"));
    });
    const child = spawn(this.options.command, this.options.args, {
      cwd: this.options.cwd,
      env: {
        ...process.env,
        ...this.options.env,
        PYTHONUNBUFFERED: "1",
        PORT: String(this.options.port),
        DP_SIDECAR_INSTANCE_ID: this.instance,
        DP_SIDECAR_PARENT_PID: String(process.pid),
      },
      stdio: ["pipe", "pipe", "pipe"],
      detached: process.platform !== "win32",
      windowsHide: true,
    });
    this.child = child;
    let spawnError: Error | undefined;
    child.once("error", (cause) => {
      spawnError = cause;
    });
    this.rpc = new SidecarRpc(child);
    child.stderr?.pipe(this.log, { end: false });
    child.once("exit", () => {
      if (!this.stopped) this.schedule(0);
    });
    const deadline = Date.now() + (this.options.startupTimeout ?? 60_000);
    while (!this.stopped && Date.now() < deadline) {
      if (spawnError)
        throw new Error("Sidecar 进程启动失败，请检查运行程序和日志。", { cause: spawnError });
      if (child.exitCode !== null || child.signalCode !== null)
        throw new Error("Sidecar 在就绪前退出，请检查 sidecar.log。");
      const health = await this.health();
      if (health?.instance_id === this.instance) {
        this.failures = 0;
        return;
      }
      await delay(200, undefined, { signal: this.abort.signal });
    }
    if (!this.stopped) throw new Error("等待 Sidecar 健康检查超时，请检查 sidecar.log。");
  }

  private schedule(ms = this.options.healthInterval ?? 5000): void {
    if (this.stopped) return;
    if (this.timer) clearTimeout(this.timer);
    this.timer = setTimeout(() => {
      this.timer = null;
      if (this.checking) return;
      this.checking = this.check().finally(() => {
        this.checking = null;
        this.schedule();
      });
    }, ms);
    this.timer.unref();
  }

  private async check(): Promise<void> {
    try {
      const health = await this.health();
      if (this.stopped) return;
      const exited = !this.child || this.child.exitCode !== null || this.child.signalCode !== null;
      if (!exited && health?.instance_id === this.instance) {
        this.failures = 0;
        return;
      }
      if (!exited && ++this.failures < (this.options.healthFailures ?? 3)) return;
      const now = Date.now();
      this.restarts = this.restarts.filter(
        (time) => now - time < (this.options.restartWindow ?? 60_000),
      );
      if (this.restarts.length >= (this.options.maxRestarts ?? 5)) {
        await this.stop();
        this.onFailure(new Error("Sidecar 连续重启失败，已停止自动重试，请查看 sidecar.log。"));
        return;
      }
      this.restarts.push(now);
      await this.terminate();
      await delay(
        Math.min(30_000, (this.options.restartDelay ?? 1000) * 2 ** (this.restarts.length - 1)),
        undefined,
        { signal: this.abort.signal },
      );
      if (!this.stopped && (await this.occupied()))
        throw new Error("Sidecar 重启端口被其他进程占用，未终止该进程。");
      await this.launch();
    } catch (cause) {
      if (!this.stopped) {
        await this.terminate();
        // 后续检查继续受重启次数及退避限制，不无限快速重试。
        if (cause instanceof Error) console.warn(cause.message);
      }
    }
  }

  private groupAlive(pid: number): boolean {
    try {
      process.kill(process.platform === "win32" ? pid : -pid, 0);
      return true;
    } catch {
      return false;
    }
  }

  private terminate(): Promise<void> {
    this.terminating ??= this.terminateChild().finally(() => {
      this.terminating = null;
    });
    return this.terminating;
  }

  private async terminateChild(): Promise<void> {
    const child = this.child;
    this.rpc?.close();
    this.rpc = null;
    this.child = null;
    const log = this.log;
    this.log = null;
    if (child?.pid) {
      const pid = child.pid;
      if (process.platform === "win32") {
        await new Promise<void>((resolve) => {
          execFile(
            "taskkill",
            ["/pid", String(pid), "/T", "/F"],
            {
              windowsHide: true,
              timeout: this.options.shutdownTimeout ?? 5000,
            },
            () => resolve(),
          );
        });
      } else {
        try {
          process.kill(-pid, "SIGTERM");
        } catch {
          /* 已退出。 */
        }
        const deadline = Date.now() + (this.options.shutdownTimeout ?? 5000);
        while (this.groupAlive(pid) && Date.now() < deadline) await delay(40);
        if (this.groupAlive(pid)) {
          try {
            process.kill(-pid, "SIGKILL");
          } catch {
            /* 已退出。 */
          }
        }
      }
      child.stdout?.unpipe(log ?? undefined);
      child.stderr?.unpipe(log ?? undefined);
    }
    log?.end();
  }

  /** Electron 正常退出时有界等待，停止后不会再次拉起进程。 */
  stop(): Promise<void> {
    if (this.stopping) return this.stopping;
    this.stopped = true;
    this.abort.abort();
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    this.stopping = this.terminate();
    return this.stopping;
  }

  /** Node 退出钩子无法等待 Promise，兜底同步终止自己创建的进程组。 */
  forceStop(): void {
    this.stopped = true;
    if (!this.child?.pid) return;
    if (process.platform === "win32") {
      try {
        execFileSync("taskkill", ["/pid", String(this.child.pid), "/T", "/F"], {
          windowsHide: true,
          stdio: "ignore",
          timeout: 1000,
        });
      } catch {
        this.child.kill();
      }
    } else {
      try {
        process.kill(-this.child.pid, "SIGKILL");
      } catch {
        /* 已退出。 */
      }
    }
  }
}
