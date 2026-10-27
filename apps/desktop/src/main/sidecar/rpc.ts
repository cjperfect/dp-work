import { randomUUID } from "node:crypto";
import type { ChildProcess } from "node:child_process";

import {
  SIDECAR_RPC,
  isRpcMethod,
  type RpcIncomingFrame,
  type SidecarJob,
} from "@dp-work/protocols";
const { control, limits } = SIDECAR_RPC;

type Pending = {
  resolve: (value: unknown) => void;
  reject: (error: Error) => void;
  stream?: ReadableStreamDefaultController<Uint8Array>;
  head: boolean;
  sequence: number;
  bytes: number;
  cleanup: () => void;
};

/** 一个子进程对应一个 RPC 客户端，退出后拒绝全部在途调用。 */
export class SidecarRpc {
  private pending = new Map<string, Pending>();
  private buffer = Buffer.alloc(0);
  private closed = false;

  constructor(private readonly child: ChildProcess) {
    child.stdout?.on("data", (data: Buffer) => this.receive(data));
    child.once("exit", () => this.close());
    child.once("error", () => this.close());
    child.stdin?.on("error", () => this.close());
  }

  private write(message: unknown): void {
    if (this.closed || !this.child.stdin?.writable) throw new Error("Sidecar 管道已关闭。");
    this.child.stdin.write(JSON.stringify(message) + "\n");
  }

  private cancel(id: string): void {
    try {
      this.write({ jsonrpc: "2.0", method: control.cancel, params: { id } });
    } catch {
      /* 进程已经退出。 */
    }
  }

  private fail(id: string, error: Error): void {
    const item = this.pending.get(id);
    if (!item) return;
    this.pending.delete(id);
    item.cleanup();
    item.reject(error);
    try {
      item.stream?.error(error);
    } catch {
      /* 流已关闭。 */
    }
  }

  private start(
    method: string,
    params: unknown,
    signal: AbortSignal,
    streaming: boolean,
  ): Promise<unknown> {
    signal.throwIfAborted();
    if (this.closed) return Promise.reject(new Error("Sidecar 未连接。"));
    if (this.pending.size >= limits.maxPendingRequests)
      return Promise.reject(new Error("Sidecar 请求过多。"));
    const id = randomUUID();
    return new Promise((resolve, reject) => {
      const abort = () => {
        this.cancel(id);
        this.fail(id, new Error("Sidecar 任务已取消或超时。"));
      };
      const item: Pending = {
        resolve,
        reject,
        head: false,
        sequence: 0,
        bytes: 0,
        cleanup: () => signal.removeEventListener("abort", abort),
      };
      if (streaming) {
        const body = new ReadableStream<Uint8Array>({
          start: (controller) => {
            item.stream = controller;
          },
          cancel: abort,
        });
        item.resolve = (head) => {
          const value = head as { status: number; content_type: string };
          resolve(
            new Response([204, 205, 304].includes(value.status) ? null : body, {
              status: value.status,
              headers: { "Content-Type": value.content_type },
            }),
          );
        };
      }
      this.pending.set(id, item);
      signal.addEventListener("abort", abort, { once: true });
      try {
        this.write({ jsonrpc: "2.0", id, method, params });
      } catch (cause) {
        this.fail(id, new Error("Sidecar 请求发送失败。", { cause }));
      }
    });
  }

  health(signal: AbortSignal): Promise<unknown> {
    return this.start(control.health, {}, signal, false);
  }

  request(job: SidecarJob, signal: AbortSignal): Promise<Response> {
    if (!isRpcMethod(job.method)) return Promise.reject(new Error("不支持的 Sidecar 方法。"));
    return this.start(job.method, job.params, signal, true) as Promise<Response>;
  }

  private receive(data: Buffer): void {
    if (this.closed) return;
    this.buffer = Buffer.concat([this.buffer, data]);
    try {
      let end: number;
      while ((end = this.buffer.indexOf(10)) >= 0) {
        if (end > limits.maxOutputLineBytes) throw new Error("Sidecar 响应过大。");
        const line = this.buffer.subarray(0, end);
        this.buffer = this.buffer.subarray(end + 1);
        this.frame(JSON.parse(line.toString("utf8")));
      }
      if (this.buffer.length > limits.maxOutputLineBytes)
        throw new Error("Sidecar 协议缺少消息边界。");
    } catch {
      this.close();
      this.child.kill();
    }
  }

  private frame(message: RpcIncomingFrame): void {
    if (message.jsonrpc !== "2.0") throw new Error("Sidecar 协议无效。");
    const id = message.id ?? message.params?.id;
    if (typeof id !== "string") throw new Error("Sidecar 响应缺少 ID。");
    const item = this.pending.get(id);
    if (!item) return; // 取消后的迟到通知不影响其他请求。
    if (message.error) {
      this.fail(id, new Error("Sidecar 执行失败，请检查日志。"));
      return;
    }
    if (message.method === control.head) {
      const head = message.params!;
      if (
        item.head ||
        !item.stream ||
        !Number.isInteger(head.status) ||
        Number(head.status) < 200 ||
        Number(head.status) > 599 ||
        typeof head.content_type !== "string"
      )
        throw new Error("Sidecar 响应头无效。");
      item.head = true;
      item.resolve(head);
    } else if (message.method === control.chunk) {
      const chunk = message.params!;
      if (
        !item.head ||
        !item.stream ||
        chunk.seq !== item.sequence ||
        typeof chunk.data !== "string" ||
        chunk.data.length > limits.maxEncodedChunkCharacters
      )
        throw new Error("Sidecar 响应分片无效。");
      const bytes = Buffer.from(chunk.data, "base64");
      item.bytes += bytes.length;
      if (item.bytes > limits.maxResponseBytes) {
        this.cancel(id);
        this.fail(id, new Error("Sidecar 响应超过限制。"));
        return;
      }
      item.sequence++;
      item.stream.enqueue(bytes);
    } else if ("result" in message) {
      if (item.stream && !item.head) throw new Error("Sidecar 缺少响应头。");
      this.pending.delete(id);
      item.cleanup();
      if (item.stream) item.stream.close();
      else item.resolve(message.result);
    } else throw new Error("Sidecar 响应类型无效。");
  }

  close(): void {
    if (this.closed) return;
    this.closed = true;
    this.buffer = Buffer.alloc(0);
    for (const id of this.pending.keys())
      this.fail(id, new Error("Sidecar 进程已断开，任务已中断。"));
  }
}
