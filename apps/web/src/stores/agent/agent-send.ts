import { toast } from "sonner";
import { isContinuationRequest } from "@/features/agent/lib/continuation";
import type { SteeringEvent, ChatMessage, ThreadDetail } from "@/interfaces/agent";
import type { AgentId } from "@/interfaces/app";
import { streamAgentChat, stopAgentRun } from "@/apis/agents";

import { getConversation } from "@/apis/conversations";
import { loadApprovals, markApprovalDecided } from "@/stores/agent/agent-approvals";
import { useAppStore } from "@/stores/app";
import { useAgentModelStore } from "@/stores/agent/agent-models";

import {
  currentOwner,
  mutations,
  owned,
  persistGraph,
  remember,
  runIds,
  runs,
  stops,
  updateList,
  useAgentStore,
} from "./state";
import {
  applyCompaction,
  applyFileChange,
  applyReasoning,
  applySteeringEvent,
  applyToolTrace,
  applyUsage,
  collectMessageBranches,
} from "@/stores/agent/agent-files";
import { getThreadAgentCode, selectThreadById } from "@/stores/agent/agent-threads";

/** 停止当前会话的生成，并中断 API 和 Sidecar 的上游流。 */
export function cancelMessage(id: string) {
  if (!runs.has(id)) return;
  if (!stops.has(id)) {
    const responseId = useAgentStore.getState().details[id]?.messages.at(-1)?.id;
    const stopping = stopAgentRun(id, responseId, runIds.get(id));
    stops.set(id, stopping);
    void stopping.catch(() => {});
  }
  runs.get(id)?.abort();
}

/** 修改历史提问，从该条消息重新生成后续回答。 */
export async function editMessage(
  code: AgentId,
  id: string,
  messageId: string,
  text: string,
  images?: import("@/interfaces/agent").ChatImage[],
) {
  currentOwner();
  const state = useAgentStore.getState();
  const detail = state.details[id];
  const agent = state.agents.find((row) => row.code === code);
  if (!detail || detail.thread.agent_id !== agent?.id)
    throw new Error("会话不存在或与 Agent 不匹配。");
  if (state.sending[id]) throw new Error("请先停止当前生成，再编辑消息。");
  if (!text.trim()) throw new Error("请输入消息。");
  const index = detail.messages.findIndex((row) => row.id === messageId && row.role === "user");
  if (index < 0) throw new Error("只能编辑当前会话中的用户消息。");
  await sendMessage(code, id, text, {
    editedMessageId: messageId,
    images: images ?? detail.messages[index].context.images,
  });
}

/** 针对原用户消息生成新的助手分支。 */
export async function regenerateMessage(code: AgentId, id: string, parentId: string | null) {
  currentOwner();
  const detail = useAgentStore.getState().details[id];
  const parent = detail?.messages.find((row) => row.id === parentId && row.role === "user");
  if (!parent) throw new Error("原消息不存在，请重新加载会话。");
  if (detail?.messages.at(-1)?.status === "waiting_approval")
    throw new Error("请先处理或停止当前审批。");
  await sendMessage(code, id, parent.content, {
    regenerateParentId: parent.id,
    images: parent.context.images,
  });
}

