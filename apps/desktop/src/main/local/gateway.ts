import type {
  LocalRequest,
  LocalResponseChunk,
  LocalResponseHead,
} from "@dp-work/protocols/desktop";
import { isRpcMethod, type SidecarJob } from "@dp-work/protocols";
import { routeLocal } from "./routes";

type Identity = { owner: number; deviceId: string };
export class LocalGateway {
  get hasActiveRequests(): boolean {
    return this.calls.size > 0;
  }
  private calls = new Map<string, AbortController>();
  private owner: number | null = null;
  constructor(
    private execute: (job: SidecarJob, signal: AbortSignal) => Promise<Response>,
    private identity: (token: string) => Promise<Identity>,
    private api: () => string,
    private emit: (chunk: LocalResponseChunk) => void,
  ) {}
  cancel(id: string): void {
    this.calls.get(id)?.abort();
  }
  cancelAll(): void {
    for (const controller of this.calls.values()) controller.abort();
  }
  private async rpc(
    method: string,
    params: Record<string, unknown>,
    signal: AbortSignal,
  ): Promise<Response> {
    if (!isRpcMethod(method)) throw new Error("不支持的本地方法。");
    return this.execute({ method, params }, signal);
  }
  private async json(method: string, params: Record<string, unknown>, signal: AbortSignal) {
    const response = await this.rpc(method, params, signal);
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail?.message || "本地服务请求失败。");
    return data;
  }
  async open(input: LocalRequest): Promise<LocalResponseHead> {
    if (
      !input ||
      !/^[a-fA-F0-9-]{36}$/.test(input.id) ||
      typeof input.token !== "string" ||
      input.token.length > 8192 ||
      typeof input.path !== "string" ||
      input.path.length > 1024
    )
      throw new Error("无效的本地请求。");
    if (this.calls.has(input.id) || this.calls.size >= 16) throw new Error("本地请求过多。");
    const controller = new AbortController();
    this.calls.set(input.id, controller);
    const timer = setTimeout(() => controller.abort(), 600000);
    try {
      const identity = await this.identity(input.token);
      if (this.owner !== null && this.owner !== identity.owner)
        for (const [id, active] of this.calls) if (id !== input.id) active.abort();
      this.owner = identity.owner;
      controller.signal.throwIfAborted();
      const call = routeLocal(
        input.path,
        (input.method || "GET").toUpperCase(),
        input.query || {},
        (input.body || {}) as Record<string, unknown>,
        identity.owner,
        identity.deviceId,
      );
      if (call.method === "sessions.approval.decide") {
        const detail = await this.json(
          "sessions.approval.lookup",
          { owner_id: identity.owner, body: call.params.body },
          controller.signal,
        );
        call.params.thread_id = detail.thread.id;
        call.params.body = {
          ...(call.params.body as object),
          knowledge_base_ids: detail.knowledge_base_ids,
        };
      }
      if (call.needsRetrieval) {
        const bases = (call.params.body as Record<string, unknown>).knowledge_base_ids;
        if (Array.isArray(bases) && bases.length) {
          if (bases.length > 20 || bases.some((id) => !Number.isSafeInteger(id) || id <= 0))
            throw new Error("知识库选择无效。");
          const response = await fetch(this.api() + "/api/knowledge-bases/retrieval-capability", {
            method: "POST",
            headers: { Authorization: `Bearer ${input.token}`, "Content-Type": "application/json" },
            body: JSON.stringify({ knowledge_base_ids: bases }),
            signal: controller.signal,
            redirect: "error",
          });
          const data = await response.json();
          if (!response.ok || data.code !== 0)
            throw new Error(data.message || "无法取得知识库检索授权。");
          call.params.retrieval_token = data.data.capability;
        }
      }
      const response = await this.rpc(call.method, call.params, controller.signal);
      void (async () => {
        const reader = response.body?.getReader();
        try {
          if (reader)
            while (true) {
              const chunk = await reader.read();
              if (chunk.done) break;
              this.emit({ id: input.id, data: chunk.value });
            }
          this.emit({ id: input.id, done: true });
        } catch {
          this.emit({ id: input.id, error: "本地执行已停止或连接中断。" });
        } finally {
          reader?.releaseLock();
          clearTimeout(timer);
          this.calls.delete(input.id);
        }
      })();
      return {
        status: response.status,
        contentType: response.headers.get("content-type") || "application/json",
      };
    } catch (cause) {
      clearTimeout(timer);
      this.calls.delete(input.id);
      throw cause;
    }
  }
}
