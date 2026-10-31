import type { LocalProject } from "@dp-work/protocols/desktop";
import type {
  ReasoningEvent,
  CompactionEvent,
  SteeringEvent,
  AgentModels,
  AgentChatInput,
  AgentRuntimeConfig,
  ToolExecution,
  FileChange,
  AgentApproval,
  ChatThread,
  AgentProject,
  ThreadDetail,
} from "@/interfaces/agent";
import type { AgentId } from "@/interfaces/app";
import { http } from "@/lib/http";
import { getAccessToken, useAuthStore } from "@/stores/auth";

/** 向正在执行的 Agent 提交引导消息。 */
export const steerAgentRun = (threadId: string, id: string, content: string) =>
  http.post<{ id: string; status: "queued" | "applied" }>(`/api/agents/threads/${threadId}/steer`, {
    id,
    content,
  });

/** 获取当前账号可用的模型列表。 */
export const getAgentModels = () => http.get<AgentModels>("/api/agents/models");

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
  onUsage?: (usage: import("@/interfaces/agent").RunUsage) => void,
  onCompaction?: (event: CompactionEvent) => void,
  onRestore?: (content: string) => void,
): Promise<string | null> {
  const owner = useAuthStore.getState().user?.id;
  const token = getAccessToken();
  let url: string;
  let data:
    | AgentChatInput
    | { decision: "approve" | "reject" }
    | { run_id: string; expected_revision: number };

  if (input.approval_request) {
    // 提交审批决定，继续原任务。
    url = `/api/agents/approvals/${input.approval_request.id}/decide`;
    data = { decision: input.approval_request.decision };
  } else if (input.resume_request) {
    // 从原运行检查点继续，不追加新的用户消息。
    url = `/api/agents/threads/${input.thread_id}/resume`;
    data = input.resume_request;
  } else {
    // 普通聊天必须关联已保存的回复记录。
    if (!input.response_id) throw new Error("回复记录缺失，请重新发送消息。");
    url = `/api/agents/threads/${input.thread_id}/chat`;
    data = input;
  }

  // 审批续接和普通聊天共用流式事件读取逻辑。
  const stream = await http.post<ReadableStream<Uint8Array>>(url, data, {
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
  let paused = false;
  /** 解析并分发一条 SSE 事件。 */
  const consume = (frame: string) => {
    const data = frame
      .split("\n")
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).trimStart())
      .join("\n");
    if (!data) return;
    const event = JSON.parse(data);
    if (event.type === "restore" && typeof event.content === "string") onRestore?.(event.content);
    if (event.type === "compaction") onCompaction?.(event);
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
    const page = await http.get<{ item: { id: string; response_id: string }[] }>(
      "/api/agents/runs",
      { params: { conversation_id: threadId, status: "running", page: 1, page_size: 20 } },
    );
    runId = page?.item?.find((row) => row.response_id === responseId)?.id;
  }
  if (runId) await http.post(`/api/agents/runs/${runId}/cancel`);
}

/** 调用后端 LLM 生成会话标题，再由会话接口保存。 */
export function generateAgentTitle(input: {
  thread_id: string;
  messages: { role: "user" | "assistant"; content: string }[];
  model?: string;
}): Promise<{ title: string }> {
  return http.post("/api/agents/title", input, { timeout: 45000 });
}

/** 读取指定 Agent 的提示词配置。 */
export const getAgentConfig = (code: AgentId, signal?: AbortSignal) =>
  http.get<AgentRuntimeConfig>("/api/agents/config", { params: { agent_code: code }, signal });

/** 保存 Agent 提示词并校验旧版本。 */
export const updateAgentConfig = (code: AgentId, prompt: string, expectedPrompt: string) =>
  http.put<AgentRuntimeConfig>("/api/agents/config", {
    agent_code: code,
    prompt,
    expected_prompt: expectedPrompt,
  });

/** 查询当前会话的工具审批记录。 */
export const listAgentApprovals = (threadId: string) =>
  http.get<AgentApproval[]>("/api/agents/approvals", { params: { conversation_id: threadId } });

/** 从本机快照恢复一次文件修改，不上传文件正文。 */
export const undoAgentFile = (threadId: string, changeId: string) =>
  http.post<{ change: FileChange; thread: ChatThread }>(
    `/api/agents/threads/${threadId}/files/${changeId}/undo`,
  );

const projectsPath = "/api/agents/projects";
/** 获取当前账号的本机项目列表。 */
export const listProjects = () => http.get<AgentProject[]>(projectsPath);
/** 登记用户选择的本机项目目录。 */
export const createProject = (project: LocalProject) =>
  http.post<AgentProject>(projectsPath, {
    id: project.id,
    name: project.name,
    path: project.path,
    device_id: project.device_id,
  });
/** 修改本机项目名称。 */
export const renameProject = (id: string, name: string) =>
  http.patch<AgentProject>(`${projectsPath}/${id}`, { name });
/** 移除项目记录，保留用户目录。 */
export const removeProject = (id: string) => http.delete<null>(`${projectsPath}/${id}`);
/** 调整会话关联的项目。 */
export const setConversationProject = (
  id: string,
  project_id: string | null,
  expected_revision: number,
) =>
  http.patch<ThreadDetail>(`/api/agents/threads/${id}/project`, { project_id, expected_revision });