export async function sendMessage(
  code: AgentId,
  id: string,
  text: string,
  options?: {
    editedMessageId?: string;
    regenerateParentId?: string;
    images?: import("@/interfaces/agent").ChatImage[];
  },
) {
  const owner = currentOwner();
  if (!text.trim()) throw new Error("请输入消息。");
  if (!useAgentStore.getState().details[id]) throw new Error("会话尚未加载。");
  if (useAgentStore.getState().sending[id]) throw new Error("Agent 正在回复。");
  const agent = useAgentStore.getState().agents.find((row) => row.code === code);
  if (!agent || useAgentStore.getState().details[id]?.thread.agent_id !== agent.id)
    throw new Error("会话与 Agent 不匹配。");
  const controller = new AbortController();
  runs.set(id, controller);
  useAgentStore.setState((state) => ({
    sending: { ...state.sending, [id]: true },
  }));
  let replyId = "";
  let continuing = false;
  try {
    await mutations.get(`${owner}:${id}`);
    let state = useAgentStore.getState();
    if (!owned(owner) || !state.details[id]) return;
    if (
      !options?.editedMessageId &&
      !options?.regenerateParentId &&
      !options?.images?.length &&
      isContinuationRequest(text)
    ) {
      continuing = true;
      // 先读取服务端的当前分支和检查点状态，不能只相信页面缓存。
      const latest = await getConversation(id);
      if (!owned(owner) || controller.signal.aborted) return;
      remember(owner, code, latest);
      const pending = latest.messages.at(-1);
      if (
        pending?.context.recovery &&
        (pending.status === "cancelled" || pending.status === "failed")
      ) {
        return await resumeExistingRun(
          {
            conversation_id: id,
            response_id: pending.id,
            run_id: pending.context.recovery.run_id,
            checkpoint: true,
            instruction: text.trim(),
          },
          undefined,
          controller,
        );
      }
      continuing = false;
    }
    state = useAgentStore.getState();
    const messages = state.details[id].messages;
    const previousUser = messages.at(-2);
    const retryFailed =
      !options?.editedMessageId &&
      !options?.regenerateParentId &&
      messages.at(-1)?.status === "failed" &&
      previousUser?.role === "user" &&
      previousUser.content === text &&
      JSON.stringify(previousUser.context.images ?? []) === JSON.stringify(options?.images ?? []);
    const pending = {
      id: retryFailed ? previousUser.id : crypto.randomUUID(),
      ...(options?.images?.length ? { images: options.images } : {}),
    };
    replyId = `${retryFailed ? crypto.randomUUID() : pending.id}-reply`;
    const cut = options?.regenerateParentId
      ? state.details[id].messages.findIndex((row) => row.id === options.regenerateParentId) + 1
      : options?.editedMessageId
        ? state.details[id].messages.findIndex((row) => row.id === options.editedMessageId)
        : retryFailed
          ? messages.length - 2
          : messages.length;
    if (cut < 0) throw new Error("待编辑消息已变化，请重新加载。");
    const history = state.details[id].messages
      .slice(0, cut)
      .filter((row) => row.id !== pending.id && row.id !== replyId);
    const now = new Date().toISOString();
    const context: ChatMessage["context"] = {
      ...(options?.images?.length ? { images: options.images } : {}),
      knowledge_bases: [],
      skills: [],
      agent: {
        id: agent.id,
        name: agent.name,
        department: agent.department,
        revision: agent.revision,
      },
    };
    const detail: ThreadDetail = {
      ...state.details[id],
      ...(options?.editedMessageId || options?.regenerateParentId || retryFailed
        ? {
            message_branches: collectMessageBranches(
              state.details[id].messages,
              state.details[id].message_branches,
            ),
          }
        : {}),
      thread: {
        ...state.details[id].thread,
        updated_at: now,
      },
      messages: [
        ...history,
        ...(!options?.regenerateParentId
          ? [
              {
                id: pending.id,
                seq: history.length + 1,
                role: "user" as const,
                content: text,
                created_at: now,
                context,
                status: "complete" as const,
              },
            ]
          : []),
        {
          id: replyId,
          seq: history.length + (options?.regenerateParentId ? 1 : 2),
          role: "assistant",
          content: "",
          created_at: now,
          context: { ...context, images: [] },
          status: "streaming",
        },
      ],
    };
    useAgentStore.setState((current) => ({
      lists: updateList(current, code, detail.thread),
      details: { ...current.details, [id]: detail },
    }));
    const updateReply = (content: string, status: ChatMessage["status"]) => {
      if (!owned(owner) || !useAgentStore.getState().details[id]) return;
      useAgentStore.setState((current) => ({
        details: {
          ...current.details,
          [id]: {
            ...current.details[id],
            messages: current.details[id].messages.map((row) =>
              row.id === replyId ? { ...row, content, status } : row,
            ),
          },
        },
      }));
    };
    await persistGraph(code, id);
    if (!owned(owner)) return;
    let accumulated = "";
    const selectedModel = useAppStore.getState().currentModel;
    const model = useAgentModelStore.getState().data?.models.some((row) => row.id === selectedModel)
      ? selectedModel
      : undefined;
    const content = await streamAgentChat(
      {
        agent_code: code,
        thread_id: id,
        response_id: replyId,
        expected_revision: useAgentStore.getState().details[id].thread.draft_revision,
        knowledge_base_ids: (
          state.agents.find((row) => row.code === code)?.knowledge_base_ids ?? []
        )
          .map((value) => Number(String(value).replace(/^server-/, "")))
          .filter((value) => Number.isSafeInteger(value) && value > 0),
        model,
        messages: [
          ...history
            .filter(
              (row) =>
                row.content &&
                (row.role === "user" ||
                  row.status === "complete" ||
                  (!row.status && !row.content.includes("这是用于体验聊天流程的模拟回复"))),
            )
            .map((row) => ({ role: row.role, content: row.content })),
          ...(!options?.regenerateParentId ? [{ role: "user" as const, content: text }] : []),
        ],
      },
      (delta) => {
        accumulated += delta;
        updateReply(accumulated, "streaming");
      },
      controller.signal,
      (runId) => {
        if (owned(owner)) runIds.set(id, runId);
      },
      (event: SteeringEvent) => {
        if (!owned(owner)) return;
        applySteeringEvent(id, event);
        replyId = event.response_id;
        accumulated = "";
      },
      (trace) => {
        if (owned(owner)) applyToolTrace(id, replyId, trace);
      },
      (change) => {
        if (owned(owner)) applyFileChange(id, replyId, change);
      },
      (event) => {
        if (owned(owner)) applyReasoning(id, replyId, event);
      },
      (usage) => {
        if (owned(owner)) applyUsage(id, replyId, usage);
      },
      (event) => {
        if (owned(owner)) applyCompaction(id, replyId, event);
      },
    );
    if (content !== null) updateReply(content, "complete");
    if (content === null) void loadApprovals(id, true);
    const saved = await getConversation(id);
    if (!owned(owner) || !useAgentStore.getState().details[id]) return;
    remember(owner, code, saved);
  } catch (error) {
    if (!owned(owner) || !useAgentStore.getState().details[id]) return;
    const cancelled = controller.signal.aborted;
    if (continuing) {
      if (!cancelled) {
        toast.error(error instanceof Error ? error.message : "任务恢复失败，请重试。");
        throw error;
      }
      return;
    }
    if (cancelled) await stops.get(id)?.catch(() => {});
    useAgentStore.setState((state) => ({
      details: {
        ...state.details,
        [id]: {
          ...state.details[id],
          messages: state.details[id].messages.map((row) =>
            row.id === replyId
              ? {
                  ...row,
                  status: cancelled ? "cancelled" : "failed",
                  content: row.content || (cancelled ? "已停止生成。" : "生成失败，请重试。"),
                }
              : row,
          ),
        },
      },
    }));
    try {
      const saved = await getConversation(id);
      const remote = saved.messages.find((row) => row.id === replyId);
      if (remote?.status === "streaming") {
        await persistGraph(code, id);
      } else remember(owner, code, saved);
    } catch {
      /* 保存失败保留页面错误和内容，可重新加载服务端版本。 */
    }
    if (owned(owner)) await loadApprovals(id, true);
    if (!cancelled) throw error;
  } finally {
    if (runs.get(id) === controller) runs.delete(id);
    runIds.delete(id);
    stops.delete(id);
    if (owned(owner))
      useAgentStore.setState((state) => ({
        sending: { ...state.sending, [id]: false },
      }));
  }
}

