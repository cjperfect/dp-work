import { request } from "@/lib/http";
import { getAccessToken, useAuthStore } from "@/stores/auth";
import type { AgentId } from "@/interfaces/app";
export type ReasoningEvent = {
  id: string;
  text?: string;
  started_at: number;
  completed_at?: number;
};
import type { ChatThread, ChatMessage, ToolExecution, FileChange } from "@/types/agent";

export type SteeringEvent = {
  id: string;
  response_id: string;
  previous_response_id: string;
  previous_content: string;
  previous_removed: boolean;
  thread: ChatThread;
  message: ChatMessage;
  response: ChatMessage;
};
export const steerAgentRun = (threadId: string, id: string, content: string) =>
  request<{ id: string; status: "queued" | "applied" }>(`/api/agents/threads/${threadId}/steer`, {
    method: "POST",
    data: { id, content },
  });

export type AgentModels = { configured: boolean; models: { id: string; name: string }[] };
export const getAgentModels = () => request<AgentModels>("/api/agents/models");
export type AgentChatInput = {
  approval_request?: { id: string; decision: "approve" | "reject" };
  response_id?: string;
  expected_revision?: number;
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
  onStart?: (runId: string) => void,
  onSteering?: (event: SteeringEvent) => void,
  onTool?: (trace: ToolExecution) => void,
  onFileChange?: (change: FileChange) => void,
  onReasoning?: (event: ReasoningEvent) => void,
  onUsage?: (usage: import("@/types/agent").RunUsage) => void,
): Promise<string | null> {
  const owner = useAuthStore.getState().user?.id;
  const token = getAccessToken();
  const stream = await request<ReadableStream<Uint8Array>>(
    input.approval_request
      ? `/api/agents/approvals/${input.approval_request.id}/decide`
      : input.response_id
        ? `/api/agents/threads/${input.thread_id}/chat`
        : "/api/agents/chat",
    {
      method: "POST",
      data: input.approval_request ? { decision: input.approval_request.decision } : input,
      adapter: "fetch",
      responseType: "stream",
      signal,
      timeout: 240000,
    },
  );
  if (!stream || typeof stream.getReader !== "function")
    throw new Error("Agent 返回了无效的事件流。");
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let completed: string | null = null;
  let paused = false;
  const consume = (frame: string) => {
    const data = frame
      .split("\n")
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).trimStart())
      .join("\n");
    if (!data) return;
    const event = JSON.parse(data);
    if (event.type === "usage" && event.usage) onUsage?.(event.usage);
    if (event.type === "reasoning" || event.type === "reasoning_end") onReasoning?.(event);
    if (event.type === "file_change" && event.change) onFileChange?.(event.change);
    if ((event.type === "tool_call" || event.type === "tool_result") && event.trace)
      onTool?.(event.trace);
    if (event.type === "steering") onSteering?.(event);
    if (event.type === "start" && typeof event.run_id === "string") onStart?.(event.run_id);
    if (event.type === "approval") paused = true;
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
      if (paused) return null;
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

/** 停止服务端运行并释放会话执行锁，再开始下一条消息。 */
export async function stopAgentRun(threadId: string, responseId?: string, runId?: string) {
  if (!runId) {
    const page = await request<{ item: { id: string; response_id: string }[] }>(
      "/api/agents/runs",
      {
        params: { conversation_id: threadId, status: "running", page: 1, page_size: 20 },
      },
    );
    runId = page?.item?.find((row) => row.response_id === responseId)?.id;
  }
  if (runId) await request(`/api/agents/runs/${runId}/cancel`, { method: "POST" });
}

/** 调用后端 LLM 生成会话标题，再由会话接口保存。 */
export function generateAgentTitle(input: {
  thread_id: string;
  messages: { role: "user" | "assistant"; content: string }[];
  model?: string;
}): Promise<{ title: string }> {
  return request("/api/agents/title", { method: "POST", data: input, timeout: 45000 });
}

export type AgentRuntimeConfig = { agent_code: AgentId; prompt: string; prompt_file: string };
export const getAgentConfig = (code: AgentId, signal?: AbortSignal) =>
  request<AgentRuntimeConfig>("/api/agents/config", { params: { agent_code: code }, signal });

export const updateAgentConfig = (code: AgentId, prompt: string, expectedPrompt: string) =>
  request<AgentRuntimeConfig>("/api/agents/config", {
    method: "PUT",
    data: { agent_code: code, prompt, expected_prompt: expectedPrompt },
  });
