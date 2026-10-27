import { createHash, randomUUID } from "node:crypto";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { setTimeout as delay } from "node:timers/promises";
import { apiBaseUrl } from "../config";

import { SIDECAR_RPC, isRpcMethod, type SidecarJob } from "@dp-work/protocols";

export function installationId(file: string): string {
  if (existsSync(file)) {
    const value = readFileSync(file, "utf8").trim();
    if (/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(value))
      return value.toLowerCase();
    throw new Error("本机设备标识文件无效。");
  }
  const value = randomUUID();
  writeFileSync(file, value, { mode: 0o600, flag: "wx" });
  return value;
}

/** Main 主动连接云端，只转发白名单中的本机 Sidecar 调用。 */
export class DeviceBridge {
  private socket: WebSocket | null = null;
  private token: string | null = null;
  private deviceId: string | null = null;
  private tasks = new Map<string, AbortController>();
  private reconnect: ReturnType<typeof setTimeout> | null = null;
  private ping: ReturnType<typeof setInterval> | null = null;
  private attempts = 0;
  private connecting: Promise<void> | null = null;
  private stopped = false;
  private readonly api: string;
  constructor(
    api: string,
    private readonly installation: string,
    private readonly executeLocal: (job: SidecarJob, signal: AbortSignal) => Promise<Response>,
    private readonly onConnected: () => void = () => {},
  ) {
    this.api = apiBaseUrl(api);
  }

