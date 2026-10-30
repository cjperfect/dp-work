import type { AxiosAdapter, AxiosResponse } from "axios";
import { AxiosHeaders } from "axios";
import { getStoredToken } from "./token-storage";

/** 可直接展示给用户的本机环境错误。 */
export class LocalTransportError extends Error {}

/** 会议、知识库及账号走远程，其余业务只能在桌面本机执行。 */
export function isLocalBusiness(path: string): boolean {
  return (
    /^\/api\/(agents|skills|connectors|memories|usage)(?:\/|$)/.test(path) ||
    /^\/api\/settings(?:\/|$)/.test(path)
  );
}

/** 将本机 IPC 字节流适配成 Axios 响应，保持现有业务 API 和错误处理。 */
export const localAdapter: AxiosAdapter = async (config) => {
  const desktop = typeof window === "undefined" ? undefined : window.desktop;
  if (!desktop?.localRequest || !desktop.onLocalChunk)
    throw new LocalTransportError("请在桌面端使用项目、会话等本地功能，浏览器无法连接本机服务。");
  const id = crypto.randomUUID();
  const token = getStoredToken();
  if (!token) throw new Error("请先登录。");
  let detach = () => {};
  let cleanup = () => {};
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      detach = desktop.onLocalChunk!((chunk) => {
        if (chunk.id !== id) return;
        if (chunk.error) {
          controller.error(new Error(chunk.error));
          cleanup();
        } else if (chunk.done) {
          controller.close();
          cleanup();
        } else if (chunk.data) controller.enqueue(new Uint8Array(chunk.data));
      });
    },
    cancel() {
      cleanup();
      void desktop.cancelLocalRequest?.(id);
    },
  });
  const abort = () => {
    void stream.cancel().catch(() => {});
    void desktop.cancelLocalRequest?.(id);
  };
  const signal = config.signal;
  const timeout = config.timeout ? setTimeout(abort, config.timeout) : undefined;
  cleanup = () => {
    detach();
    clearTimeout(timeout);
    signal?.removeEventListener?.("abort", abort);
  };
  signal?.addEventListener?.("abort", abort);
  if (signal?.aborted) {
    abort();
    throw new Error("请求已取消。");
  }
  try {
    const data = typeof config.data === "string" ? JSON.parse(config.data) : config.data;
    const head = await desktop.localRequest({
      id,
      token,
      path: config.url!,
      method: config.method,
      query: config.params || {},
      body: data,
    });
    let responseData: unknown = stream;
    if (config.responseType !== "stream" || head.status !== 200) {
      const raw = await new Response(stream).json();
      responseData =
        head.status === 200
          ? { code: 0, message: "成功", data: raw }
          : { code: head.status, message: raw.detail?.message || "本地操作失败。", data: null };
    }
    return {
      data: responseData,
      status: head.status,
      statusText: head.status === 200 ? "OK" : "Error",
      headers: new AxiosHeaders({ "Content-Type": head.contentType }),
      config,
    } as AxiosResponse;
  } catch (cause) {
    cleanup();
    void desktop.cancelLocalRequest?.(id);
    throw cause;
  }
};