/** 在原会话与原回复上续接审批或中断，不另建消息。 */
async function resumeExistingRun(
  approval: import("@/interfaces/agent").AgentApproval | import("@/interfaces/agent").ResumableRun,
  decision?: "approve" | "reject",
  existingController?: AbortController,
) {
  const owner = currentOwner();
  const id = approval.conversation_id;
  const code = getThreadAgentCode(id);
  if (!code || (runs.has(id) && runs.get(id) !== existingController))
    throw new Error("会话正在执行，请稍后重试。");
  if (!useAgentStore.getState().details[id]) await selectThreadById(id);
  const controller = existingController ?? new AbortController();
  runs.set(id, controller);
  useAgentStore.setState((state) => ({
    sending: { ...state.sending, [id]: true },
  }));
  let responseId = approval.response_id;
  let accumulated =
    useAgentStore.getState().details[id].messages.find((row) => row.id === approval.response_id)
      ?.content ?? "";
  try {
    await streamAgentChat(
      {
        agent_code: code,
        thread_id: id,
        messages: [],
        ...("checkpoint" in approval
          ? {
              resume_request: {
                run_id: approval.run_id,
                instruction: approval.instruction,
                expected_revision: useAgentStore.getState().details[id].thread.draft_revision,
              },
            }
          : { approval_request: { id: approval.id, decision: decision! } }),
      },
      (delta) => {
        if (!owned(owner)) return;
        accumulated += delta;
        useAgentStore.setState((state) => ({
          details: {
            ...state.details,
            [id]: {
              ...state.details[id],
              messages: state.details[id].messages.map((row) =>
                row.id === responseId ? { ...row, content: accumulated, status: "streaming" } : row,
              ),
            },
          },
        }));
      },
      controller.signal,
      (runId) => {
        if (!owned(owner)) return;
        runIds.set(id, runId);
        if (!("checkpoint" in approval)) markApprovalDecided(approval, decision!);
        useAgentStore.setState((state) => ({
          details: {
            ...state.details,
            [id]: {
              ...state.details[id],
              messages: state.details[id].messages.map((row) =>
                row.id === responseId ? { ...row, status: "streaming" } : row,
              ),
            },
          },
        }));
      },
      (event) => {
        if (!owned(owner)) return;
        applySteeringEvent(id, event);
        responseId = event.response_id;
        accumulated = "";
      },
      (trace) => {
        if (owned(owner)) applyToolTrace(id, responseId, trace);
      },
      (change) => {
        if (owned(owner)) applyFileChange(id, responseId, change);
      },
      (event) => {
        if (owned(owner)) applyReasoning(id, responseId, event);
      },
      (usage) => {
        if (owned(owner)) applyUsage(id, responseId, usage);
      },
      (event) => {
        if (owned(owner)) applyCompaction(id, responseId, event);
      },
      (content) => {
        if (!owned(owner)) return;
        accumulated = content;
        useAgentStore.setState((state) => ({
          details: {
            ...state.details,
            [id]: {
              ...state.details[id],
              messages: state.details[id].messages.map((row) =>
                row.id === responseId
                  ? {
                      ...row,
                      content,
                      status: "streaming",
                      context: { ...row.context, recovery: undefined },
                    }
                  : row,
              ),
            },
          },
        }));
      },
    );
  } finally {
    if (controller.signal.aborted) await stops.get(id)?.catch(() => {});
    if (!existingController) {
      if (runs.get(id) === controller) runs.delete(id);
      runIds.delete(id);
      stops.delete(id);
    }
    if (owned(owner)) {
      try {
        remember(owner, code, await getConversation(id));
      } finally {
        if (owned(owner)) {
          if (!existingController)
            useAgentStore.setState((state) => ({
              sending: { ...state.sending, [id]: false },
            }));
          await loadApprovals(id, true);
        }
      }
    }
  }
}

/** 在原运行上提交审批决定并继续执行。 */
export function resumeApprovedRun(
  approval: import("@/interfaces/agent").AgentApproval,
  decision: "approve" | "reject",
) {
  return resumeExistingRun(approval, decision);
}
