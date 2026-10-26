import { request } from "@/lib/http";
import { getAccessToken, useAuthStore } from "@/stores/auth";
import type { AgentId } from "@/interfaces/app";

export type AgentModels = { configured: boolean; models: { id: string; name: string }[] };
export const getAgentModels = () => request<AgentModels>("/api/agents/models");
export type AgentChatInput = {
  agent_code: AgentId;
  thread_id: string;
  messages: { role: "user" | "assistant"; content: string }[];
  model?: string;
  knowledge_base_ids?: number[];
};

/** 使用统一 Axios 客户端读取 SSE；缺少 done 或流中断均视为未完成。 */
export async function streamAgentChat(
  input: AgentChatInput,
  onDelta: (text: string) => void,
  signal: AbortSignal,
): Promise<string> {
  const owner = useAuthStore.getState().user?.id;
  const token = getAccessToken();
  const stream = await request<ReadableStream<Uint8Array>>("/api/agents/chat", {
    method: "POST",
    data: input,
    adapter: "fetch",
    responseType: "stream",
    signal,
    timeout: 240000,
  });
  if (!stream || typeof stream.getReader !== "function")
    throw new Error("Agent 返回了无效的事件流。");
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let completed: string | null = null;
  const consume = (frame: string) => {
    const data = frame
      .split("\n")
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).trimStart())
      .join("\n");
    if (!data) return;
    const event = JSON.parse(data);
    if (event.type === "error") throw new Error(event.message || "Agent 执行失败，请重试。");
    if (event.type === "delta" && typeof event.text === "string") onDelta(event.text);
    if (event.type === "done" && typeof event.content === "string") completed = event.content;
  };
  try {
    while (true) {
      if (signal.aborted) throw new Error("已停止生成。");
      const chunk = await reader.read();
      if (useAuthStore.getState().user?.id !== owner || getAccessToken() !== token)
        throw new Error("登录状态已改变，请重试。");
      buffer += chunk.done ? decoder.decode() : decoder.decode(chunk.value, { stream: true });
      buffer = buffer.replace(/\r\n/g, "\n");
      let split: number;
      while ((split = buffer.indexOf("\n\n")) !== -1) {
        consume(buffer.slice(0, split));
        buffer = buffer.slice(split + 2);
      }
      if (completed !== null) return completed;
      if (chunk.done) break;
      if (buffer.length > 2_000_000) throw new Error("Agent 响应片段过大。");
    }
    throw new Error("Agent 回答中断，请重试。");
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