  async setSession(token: string | null): Promise<{ deviceId: string | null }> {
    if (this.stopped) return { deviceId: null };
    if (token !== null && (typeof token !== "string" || token.length > 8192))
      throw new Error("登录凭证无效。");
    if (token !== this.token) {
      this.disconnect();
      this.connecting = null;
      this.token = token;
      if (token) {
        const payload = JSON.parse(Buffer.from(token.split(".")[1] ?? "", "base64url").toString());
        if (!/^\d+$/.test(String(payload.sub))) throw new Error("登录凭证无效。");
        const hex = createHash("sha256")
          .update(`${payload.sub}:${this.installation}`)
          .digest("hex")
          .slice(0, 32);
        this.deviceId = `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
      } else this.deviceId = null;
    }
    if (token && (this.connecting || this.socket?.readyState !== WebSocket.OPEN)) {
      if (!this.connecting) {
        const pending = this.connect();
        this.connecting = pending;
        void pending
          .finally(() => {
            if (this.connecting === pending) this.connecting = null;
          })
          .catch(() => {});
      }
      await this.connecting.catch(() => {});
    }
    return { deviceId: token === this.token ? this.deviceId : null };
  }

  private async connect(): Promise<void> {
    if (!this.token || this.stopped) return;
    const token = this.token;
    const url = new URL("/api/devices/connect", this.api);
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(url);
    this.socket = ws;
    await new Promise<void>((resolve, reject) => {
      let ready = false;
      const timeout = setTimeout(() => {
        reject(new Error("设备通道连接超时。"));
        ws.close();
      }, 5000);
      ws.addEventListener("open", () => {
        if (token !== this.token || this.stopped) {
          ws.close();
          return;
        }
        ws.send(JSON.stringify({ type: "auth", token, installation_id: this.installation }));
      });
      ws.addEventListener("message", (event) => {
        try {
          if (typeof event.data !== "string" || event.data.length > 100000)
            throw new Error("设备通道消息无效。");
          const message = JSON.parse(event.data);
          if (token !== this.token || this.stopped) return;
          if (message.type === "connected") {
            if (message.device_id !== this.deviceId) throw new Error("设备身份不匹配。");
            ready = true;
            this.attempts = 0;
            clearTimeout(timeout);
            resolve();
            this.onConnected();
            if (this.ping) clearInterval(this.ping);
            this.ping = setInterval(() => {
              if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "ping" }));
            }, 10000);
          } else if (message.type === "cancel") {
            this.tasks.get(message.id)?.abort();
            this.tasks.delete(message.id);
          } else if (
            message.type === "call" &&
            ready &&
            typeof message.id === "string" &&
            /^[a-f0-9-]{36}$/i.test(message.id)
          ) {
            if (this.tasks.has(message.id)) return;
            if (this.tasks.size >= 4) throw new Error("设备并发任务超限。");
            const controller = new AbortController();
            this.tasks.set(message.id, controller);
            void this.execute(ws, message.id, token, controller).finally(() =>
              this.tasks.delete(message.id),
            );
          } else throw new Error("设备通道消息类型无效。");
        } catch {
          ws.close();
        }
      });
      ws.addEventListener("error", () => {
        clearTimeout(timeout);
        reject(new Error("无法连接云端设备通道。"));
      });
      ws.addEventListener("close", () => {
        clearTimeout(timeout);
        if (this.socket !== ws) return;
        this.socket = null;
        if (this.ping) clearInterval(this.ping);
        this.ping = null;
        for (const task of this.tasks.values()) task.abort();
        if (!ready) reject(new Error("设备通道已断开。"));
        if (!this.stopped && this.token === token) {
          if (this.reconnect) clearTimeout(this.reconnect);
          this.reconnect = setTimeout(
            () => {
              this.reconnect = null;
              void this.setSession(token);
            },
            Math.min(30000, 1000 * 2 ** this.attempts++),
          );
        }
      });
    });
  }

  private async send(ws: WebSocket, value: unknown, signal: AbortSignal): Promise<void> {
    while (ws.bufferedAmount > 1024 * 1024) {
      signal.throwIfAborted();
      await delay(20);
    }
    signal.throwIfAborted();
    if (ws !== this.socket || ws.readyState !== WebSocket.OPEN) throw new Error("设备通道已断开。");
    ws.send(JSON.stringify(value));
  }

  private async execute(
    ws: WebSocket,
    id: string,
    token: string,
    controller: AbortController,
  ): Promise<void> {
    let timer: ReturnType<typeof setTimeout> | undefined;
    try {
      const input = await fetch(new URL(`/api/devices/calls/${id}/input`, this.api), {
        headers: { Authorization: `Bearer ${token}`, "X-Device-ID": this.deviceId! },
        signal: controller.signal,
        redirect: "error",
      });
      if (!input.ok) throw new Error("读取执行任务失败。");
      const envelope = await input.json();
      const job = envelope.data;
      if (
        envelope.code !== 0 ||
        job?.id !== id ||
        !isRpcMethod(job.method) ||
        !job.params ||
        typeof job.params !== "object" ||
        Array.isArray(job.params) ||
        JSON.stringify(job.params).length > SIDECAR_RPC.limits.maxEncodedInputCharacters ||
        typeof job.timeout_seconds !== "number" ||
        job.timeout_seconds <= 0 ||
        job.timeout_seconds > 3600
      )
        throw new Error("执行任务格式无效。");
      timer = setTimeout(() => controller.abort(), job.timeout_seconds * 1000);
      const response = await this.executeLocal(job, controller.signal);
      await this.send(
        ws,
        {
          type: "head",
          id,
          status: response.status,
          content_type: response.headers.get("content-type") ?? "application/octet-stream",
        },
        controller.signal,
      );
      const reader = response.body?.getReader();
      let seq = 0;
      try {
        if (reader)
          while (true) {
            const chunk = await reader.read();
            if (chunk.done) break;
            for (
              let offset = 0;
              offset < chunk.value.length;
              offset += SIDECAR_RPC.limits.chunkBytes
            ) {
              await this.send(
                ws,
                {
                  type: "chunk",
                  id,
                  seq: seq++,
                  data: Buffer.from(
                    chunk.value.subarray(offset, offset + SIDECAR_RPC.limits.chunkBytes),
                  ).toString("base64"),
                },
                controller.signal,
              );
            }
          }
      } finally {
        await reader?.cancel().catch(() => {});
        reader?.releaseLock();
      }
      await this.send(ws, { type: "end", id }, controller.signal);
    } catch {
      if (ws.readyState === WebSocket.OPEN && ws === this.socket)
        ws.send(JSON.stringify({ type: "error", id }));
    } finally {
      if (timer) clearTimeout(timer);
    }
  }

  private disconnect(): void {
    if (this.reconnect) clearTimeout(this.reconnect);
    this.reconnect = null;
    if (this.ping) clearInterval(this.ping);
    this.ping = null;
    const socket = this.socket;
    this.socket = null;
    socket?.close();
    for (const task of this.tasks.values()) task.abort();
    this.tasks.clear();
  }
  stop(): void {
    this.stopped = true;
    this.disconnect();
    this.token = null;
  }
}
